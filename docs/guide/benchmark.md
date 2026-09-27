# Run a baseline benchmark

Run the BM25 baseline on one question from the committed MuSiQue fixture. The fake reader keeps
the example offline:

```python
from tempfile import TemporaryDirectory

from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
from triplum.bench.report import format_summary, summary
from triplum.bench.runner import run_benchmark, runstore_path
from triplum.bench.runstore import RunStore

with TemporaryDirectory() as directory:
    config = RunConfig(
        dataset="musique",
        fixture=True,
        n=1,
        pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")),
        cache_root=directory,
    )
    run_id = run_benchmark(config)
    assert run_benchmark(config) == run_id
    with RunStore(runstore_path(config)) as runs:
        result = summary(runs, [run_id])
        assert result["n"][0] == 1
        print(format_summary(result))
```

`dataset` chooses the source; `fixture=True` uses committed data instead of downloading it.
`n=1` selects one question. The pipeline chooses lexical retrieval and a fake reader.
`cache_root` keeps this example's store and run record in a temporary directory. The second
call finds the completed run with the same identity. The report shows answer and retrieval
metrics, indexing time, cost and cache counts. Here the fake reader only exercises the workflow;
its answer metrics are not a measure of model quality. To compare pipelines, keep the reader and
the embedder (where used) fixed across runs.

For a benchmark built from your own records, run
[`examples/your_own_data.py`](https://github.com/fkarg/triplum/blob/main/examples/your_own_data.py). The [benchmarking guide](../benchmarking.md)
explains run identity and caching.
