from triplum.bench import factories
from triplum.bench.config import EmbedderConfig, LLMConfig, PipelineConfig, RunConfig
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
    )
    assert RunConfig.from_json(rc.to_json()) == rc


def test_factories_build_fakes(tmp_path):
    e = factories.make_embedder(EmbedderConfig(kind="fake", dims=16), cache_root=tmp_path)
    assert isinstance(e.inner, FakeEmbedder) and e.spec.dims == 16
    llm = factories.make_llm(LLMConfig(kind="fake"), cache_root=tmp_path)
    assert isinstance(llm, CachedLLM)
    assert factories.make_reranker(None) is None
