# Minimal Markdown indexing

Owner scope: ignore the old design. Read a folder of Markdown files, reuse the existing
RecordDataset and pass-through DataLoader, slice every X characters, retain chunks in memory.
No embedding, retrieval, backend, registry or new Protocol.

## Current prototype

The owner separated the records into `src/triplum/datatype/source.py` and
`src/triplum/datatype/chunk.py`. Both are independent Pydantic models:

- `Source(origin: Path | str, text: str)` holds text and its origin, such as a file path or URL.
- `Chunk(origin: Path | str, start: int, text: str)` holds an excerpt and its origin. `start` is a
  Python character offset into source text; it is not a byte offset.

`src/triplum/indexing.py` contains `index_folder(folder, chunk_size)`, returning a list of chunks.
The list is the toy store. The function reads top-level files in sorted order as UTF-8 without
newline conversion. Empty files yield no chunks; slicing keeps the final short chunk. Invalid
folders and nonpositive or boolean chunk sizes are rejected.

## Structure

**Owner decision:** keep `Source` and `Chunk` in separate files under `datatype/`. Build barebones
pipelines, then expand and generalize them step by step. The model base/ORM choice (`BaseModel`,
`SQLModel` or a custom base) remains open; this decision does not approve the whole pipeline.

The remaining proposal is to keep transformation functions, and any future Protocol that
actually needs interchangeable implementations, with the operation they describe. Let indexing
compose those operations. This prototype does not yet need a Protocol or additional modules for
single-use functions. `Source` and `Chunk` do not inherit from each other: a chunk refers to its
source origin and adds an offset; it is not the complete source.

## Verification checkpoint

- [ ] Pin the folder-to-chunks behavior with a temporary-directory workflow test.
- [ ] Implement the concrete function using existing data utilities.
- [ ] Document the small example and actual implementation state.
- [ ] Run tests, typing, strict docs and pre-commit; commit the checkpoint.

Opus 5.5 reviewed the minimal proposal. Impact: added verification of CRLF preservation and
file-only glob filtering. It supported using RecordDataset and a plain list as the store.
Its concern about two Source names does not require renaming existing utilities: the indexing module
imports its record from `datatype.source` and only `RecordDataset` and `DataLoader` from the data
utilities. This earlier review predates the owner’s record extraction.

### Record-separation review

Claude Opus 5.5 reviewed the record extraction. **Impact: added verification.** Running the
prototype tests found stale `Chunk(source=...)` constructions after the rename to `origin`:
one test failed and four passed. No code was changed during this discussion.

**Dissent retained:** Opus recommends keeping both records in `indexing.py` until a second consumer
exists, then moving them into one shared module. The owner resolved this choice in favor of
keeping `Source` and `Chunk` in separate files under `datatype/`. Opus’s alternative was not adopted.

The peer searched consumers and repository conventions and tested inheritance equality; it found
no equality defect. Its substitutability and source-offset concerns support keeping `Source` and
`Chunk` independent. Its suggestion to remove `RecordDataset`/`DataLoader` was rejected because
the owner explicitly requested their reuse.

### Model base and ORM — discussion, not approved

Owner requirement: persistence should eventually support both relational and graph databases.
Separate backend model variants and duplicated fields are acceptable.

The unapproved recommendation is shared `BaseModel` pipeline records with storage representations
owned by each concrete backend as it is introduced, rather than a universal ORM hierarchy.

Recommendation: retain `BaseModel` for the current in-memory pipeline; consider `SQLModel` when a
concrete SQL storage step arrives. The options are:

| Option | Tradeoff |
| --- | --- |
| Non-table `SQLModel` base with table-specific models | Shares fields, but adds the ORM dependency before storage needs it |
| Direct table models | A short SQL path, with mapping/session behavior and explicit validation to account for |
| `BaseModel` plus storage-specific mapping | Keeps storage concerns separate, at the cost of conversion |

A custom base is useful only for shared configuration or behavior. It does not make an ORM
switchable or automatically preserve user subclasses through persistence. References:
[SQLModel multiple models](https://sqlmodel.tiangolo.com/tutorial/fastapi/multiple-models/) and
[Pydantic configuration](https://docs.pydantic.dev/latest/concepts/config/).

Claude Opus 5.5 tested SQLModel 0.0.47 constructors versus `model_validate`, union-column rejection,
table inheritance versus a non-table base, `model_dump` before/after generated IDs and SQLite
roundtrips. **Impact: added verification.** Generated database IDs change the current fingerprint
if included in the dump; preserving the `Path` versus `str` distinction requires explicit encoding.

**Rejected as overgeneralized:** the claim that SQL cannot roundtrip `Path | str`. The failed test
used naive text encoding; a custom tagged mapping can preserve the distinction. Opus's preference
for `sqlite3` remains an option, not an agreed next step. Nothing in this discussion is implemented
or approved.
