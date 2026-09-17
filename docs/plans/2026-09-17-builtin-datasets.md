# Plan: built-in datasets as lazy, streaming sources

Derived from [`../specs/2026-09-17-builtin-datasets.md`](../specs/2026-09-17-builtin-datasets.md).
Snapshot 2026-09-17. Three commits on local main, each green under the pre-commit gate, the
offline test suite and the strict docs build. Every dataset file is already fetched on the
development machine, so fixtures regenerate from source.

## Commit 1: additive foundations

Nothing existing changes behaviour; the old sources keep working on top.

1. `pyproject.toml`: add `pydantic>=2.13` and `pydantic-settings>=2` to dependencies;
   `uv lock`; rows in `docs/licences.md` (both MIT).
2. `utils/data/dataset.py`: `Take[T]` and `RecordDataset[T]` with tests in
   `tests/test_data_loading.py` (take consumes exactly `n`; fingerprint composes; a record
   dataset's fingerprint changes with any field and not with construction order of equal lists).
3. `data/corpus.py`: `Segment`, `Document`, `content_id`, `chunk_id`. `eval/inputs.py`:
   `Question`, `Triple` next to the two schemas. `datasets/collate.py`: the three collators,
   tested against the schemas and against a document with two segments.
4. `triplum/settings.py`: `Settings` (top level, so `cache.default_root` can read it without
   a cycle; `datasets.files` re-exports it). `datasets/files.py`: `File`, `Files`,
   `manifest_files`. Tests move from `test_datasets.py` (hash mismatch, status states) to
   `tests/test_files.py`; a mirror test rewrites a URL prefix.
5. `datasets/base.py`: `Pinned`, `GoldMappingError`, `utc_us`, `read_jsonl` added beside the
   old helpers, which are deleted in commit 2.

## Commit 2: the swap

1. `bench/inputs.py`: `Benchmark` over datasets, `materialize` through loaders and collators,
   fingerprints from the sources. `eval/inputs.py` loses the two wrappers.
2. Source modules, one class per part plus `ENTRIES`, in this order so the default set is green
   first: `hipporag`, `wiki_multihop`, `reading`, `long_document`, `question_only`,
   `multihoprag`, `ectqa`, `metaqa`, `mquake`, `gatemem`, `longmemeval`, `extraction`,
   `tempo`, `browsecomp_plus`. Each keeps its module docstring's dataset facts. The parquet
   sources (`tempo`, `browsecomp_plus`, `hotpotqa_full`, `twowiki_full`, `conll04`) iterate
   row groups through `pyarrow.parquet.ParquetFile.iter_batches`.
3. `ingest/files.py`: `FolderCorpus`, `FolderQuestions`, `entry(path)`.
4. `datasets/registry.py`: `ENTRIES`, `get`, `names`, `is_folder`, `status`, `fetch`, `load`,
   `load_fixture`, `verify`. `datasets/fixtures.py`: `read`, `write`, `subset`, the gold check.
   `scripts/make_fixture.py` over the new functions; regenerate every fixture; update
   `tests/fixtures/ATTRIBUTION.md` only if a source changed.
5. `bench/cli.py`: `data` overview over entries, `data fetch` unchanged in behaviour,
   `data verify <name>`. `bench/data_view.py` renders entries. `bench/runner.py` passes
   settings through `_load`.
6. Tests: `test_datasets.py` and `test_dataset_parsers.py` iterate classes over small
   source-shaped files through `materialize`; `test_runner_dataset_rules.py` registers entries;
   `test_ingest_files.py` and `test_benchmark_inputs.py` updated for records; a new
   `tests/test_registry_identity.py` asserts constructing and fingerprinting every entry does
   no file read (a settings root that does not exist), that `materialize` rejects a question
   whose gold is not in the corpus and a duplicate document id, and that `Take` pulls exactly
   `n` records.
7. Delete the old helpers, `CorpusDataset`, and the `Spec` machinery.

## Commit 3: documentation

1. `docs/datasets.md` (nav entry after Flow): built-in sources, records, identity, composing
   without the registry, "your own source" with two examples in `docs/examples/` executed by
   `tests/test_docs_examples.py`.
2. `docs/api/utils-data.md`, `docs/api/datasets.md`, `docs/api/data.md`, `docs/api/eval.md`
   render the new modules; `docs/api/index.md` rows for `utils.data`, `datasets`,
   `data.corpus`, `eval`, `bench.inputs`, `ingest.files`; `docs/flow.md` step 1 and the
   implemented list; `docs/benchmarking.md` where it names the corpus hash; the stale manifest
   path in `docs/research/benchmarks.md`.
3. `docs/research/design.md`: D2 and D8 wording for records and source identity; the review
   record entry for this spec. The superseded specs get a one-line pointer at the top.
4. `docs/plans/2026-09-17-stack-walk.md`: layer 0 marked done for the built-in sources.

## Verification per commit

`uv run pytest -m "not model" --durations=10`, `uv run ty check`, `ruff check`,
`ruff format --check`, `cargo check`, `uv run mkdocs build --strict`. Commit 2 additionally
runs the fixture pipelines through the CLI on `hotpotqa --fixture` for `bm25` and `dense`
with fakes, and `bench extract --fixture` on `twowiki`, and compares the summaries to the
numbers in `flow.md`.
