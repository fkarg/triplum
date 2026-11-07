# External ids, Viewer and source access (draft for owner review)

Status: **approved** by the owner (P6 and P7, 2026-11-07) and implemented. Two separately approvable declarations: P6 (BE18 `external_id`) and P7
(RT3/RT6 Viewer and access). Settled by the owner in round 7: BE18 (b), RT3 (a), RT6 with raising
reads. Neither touches retrieval (P8) or scoring (P9).

## P6: `Source.external_id`

```python
class Source(BaseModel):
    ...
    external_id: str | None = Field(
        default=None,
        description="The dataset's own key for this document, unique within the collection when set.",
    )
```

- Outside the id: the id stays `(collection_id, origin, text)`. A source equal in those fields but
  with another `external_id` is an unequal duplicate, so `add_sources` raises.
- Inside `fingerprint()`: it is data a computation may read (evidence resolution), so value
  identity must cover it: `content_key("source", [collection_id, origin, text, external_id])`.
  The fingerprint then no longer has exactly the id's inputs, and every existing Source
  fingerprint changes once (cached results recompute).
- `add_sources` raises `ValueError`, before writing anything, when a source's non-null
  `external_id` is held by a different source of the same collection, stored or earlier in the
  batch. SQL: nullable column, unique index on `(collection_id, external_id)` (SQLite and
  PostgreSQL treat NULLs as distinct), with the check done in `store/checks.py` first so both
  stores raise the same error.
- SQL stores and reads the column (`SourceRow`, insertion and `_source` enumerate fields).
- No read by external id yet: evaluation resolves evidence from the benchmark's own corpus (one
  collection), `{s.external_id: s.id for s in corpus if s.external_id is not None}`.
- `LegacyFixture` sets `external_id` to the legacy document id (origin unchanged).
- Known consequence (BE19, open): two text revisions of one document cannot both carry its
  external id.

## P7: Viewer and access

```python
# src/triplum/datatype/viewer.py
class Viewer(BaseModel):
    """Who is reading. A source is visible when its allowed principals and `principals` meet."""

    model_config = ConfigDict(frozen=True)

    principals: frozenset[str]
```

`RecordStore` changes (both stores):

```python
def add_sources(self, sources: Iterable[Source], /, *, allow: Iterable[str]) -> None:
    """Store each new source, readable by the principals in `allow`.

    Re-adding a stored source with the same `allow` does nothing; with a different `allow`, or
    a different source under a stored id, raises `ValueError`.
    """


def source(self, id: UUID, /, *, viewer: Viewer) -> Source:
    """The source with this `id`; `KeyError` if there is none or `viewer` may not read it."""


def sources(self, *, viewer: Viewer) -> Iterator[Source]:
    """The sources `viewer` may read, in no particular order."""


def chunks(self, source_id: UUID, /, *, viewer: Viewer) -> list[Chunk]:
    """The current chunks of a source `viewer` may read, by `ordinal`; `KeyError` otherwise."""
```

- Access lives in the store, keyed by Source id: SQL table `source_access(source_id, principal)`;
  memory `dict[UUID, frozenset[str]]`. It is not part of `Source`, its id or fingerprint.
- One `allow` per call; sources with different access are added in separate calls, with no
  all-or-nothing guarantee across calls. An empty `allow` is accepted (nobody may read; no
  operation can change it yet). Each call checks the whole input before writing, **including
  equal stored sources** that `new_sources` currently drops: an equal source with a different
  `allow` raises.
- Guarantees assume serialized writers (memory: single-threaded; SQL: one transaction, and two
  concurrent writers of the same new source may surface the database's integrity error rather than
  the promised `ValueError` or no-op).
- Visibility: `allow ∩ viewer.principals` nonempty. `"public"` is an ordinary principal. A Viewer
  without principals sees nothing.
- Missing and invisible raise the same `KeyError(id)`, so **reads** do not reveal existence.
  Visibility is decided before a record is reconstructed (SQL: an `EXISTS` predicate), so a
  corrupt invisible row also reads as missing and several matching principals do not duplicate
  results. `chunks()` of an unknown source changes from `[]` to `KeyError`.
- Writes are trusted ingestion and take no Viewer: `add_sources` and `replace_chunks` conflict
  errors necessarily reveal stored ids. The store is not an authorization boundary for writers.
  Chunks inherit their source's access.
- Databases created before this change are not upgraded (no migrations); recreate them.
- No revoke or update operation; no time axes. Derived-record access (intersection) arrives with
  those records.
- `LegacyFixture` callers pass `allow=["public"]`; the fixture's own grants stay unused (gatemem
  is the only fixture with per-principal grants).

## Verification plan

- P6: conflicting external id across stored/batch sources raises and stores nothing; same
  external id in another collection is fine; `None` never conflicts; equal re-add no-op; SQL and
  memory alike; fingerprint changes with external id; fixture sets it.
- P6 also: external id survives an SQL reopen; same id with differing external id (None vs a
  string) raises.
- P7: invisible equals missing for `source` and `chunks`, including a corrupt invisible SQL row;
  `sources` filters and does not duplicate with two matching principals; public principal; empty
  principals; conflicting `allow` raises without writing, also for an equal stored source after a
  new one in the batch; equal re-add no-op; both stores via the existing parametrized store
  tests; `examples/naive.py` updated and run.

## Implementation review

Security reviewer (its peer gpt-6.1-sol `0c9c784c7c7a42a0a55ac91aeccb8bc2`, which independently found
the same defect): unique defect, a bare string `allow="team"` allowed the principals `t`, `e`, `a`,
`m` → `TypeError`, with a regression test. Noted: principal matching is exact on SQLite and
PostgreSQL, the supported SQL backends; case-insensitive collations (MySQL, many MSSQL setups) would
diverge from the memory store. Old databases fail closed. General reviewer (its peer gpt-6.1-sol `72ddfbff96824ab2b49900642498d49b`
found the same independently): unique defect, SQL flushed access rows before their source rows, so
`add_sources` failed wherever foreign keys are enforced (always on PostgreSQL) → sources flushed
first, regression test with SQLite `foreign_keys=ON` (failed before the fix, observed); also
found the bare-string `allow`; nits applied (docstring wrapping, `chunks()` on a corrupt hidden
row). Simplicity reviewer (its peer gpt-6.1-sol `24cf857c…`): shorter test helper and a plain
lambda applied; explicit branches in `new_sources` not applied (its peer argued against them),
memory index and separate access dict kept (performance; spec layout). Constraints for P8 (BM25): mask to the
viewer's sources before top-k; never return or tie-break with hidden chunks; key any index or
result cache by the principal set; rebuild when sources or access change; global corpus
statistics leak term statistics of hidden sources through visible scores (RT5 chose global
statistics for benchmarks; private corpora need viewer-scoped statistics, an open P8 question).

## Peer review

gpt-6.1-sol, review `583e06a23d8e4b5795f8a19b8a54a822` (falsifications: failing iterables, conflict
after a new batch source, interleaved SQL sessions, `replace_chunks` existence probe, corrupt
invisible rows, a Source subclass with the field, SQLite NULL/empty-string uniqueness, equal stored
sources dropped by `new_sources`, hidden top-scoring chunk for P8). Dispositions: unique defects,
equal stored sources skipped grant checks, reconstruction before authorization leaks existence,
SQL field enumeration would drop `external_id` → all in the draft; changed decision, existence
secrecy scoped to reads, writes trusted; added verification, serialized-writer scope stated, no
upgrade path; no impact, P8 can mask from `sources(viewer=...)` ids without a new method.
Tradeoffs: agrees on one `allow` per call and `external_id` in the fingerprint; recommends
accepting an empty `allow`, which the draft now does.

## Unresolved tradeoffs

None beyond the above; each choice is the owner's to approve with the declaration.
