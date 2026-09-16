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


def test_store_bound_to_one_corpus(tmp_path):
    from triplum.bench.index import CorpusMismatch

    run_benchmark(_cfg(tmp_path, "bm25", "musique"))
    with pytest.raises(CorpusMismatch):
        run_benchmark(_cfg(tmp_path, "bm25", "twowiki").__class__(
            **{**_cfg(tmp_path, "bm25", "twowiki").__dict__, "store_path": str(tmp_path / "musique.sqlite")}
        ))


def test_same_family_judge_rejected(tmp_path):
    cfg = _cfg(tmp_path, "bm25")
    bad = RunConfig(**{**cfg.__dict__, "judge": LLMConfig(kind="openai", model="gpt-5.6-luna"),
                       "pipeline": PipelineConfig(**{**cfg.pipeline.__dict__, "reader": LLMConfig(kind="openai", model="gpt-5.6-sol")})})
    with pytest.raises(ValueError):
        run_benchmark(bad)


def test_events_reconcile_with_questions(tmp_path):
    rid = run_benchmark(_cfg(tmp_path, "hybrid"))
    rs = RunStore(tmp_path / "runs.db")
    ev = rs.events(rid)
    assert set(ev["stage"].to_list()) >= {"index.documents", "index.embed", "retrieve", "read", "judge"}
    assert ev.filter(ev["stage"] == "judge")["output_tokens"].sum() > 0
    reads = ev.filter(ev["stage"] == "read")
    assert reads["input_tokens"].sum() == rs.questions(rid)["input_tokens"].sum()
