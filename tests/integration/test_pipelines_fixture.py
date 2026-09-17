from dataclasses import replace

import pytest
from triplum.bench.config import (
    EmbedderConfig,
    LLMConfig,
    PipelineConfig,
    RerankerConfig,
    RunConfig,
)
from triplum.bench.inputs import materialize
from triplum.bench.report import summary
from triplum.bench.runner import run_benchmark
from triplum.bench.runstore import RunStore
from triplum.datasets import fixtures, registry
from triplum.retrieve import pipelines

FAKE_READER = LLMConfig(kind="fake")
FAKE_EMB = EmbedderConfig(kind="fake", dims=64)
PIPELINES = pipelines.NAMES


def _cfg(tmp_path, name, dataset="musique", **kw):
    return RunConfig(
        dataset=dataset,
        n=20,
        fixture=True,
        pipeline=PipelineConfig(
            name=name,
            reader=FAKE_READER,
            embedder=FAKE_EMB,
            reranker=RerankerConfig(kind="fake") if pipelines.get(name).needs_reranker else None,
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
    assert s.height == len(PIPELINES) and set(s["pipeline"]) == set(ids)
    by = {r["pipeline"]: r for r in s.iter_rows(named=True)}
    assert by["oracle"]["r5"] == 1.0
    assert by["closed_book"]["r5"] == 0.0 and by["closed_book"]["n_chunks"] == 0.0
    assert by["oracle"]["r5"] >= by["dense"]["r5"] >= by["closed_book"]["r5"]
    assert by["rrf"]["r5"] >= by["closed_book"]["r5"] and by["rrf"]["n_chunks"] > 0
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
        run_benchmark(
            replace(_cfg(tmp_path, "bm25", "twowiki"), store_path=str(tmp_path / "musique.sqlite"))
        )


def test_same_family_judge_rejected(tmp_path):
    cfg = _cfg(tmp_path, "bm25")
    bad = replace(
        cfg,
        judge=LLMConfig(kind="openai", model="gpt-5.6-luna"),
        pipeline=replace(cfg.pipeline, reader=LLMConfig(kind="openai", model="gpt-5.6-sol")),
    )
    with pytest.raises(ValueError):
        run_benchmark(bad)


def test_events_reconcile_with_questions(tmp_path):
    rid = run_benchmark(_cfg(tmp_path, "hybrid"))
    rs = RunStore(tmp_path / "runs.db")
    ev = rs.events(rid)
    assert set(ev["stage"].to_list()) >= {
        "index.documents",
        "index.embed",
        "retrieve",
        "read",
        "judge",
    }
    assert ev.filter(ev["stage"] == "judge")["output_tokens"].sum() > 0
    reads = ev.filter(ev["stage"] == "read")
    assert reads["input_tokens"].sum() == rs.questions(rid)["input_tokens"].sum()


def test_cli_show_and_rerun(tmp_path, capsys):
    from triplum.bench.cli import main

    rid = run_benchmark(_cfg(tmp_path, "bm25"))
    assert main(["bench", "show", rid, "--runstore", str(tmp_path / "runs.db")]) == 0
    shown = capsys.readouterr().out
    assert '"pipeline": "bm25"' in shown and '"identity_hash"' in shown
    assert main(["bench", "rerun", rid, "--runstore", str(tmp_path / "runs.db")]) == 0
    assert capsys.readouterr().out.startswith("reused " + rid)
    assert main(["bench", "rerun", rid, "--force", "--runstore", str(tmp_path / "runs.db")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("new ") and rid not in out.split("\n")[0]


def test_crash_then_resume_completes_same_run(tmp_path, monkeypatch):
    from triplum.llm import fake as fake_mod

    calls = {"n": 0}
    orig = fake_mod._default_responder

    def flaky(msgs, schema):
        calls["n"] += 1
        if calls["n"] == 6:
            raise RuntimeError("simulated provider crash")
        return orig(msgs, schema)

    monkeypatch.setattr(fake_mod, "_default_responder", flaky)
    cfg = _cfg(tmp_path, "bm25")
    cfg = replace(cfg, judge=None)
    with pytest.raises(RuntimeError):
        run_benchmark(cfg)
    rs = RunStore(tmp_path / "runs.db")
    runs = rs.runs()
    assert runs.height == 1 and runs["status"][0] == "failed"
    rid = runs["run_id"][0]
    n_done = rs.questions(rid).height
    assert 0 < n_done < 20
    resumed = run_benchmark(replace(cfg, resume=True))
    assert resumed == rid
    assert rs.questions(rid).height == 20 and rs.runs()["status"][0] == "ok"
    assert calls["n"] == 21  # 5 ok + 1 crash + 15 remaining; completed ones were not re-read


def test_inspect_diff_tail(tmp_path, capsys):
    from triplum.bench.cli import main
    from triplum.bench.inspect import diff_runs, inspect_run, tail_run

    a = run_benchmark(_cfg(tmp_path, "bm25"))
    b = run_benchmark(_cfg(tmp_path, "dense"))
    rs = RunStore(tmp_path / "runs.db")
    view = inspect_run(rs, a)
    assert len(view["questions"]) == 20 and view["store_available"]
    first = view["questions"][0]
    assert first["retrieved"] and first["retrieved"][0]["text"] is not None
    assert any(e["stage"] == "read" for e in first["events"])
    d = diff_runs(rs, a, b)
    assert d["config_diff"]["pipeline.name"] == ("bm25", "dense") and not d["only_in_a"]
    assert d["per_question"].height == 20 and "d_r5" in d["per_question"].columns
    t = tail_run(rs, a)
    assert t["done"] == 20 and t["total"] == 20 and t["status"] == "ok"
    db = str(tmp_path / "runs.db")
    assert main(["bench", "inspect", a, "--question", first["question_id"], "--runstore", db]) == 0
    assert first["question_id"] in capsys.readouterr().out
    assert main(["bench", "diff", a, b, "--runstore", db]) == 0
    assert "pipeline.name" in capsys.readouterr().out
    assert main(["bench", "tail", a, "--once", "--runstore", db]) == 0
    assert "20/20" in capsys.readouterr().out


OTHER_FIXTURES = [
    name
    for name, entry in registry.ENTRIES.items()
    if entry.fixture and not entry.default and not entry.needs and fixtures.path(name).exists()
]


@pytest.mark.parametrize("dataset", OTHER_FIXTURES)
def test_registered_fixtures_run(tmp_path, dataset):
    """Every runnable fixture goes through bm25 and oracle (closed_book when there is no corpus);
    extraction-only datasets are refused."""
    ds = materialize(registry.load_fixture(dataset))
    if ds.qa is None:
        with pytest.raises(ValueError, match="no questions"):
            run_benchmark(_cfg(tmp_path, "bm25", dataset))
        return
    pipelines = ("closed_book",) if ds.corpus.chunks.height == 0 else ("bm25", "oracle")
    for name in pipelines:
        run_benchmark(_cfg(tmp_path, name, dataset))
    by = {r["pipeline"]: r for r in summary(RunStore(tmp_path / "runs.db")).iter_rows(named=True)}
    assert set(by) == set(pipelines)
    assert ds.qa is not None
    if "oracle" in by and ds.qa["answerable"].any():
        assert (
            by["oracle"]["r5"] >= by["bm25"]["r5"] > 0
        )  # some questions have more than 5 gold chunks
