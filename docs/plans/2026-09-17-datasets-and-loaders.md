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

- [ ] Add tests in `tests/test_data_loading.py` for indexed and streaming subclasses, generators,
  bounded consumption, final partial batch, custom collation, pass-through, invalid batch size.
  Example: `next(iter(DataLoader(count(), batch_size=3))) == [0, 1, 2]`.
- [ ] Run `uv run --frozen pytest tests/test_data_loading.py` and observe missing API failure.
- [x] Implement `Dataset[T]`, `IterableDataset[T]`, `DataLoader[T, B]`; export from `triplum.utils.data`.
- [ ] Run focused tests and `uv run --frozen ty check`; update data API docs and commit.

## 2. Replace built-in composition

- [ ] Add corpus/QA/extraction composition tests, including a QA-only source with no corpus and a
  corpus source with no evaluation targets. Use existing fixture tests as behavioral regression.
- [ ] Introduce `CorpusBatch`, task-specific evaluation inputs and benchmark composition.
  Replace `Frames(...)` parser construction with explicit corpus/QA/extraction construction in
  all `eval/datasets/*.py` parsers and `ingest/files.py`; remove old Dataset and Frames.
- [ ] Update fixtures to task-owned structure and fixture helper/subset/script code.
- [ ] Add `bench/inputs.py` explicit materialization and content hashing; update runner/index
  consumers and tests. Allow direct benchmark input to run_benchmark/run_extraction.
- [ ] Verify fixture identity, parser semantics, QA and extraction workflows. Commit.

## 3. Documentation, review, final checks

- [ ] Add a runnable custom streaming dataset + loader example, explain materialization boundaries,
  and update README, design D2/D8, docs/flow.md, docs/api/index.md and data API references.
- [ ] Run `uv run --frozen pytest -m 'not model' --cov --cov-branch`, `uv run --frozen ty check`,
  `cargo check`, Ruff checks, and `uv run --frozen mkdocs build --strict`.
- [ ] Fresh-context review and cross-model diff review; fix verified in-scope defects, record
  peer outcomes in design.md, rerun affected checks and commit. No push/PR requested.
