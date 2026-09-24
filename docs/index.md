# triplum

Triplum is a Python library for comparing document search and knowledge graph techniques on
benchmarks. It includes data sources, a viewer-aware store, retrieval pipelines, and run records.

## Try a baseline

From a clone, run the committed fixture with a fake reader:

```console
uv sync --all-extras
uv run triplum bench run --pipeline bm25 --dataset musique --n 20 --fixture --reader fake
uv run triplum bench report
```

This runs the BM25 question-answering baseline and shows stored results. The fake reader keeps
the example local and reproducible.

## Find your way

- [Learn](guide/index.md) introduces documents, sources, batches, frames, and viewers one at a
  time.
- [Datasets](datasets.md) shows the available inputs and how to supply your own.
- [Benchmark runs](flow.md) follows a run through the implemented pipeline.
- [Benchmark caching](benchmarking.md) explains run identity, reuse, and replay.
- [API reference](api/index.md) maps modules to importable interfaces.
- [Design record](research/design.md) holds architectural decisions and open questions.

The [research notes](research/README.md), [licence ledger](licences.md), and
[release instructions](releasing.md) cover work around the library.
