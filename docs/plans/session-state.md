# Session state (2026-09-29)

Hand-off note for continuing the v2 rewrite on branch `v2-rewrite`. The latest commit is a
work-in-progress snapshot, but tests, ruff, ty and the strict docs build pass.

## Where things are

- Records: `datatype/source.py` and `datatype/chunk.py` are Pydantic models.
  - Both use a uuid7 `id`, plus a `fingerprint` computed field (`content_key` over the content).
  - `Chunk` has `source_id`, `origin`, `start` and `text`.
- Steps (`steps/`): a Protocol per step, and our implementations subclass it together with
  `Fingerprinted`.
  - Converter: `Utf8File`
  - Chunker: `FixedSize`
  - EmbeddingText: `OriginalText`
  - Embedder: `ZeroEmbedder`
- Store (`store/`):
  - The `RecordStore` protocol, with two implementations: `MemoryStore` and
    `SQLAlchemyStore(url="sqlite://")`.
  - The SQLAlchemy tables are in `store/sql/tables.py`.
  - `store/graph/` is an empty placeholder.
- Utils: `utils/fingerprint.py` (`Fingerprinted`, `source_hash`) and `utils/cache.py`
  (`content_key`, `Cache`).
- Datasets:
  - `MarkdownFolder` (reference dataset)
  - `MultiHopRAGCorpus` with `download()`
- Docs:
  - `docs/concepts/*` covers the steps and records.
  - `docs/infrastructure/{store,fingerprints,cache}.md`.
  - `docs/specs/record-types.md` holds the record-type research and proposal. It is a draft and
    has no decisions yet.
- Owner prototypes, committed in this snapshot at the owner's request:
  - `steps/indexing.py`
  - `steps/ingestion.py` (an outline)
  - `examples/naive.py`
  - `tests/test_indexing_prototype.py`

## Just changed

The owner changed `Source.origin` to `str`, and I carried the change through mechanically:
- `Utf8File` and `MarkdownFolder` now pass `str(path)`.
- `SourceRow` no longer has `origin_is_path`.
- Tests and docs examples are updated.

Still open:
- `Chunk.origin` is still `Path | str`. The proposal is to drop it, since the origin can be
  reached through `source_id`.
- Whether file origins should become `file://` URIs.

## Decided so far (recent)

- Protocols define the step contracts; type aliases are used only for data shapes.
- Store and cache are separate. The cache stays SQLite. Store backends will be benchmarked
  later.
- One Protocol per store capability (records, vectors, blobs, graph).
  - Implementations are grouped by backend.
  - `SQLAlchemyStore` is the generic variant; specialised ones come later where they are faster.
- Row models are written by hand, maybe with automatic checks for field coverage and
  serialisation, rather than generated.
- The record `fingerprint` becomes a plain method instead of a computed field.
  - Agreed, not yet implemented.
  - Stores would fill the column from `record.fingerprint()`.
- Record types: a many-to-many membership table for groups, which allows several parents.
  - Entities will likely need the same (several relations/parents); revisit with the graph
    types.
- Python 3.14 is the minimum version.

## Open, in suggested order

The details for each item are in `docs/specs/record-types.md`.

1. **Collection level:** the search and permission boundary. Its name is open (collection / data
   room / context / folder). `collection_id` goes on every row.
2. **Reproducible UUIDv8 layout** for locality within the `source_id` indexes:

   ```
   source: [collection 32][source hash 28][rest 62]
   chunk:  [collection 32][source hash 28][start 32][hash 30]
   ```

   - With a 32-bit collection prefix, two sources sharing a prefix becomes likely at about
     20k sources.
   - My recommendation is 16/44 instead.
   - Prefix collisions only cost locality, not correctness.
   - The layout also fixes the duplicates that appear on re-runs.
3. **Source fields:**
   - `acl`
   - `reference_time` / `observed_at`
   - `metadata`
   - `supersedes`
   - `origin` is now a str (done)
4. **Chunk:** drop `origin`, add `parent_id` / `level`, and define that offsets index the
   post-preprocessing `Source.text`.
5. **Representations:** `ChunkText`, `EmbeddingConfig`, and `Vector` keyed by (owner, config).
6. **Graph:**
   - `Mention`, `Entity`
   - `Relation`, with two time axes (valid time and recorded time) plus `invalidated_by`
   - an optional `EntityLink`
7. **Groups and summaries:** `Group` plus membership, and `Summary`.
   - The ACL of derived content is the intersection of its inputs' ACLs.
   - No community summaries until they are principal-scoped.

These break things if added later:
- `collection_id` on Source and Chunk
- `acl` on Source
- how vectors are keyed
- the offset definition

## Known issues (later)

- Re-running creates duplicates because ids are random; this is solved by (2).
- `RecordDataset.fingerprint` includes the ids, so it is nondeterministic.
- The `Dataset.fingerprint` contract needs rethinking. The owner leans towards lazy
  fingerprints that are available only after the dataset has been consumed.
- Replacing a source keeps its old chunks.
- The `utils.data.Source` alias clashes with `datatype.Source`.
- Add a composite index on `(source_id, start)`.
- `SQLAlchemyStore.sources()` loads everything, and merging row by row is slow.
- The examples in the docs are not tested automatically.

## Working agreements

- The owner decides the core design one topic at a time. Implement only what has been decided,
  and don't run ahead.
- Keep the hand-written docs in sync: use a docs subagent after interface changes, spell out
  practical usage, and add a licence row for every new dependency.
- Commit only when asked.
- Codex peer review is available again; use it where a design fork warrants the latency.
