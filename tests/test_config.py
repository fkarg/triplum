from triplum.bench import factories
from triplum.bench.config import (
    EmbedderConfig,
    LLMConfig,
    PipelineConfig,
    RerankerConfig,
    RunConfig,
)
from triplum.embed.fake import FakeEmbedder
from triplum.llm.cached import CachedLLM


def test_config_hash_is_stable_and_sensitive():
    emb = EmbedderConfig(kind="fake", dims=32)
    a = PipelineConfig(name="dense", embedder=emb, reader=LLMConfig(kind="fake"))
    b = PipelineConfig(name="dense", embedder=emb, reader=LLMConfig(kind="fake"))
    c = PipelineConfig(name="dense", top_k=3, embedder=emb, reader=LLMConfig(kind="fake"))
    assert a.hash() == b.hash() != c.hash()


def test_run_config_roundtrips_json():
    rc = RunConfig(
        dataset="musique",
        n=20,
        fixture=True,
        pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")),
        judge=LLMConfig(kind="cli", argv=("claude", "-p"), json_field="result"),
    )
    assert RunConfig.from_json(rc.to_json()) == rc


def test_factories_build_fakes(tmp_path):
    e = factories.make_embedder(EmbedderConfig(kind="fake", dims=16), cache_root=tmp_path)
    assert isinstance(e.inner, FakeEmbedder) and e.spec.dims == 16
    llm = factories.make_llm(LLMConfig(kind="fake"), cache_root=tmp_path)
    assert isinstance(llm, CachedLLM)
    assert factories.make_reranker(None) is None
    rr = factories.make_reranker(RerankerConfig(kind="fake"), cache_root=tmp_path)
    assert rr.score("a b", ["a b", "c"]).shape == (2,) and rr.calls == 2
    rr.score("a b", ["a b"])
    assert rr.calls == 2
    assert factories.model_family("gpt-5.6-luna") == "gpt"
    assert factories.model_family("google/gemma-4-31B-it") == "gemma"
    assert factories.model_family("gpt-5.6-luna") != factories.model_family("claude-opus-5")


def test_cli_run_records_the_flags_it_was_given(tmp_path):
    from triplum.bench.cli import main
    from triplum.bench.runstore import RunStore

    db = tmp_path / "runs.db"
    rc = main(
        [
            "bench",
            "run",
            "--pipeline",
            "dense",
            "--dataset",
            "musique",
            "--n",
            "5",
            "--fixture",
            "--reader",
            "fake",
            "--embedder",
            "fake",
            "--judge",
            "fake",
            "--top-k",
            "3",
            "--cache-root",
            str(tmp_path),
            "--runstore",
            str(db),
        ]
    )
    assert rc == 0
    rs = RunStore(db)
    (run_id,) = [r["run_id"] for r in rs.runs().iter_rows(named=True)]
    row = rs.run(run_id)
    assert row is not None
    cfg = RunConfig.from_json(row["config_json"])
    assert cfg.pipeline.name == "dense" and cfg.dataset == "musique" and cfg.n == 5 and cfg.fixture
    assert cfg.pipeline.embedder is not None
    assert cfg.pipeline.embedder.kind == "fake" and cfg.pipeline.top_k == 3
    assert cfg.judge is not None and cfg.cache_root == str(tmp_path)


def test_cli_embedder_shorthand():
    from triplum.bench.cli import _embedder

    assert _embedder("st:BAAI/bge-large-en-v1.5") == EmbedderConfig(
        kind="st", model="BAAI/bge-large-en-v1.5"
    )
    assert _embedder("openai:text-embedding-3-large").dims == 3072
    assert _embedder({"kind": "fake", "dims": 8}).dims == 8


def test_cli_data_lists_registered_datasets_without_fetching(tmp_path, monkeypatch, capsys):
    from triplum.bench.cli import main

    monkeypatch.setenv("TRIPLUM_DATA", str(tmp_path))
    assert main(["data"]) == 0
    out = capsys.readouterr().out
    assert "hotpotqa" in out and "musique" in out and "twowiki" in out
    assert "Dataset" in out and "State" in out and "Family" in out and "Flags" in out
    assert "not downloaded" in out and "default" in out and "multihop" in out
    assert "triplum data fetch --dataset <name>" in out
    assert "triplum data --help" in out
    assert "Usage:" not in out and "Commands" not in out
    assert not (tmp_path / "hipporag").exists()


def test_sweep_continues_past_failed_spec(tmp_path, capsys):
    import json

    from triplum.bench.cli import main

    specs = tmp_path / "emb.json"
    specs.write_text(
        json.dumps(
            [{"kind": "fake", "dims": 8}, {"kind": "nonexistent"}, {"kind": "fake", "dims": 16}]
        )
    )
    rc = main(
        [
            "bench",
            "sweep",
            "--dataset",
            "musique",
            "--n",
            "5",
            "--fixture",
            "--reader",
            "fake",
            "--embedders",
            str(specs),
            "--cache-root",
            str(tmp_path),
            "--runstore",
            str(tmp_path / "runs.db"),
        ]
    )
    out = capsys.readouterr()
    assert rc == 1 and "FAILED" in out.err and out.out.count("dense") == 2


def test_config_hashes_survived_the_move_to_pydantic():
    """Extraction literals captured from the dataclass configs on 2026-09-18: those identities
    did not move with the config type. The pipeline literals are from the pydantic configs:
    the pipeline hash moved once because `LLMConfig` gained `perturb`, and is pinned here."""
    from triplum.bench.config import ExtractConfig, ExtractorConfig
    from triplum.extract.protocol import ResolverSpec

    assert PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")).hash() == "8b9a61d024a0a76e"
    dense = PipelineConfig(
        name="dense",
        reader=LLMConfig(kind="fake"),
        embedder=EmbedderConfig(kind="fake", dims=32),
        top_k=3,
    )
    assert dense.hash() == "3460d900f43b1598"
    assert ExtractConfig(dataset="x").hash() == "04b4c9eb4282f2bf"
    x = ExtractConfig(
        dataset="x",
        extractor=ExtractorConfig(kind="small_model", entity_types=("A", "B")),
        resolver=ResolverSpec("fuzzy", 0.9),
    )
    assert x.hash() == "d8572cd4aa15751e"
    assert ExtractConfig.from_json(x.to_json()) == x
    assert x.model_copy(update={"n": 3}).n == 3 and x.n is None


def test_adapters_declare_seed_sensitivity(tmp_path):
    from triplum.llm.protocol import GenParams, Message

    plain = factories.make_llm(LLMConfig(kind="fake"), cache_root=tmp_path)
    shaky = factories.make_llm(LLMConfig(kind="fake", perturb=True), cache_root=tmp_path)
    assert plain.seed_sensitive is False and shaky.seed_sensitive is True
    msgs = [Message(role="user", content="What is 2+2?")]
    a = shaky.complete(msgs, params=GenParams(seed=1)).text
    b = shaky.complete(msgs, params=GenParams(seed=2)).text
    c = shaky.complete(msgs, params=GenParams(seed=1)).text
    assert a != b and a == c
    assert (
        plain.complete(msgs, params=GenParams(seed=1)).text
        == plain.complete(msgs, params=GenParams(seed=2)).text
    )
    assert factories.make_embedder(EmbedderConfig(kind="fake"), tmp_path).seed_sensitive is False
    assert factories.make_reranker(RerankerConfig(kind="fake"), tmp_path).seed_sensitive is False
