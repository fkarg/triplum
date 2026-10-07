# Computation tables and cache utilities implementation plan

**Goal:** Computation→data cache identity and inspection/clearing without migration machinery.
**Authorization:** Owner explicitly selected per-computation tables and requested implementation.
**Contracts:** docs/specs/cache-interfaces.md and docs/specs/cli-selection.md.

CacheKey becomes (process: bytes, input: bytes). SQLite table cache_<full process hex> has input BLOB
primary key and value BLOB, using ordinary rowid tables. Codec only encodes/decodes. Semantic input
changes change input identity; output/computation changes require process revision or clearing.
No hidden format identity is introduced. No migration; existing unscoped rows are ignored.

- [x] Test/implement process isolation, data-only row key, persistence, missing-table misses,
  creation on write and recreation after clearing. Remove format from keys/codecs.
- [x] Test/implement importable read-only stats and transactional clear on temporary databases.
  Fast stats avoid data-table scans; --details opts into counts/byte sums. Path lookup performs no I/O.
- [x] Delegate independent CLI implementation with subprocess tests and standard-library parsing.
- [x] Delegate docs sync, review changes independently, run Python/typing/style/Cargo/MkDocs checks,
  and commit coherent verified changes periodically.

## Review decisions

Claude Opus 5.5, design review 0055212ba7284728bf9314b6de79b8b9, preferred a single composite-key
table because retained variants increase schema/opening costs and tables still share one writer.
Owner selected per-computation tables; no speed win is claimed. Its proposal to fold format into
computation identity is rejected under the owner's explicit no-format/no-migration requirement.
Model/output changes need computation revision or clearing, not just input changes. CLI approval
concerns preceded the owner's explicit selection and this written command contract.

Adopted: committed/runtime stats distinction, point-in-time clearing, no unlink/VACUUM, exact opaque
selectors and schema overhead caveat. Peer checked output-schema coverage, absent CLI/counters and
clearing concurrency assumptions; did not measure DROP/DELETE or large-database performance.


Claude Opus 5.5 diff review 4f2c16a9319a4bbebd3c8d3e2c22c70b found a unique defect in
legacy cleanup: dropping a generic cache_entries table could affect an unrelated database.
Removed that special case and added a preservation regression test. Adopted documentation
clarifications for output-schema responsibility and read-only WAL sidecars. Injection,
reader/clear races, retained read snapshots and concurrent table creation were tested without
finding defects. Exact missing-table error matching and CLI error exit codes remain unchanged;
both fail visibly. No performance claim follows from this review.
