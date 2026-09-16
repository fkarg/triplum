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
        dataset="musique", n=20, fixture=True,
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


def test_cli_builds_run_config(tmp_path):
    from triplum.bench.cli import build_run_config, parse_args

    ns = parse_args([
        "bench", "run", "--pipeline", "dense", "--dataset", "musique", "--n", "20", "--fixture",
        "--reader", "fake", "--embedder", "fake", "--judge", "fake", "--cache-root", str(tmp_path),
    ])
    rc = build_run_config(ns)
    assert rc.pipeline.name == "dense" and rc.n == 20 and rc.fixture
    assert rc.pipeline.embedder.kind == "fake"
    assert rc.judge is not None and rc.cache_root == str(tmp_path)


def test_cli_sweep_reads_embedder_specs(tmp_path):
    import json

    from triplum.bench.cli import build_run_config, parse_args

    specs = tmp_path / "emb.json"
    specs.write_text('[{"kind": "fake", "dims": 8}, {"kind": "fake", "dims": 16}]')
    ns = parse_args([
        "bench", "sweep", "--dataset", "musique", "--fixture", "--reader", "fake",
        "--embedders", str(specs), "--cache-root", str(tmp_path),
    ])
    cfgs = [build_run_config(ns, embedder=e) for e in json.loads(specs.read_text())]
    assert [c.pipeline.embedder.dims for c in cfgs] == [8, 16]
    assert all(c.pipeline.name == "dense" for c in cfgs)
