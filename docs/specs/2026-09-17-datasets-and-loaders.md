# Dataset and loader foundation

Snapshot: 2026-09-17. Approved by the owner in conversation. Replace the existing API outright;
work and commit on local main. There are no compatibility consumers.

## Contract

`Dataset[T]` provides indexed access (`__getitem__`, `__len__`). `IterableDataset[T]`
provides `__iter__` without requiring length, random access, or replay. Both require a
dataset-owned `fingerprint() -> str` for persistent logical identity; computing it must not
consume iteration. Both are
small overridable classes in `triplum.utils.data`. Records belong to the dataset author.
Built-in sources move from `triplum.eval.datasets` to `triplum.datasets`.

`DataLoader[T, B]` accepts these classes and ordinary Python iterables. It lazily batches
records and applies a supplied collator; its default yields lists. Disabling batching passes
through source items, including native columnar batches. It does not download, hash, write
stores, silently shuffle, or impose task schemas. Invalid batch sizes fail at construction.
One-shot iterators remain one-shot; creating a loader does not consume them.

Canonical Arrow schemas remain the store boundary. `CorpusBatch` groups documents, grants,
and chunks for ingestion. A benchmark composition references a corpus source and independent
QA and/or extraction evaluation sources. Gold triples are owned by extraction evaluation,
never by the generic Dataset or corpus. The old five-frame `Frames` and frozen `Dataset`
are removed, including their parser, fixture, and test contracts.

Existing parsers may still read their upstream files eagerly. Existing algorithms may explicitly
materialize task inputs at the benchmark boundary in this change: the owner explicitly deferred
those boundaries. This must be documented, not presented as an end-to-end bounded-memory runner.
Custom sources and the generic loader must work incrementally without the registry.

## Composition and identity

Registry metadata (files, licences, parser) belongs to the built-in benchmark catalog, not the
dataset base. A benchmark can be supplied directly to the runner without a registry entry.
Dataset subclasses must supply a fingerprint: a revision/manifest or deterministic generation
specification can identify a stream without reading it. `FrameDataset` owns frame content hashing;
`CorpusDataset` composes its frame fingerprints. Identity includes schema and ordered values,
independent of loading batches and physical frame chunks. Python `__hash__` is not this contract.
For now the eager benchmark boundary fingerprints its materialized content, including ordinary
iterables; consulting source identity before reading belongs to the later caching redesign.
Source-native ordering is retained. Corpus truncation and evaluation selection are distinct.

No workers, prefetching, automatic function serialization, generic table registry, or framework
dependency is introduced. Dataset authors control I/O and may override iteration and loading.

## Review record

External references: PyTorch 2.14 data API and dataset tutorial, Arrow RecordBatchReader,
ir_datasets independent document/query/judgment iterators, Hugging Face streaming documentation.
These support access/consumption separation, native batches, and explicit replay requirements.

Claude Opus 5 cross-model design review returned challenges and eleven named falsification
attempts. **Rejected with reason:** no DataLoader and eager-only evaluation sources would preserve
today's runner constraints in the extension API and conflict with the owner's goal. **Added
verification:** avoid publishing partial ingestion, preserve ACLs at ingestion boundaries, and
do not turn global entity resolution into independent per-batch resolution. **Rejected with
reason:** hashing batch digests would make content identity depend on batch size. **Confirmed
existing coupling:** gold-derived vocabulary and gold spans in document metadata; redesigning
those algorithm boundaries is deferred, and must not be described as already isolated.

## Acceptance

- Indexed subclasses, streaming subclasses and ordinary generators work with one loader.
- Taking one batch consumes only that batch, with no lookahead; incomplete last batches survive.
- Collation supports custom types and Polars; native batches pass through unchanged.
- Corpus-only, QA-only and extraction sources do not construct irrelevant empty task tables.
- All committed fixture pipelines and extraction tests retain their behavior.
- Custom benchmark composition runs without registering a named dataset.
- Source/tests typecheck, Rust checks, lint, offline tests and strict docs build pass.
