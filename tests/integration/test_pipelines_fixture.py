import pytest
from triplum.bench.config import (
    EmbedderConfig,
    LLMConfig,
    PipelineConfig,
    RerankerConfig,
    RunConfig,
)
from triplum.bench.report import summary
from triplum.bench.runner import run_benchmark
from triplum.bench.runstore import RunStore

FAKE_READER = LLMConfig(kind="fake")
FAKE_EMB = EmbedderConfig(kind="fake", dims=64)
PIPELINES = ("closed_book", "bm25", "dense", "hybrid", "oracle")


def _cfg(tmp_path, name, dataset="musique", **kw):
    return RunConfig(
        dataset=dataset,
        n=20,
        fixture=True,
        pipeline=PipelineConfig(
            name=name,
            reader=FAKE_READER,
            embedder=FAKE_EMB,
            reranker=RerankerConfig(kind="fake") if name == "hybrid" else None,
            **kw,
        ),
        judge=LLMConfig(kind="fake", model="judge-fake"),
        store_path=str(tmp_path / f"{dataset}.sqlite"),
        runstore_path=str(tmp_path / "runs.db"),
        cache_root=str(tmp_path / "cache"),
    )


@pytest.mark.parametrize("dataset", ["hotpotqa", "musique", "twowiki"])
def test_all_baselines_run_on_fixture(tmp_path, dataset):
    ids = {name: run_benchmark(_cfg(tmp_path, name, dataset)) for name in PIPELINES}
    rs = RunStore(tmp_path / "runs.db")
    s = summary(rs).sort("pipeline")
    assert s.height == 5 and set(s["pipeline"]) == set(ids)
    by = {r["pipeline"]: r for r in s.iter_rows(named=True)}
    assert by["oracle"]["r5"] == 1.0
    assert by["closed_book"]["r5"] == 0.0 and by["closed_book"]["n_passages"] == 0.0
    assert by["oracle"]["r5"] >= by["dense"]["r5"] >= by["closed_book"]["r5"]
    for r in by.values():
        assert r["n"] == 20 and r["indexing_s"] >= 0 and r["latency_s"] >= 0
    assert rs.questions(ids["dense"]).height == 20


def test_identical_run_is_a_lookup(tmp_path):
    a = run_benchmark(_cfg(tmp_path, "bm25"))
    b = run_benchmark(_cfg(tmp_path, "bm25"))
    assert a == b
    c = run_benchmark(_cfg(tmp_path, "bm25", top_k=3))
    assert c != a
