"""Run one pipeline on a committed fixture, then again, then three replicates.

Everything runs offline: the fake reader answers deterministically, the fake judge agrees with
it, and the fixture is twenty MuSiQue questions with their gold passages.
"""

import tempfile
from pathlib import Path

from triplum.bench.bench_view import print_summary, print_variance
from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
from triplum.bench.report import summary, variance
from triplum.bench.runner import run_benchmark, run_experiment
from triplum.bench.runstore import RunStore

root = Path(tempfile.mkdtemp())  # a throwaway cache root; drop this to use ~/.cache/triplum
cfg = RunConfig(
    dataset="musique",
    fixture=True,
    n=5,
    pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")),
    judge=LLMConfig(kind="fake"),
    cache_root=str(root),
)

run_id = run_benchmark(cfg)
assert run_benchmark(cfg) == run_id  # identical configuration: the stored run comes back

with RunStore(root / "runs.db") as rs:
    print_summary(summary(rs, [run_id]))

    # three replicates under derived seeds; replicate 0 is the run above
    ids = run_experiment(cfg.model_copy(update={"replicates": 3}))
    assert ids[0] == run_id
    row = rs.run(ids[1])
    assert row is not None
    print_variance(*variance(rs, row["experiment_id"]))
