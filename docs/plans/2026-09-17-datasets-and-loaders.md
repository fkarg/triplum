# Dataset and Loader Implementation Plan

> Execute inline; delegate exploration and review only, never code writing. The owner explicitly
> authorized local main and periodic commits. Use test-driven-development and writing-tests.

**Goal:** Replace the universal benchmark dataset with extensible typed datasets/loaders and
separate corpus/evaluation sources.

**Architecture:** Generic access and batching live in `utils/data/dataset.py` and
`utils/data/loader.py`. Built-in sources move from `eval/datasets` to `datasets`.
Built-in parsers return a benchmark composition of corpus and task sources. Existing whole-frame
algorithms consume explicit materialized task inputs in `bench/inputs.py`.

**Tech stack:** Python 3.12 generics, existing Polars/Arrow, pytest; no new dependencies.

## 1. Generic access and loading

- [x] Add tests in `tests/test_data_loading.py` for indexed and streaming subclasses, generators,
  bounded consumption, final partial batch, custom collation, pass-through, invalid batch size.
  Example: `next(iter(DataLoader(count(), batch_size=3))) == [0, 1, 2]`.
- [x] Run `uv run --frozen pytest tests/test_data_loading.py` and observe missing API failure.
- [x] Implement `Dataset[T]`, `IterableDataset[T]`, `DataLoader[T, B]`; export from `triplum.utils.data`.
- [x] Run focused tests and `uv run --frozen ty check`; update data API docs and commit.

## 2. Replace built-in composition

- [x] Add corpus/QA/extraction composition tests, including a QA-only source with no corpus and a
  corpus source with no evaluation targets. Use existing fixture tests as behavioral regression.
- [x] Introduce `CorpusBatch`, task-specific evaluation inputs and benchmark composition.
  Replace `Frames(...)` parser construction with explicit corpus/QA/extraction construction in
  all `eval/datasets/*.py` parsers and `ingest/files.py`; remove old Dataset and Frames.
- [x] Update fixtures to task-owned structure and fixture helper/subset/script code.
- [x] Add `bench/inputs.py` explicit materialization and content hashing; update runner/index
  consumers and tests. Allow direct benchmark input to run_benchmark/run_extraction.
- [x] Verify fixture identity, parser semantics, QA and extraction workflows.

## 3. Documentation, review, final checks

- [x] Add a runnable custom streaming dataset + loader example, explain materialization boundaries,
  and update README, design D2/D8, docs/flow.md, docs/api/index.md and data API references.
- [x] Run `uv run --frozen pytest -m 'not model' --cov --cov-branch`, `uv run --frozen ty check`,
  `cargo check`, Ruff checks, and `uv run --frozen mkdocs build --strict`.
- [x] Fresh-context review; cross-model follow-up unavailable (expired OAuth), so use the
  fresh-context fallback. Fix verified defects, record outcomes in design.md and rerun checks.
  No push/PR requested.

## Verification outcome

294 offline tests passed, three real-model tests deselected; branch-inclusive coverage 93%.
Typechecking, Ruff and strict MkDocs passed. Cargo passed with `PYO3_PYTHON` set to the project's
Python (the shell default is too old). Existing SQLite resource/Polars deprecation warnings remain.
Owner follow-up requires `fingerprint()` on both dataset base classes; frame hashing preserves
nanoseconds and categorical values, independent of batching and physical chunks. Fresh-context
fallback review independently verified those cases and ran 62 focused tests without failures.
