import numpy as np
from triplum.cache import Cache
from triplum.embed.cached import CachedEmbedder
from triplum.embed.fake import FakeEmbedder
from triplum.embed.openai_compat import OpenAICompatEmbedder
from triplum.embed.protocol import EmbeddingSpec


def test_spec_hash_is_stable_and_sensitive():
    a = EmbeddingSpec(model="m", revision="r", dims=8)
    b = EmbeddingSpec(model="m", revision="r", dims=8)
    c = EmbeddingSpec(model="m", revision="r", dims=8, query_prefix="query: ")
    assert a.hash() == b.hash() and a.hash() != c.hash() and len(a.hash()) == 16


def test_fake_embedder_shapes_and_determinism():
    e = FakeEmbedder(dims=8)
    q = e.embed_queries(["a", "b"])
    p = e.embed_passages(["a"])
    assert q.shape == (2, 8) and p.shape == (1, 8) and q.dtype == np.float32
    assert np.allclose(np.linalg.norm(q, axis=1), 1.0)
    assert np.allclose(e.embed_queries(["a"])[0], q[0])


def test_fake_embedder_similar_texts_are_closer():
    e = FakeEmbedder(dims=64)
    v = e.embed_passages(
        ["the cat sat on the mat", "the cat sat on a mat", "quarterly revenue grew"]
    )
    assert v[0] @ v[1] > v[0] @ v[2]


def test_cached_embedder_hits_per_text(tmp_path, monkeypatch):
    inner = FakeEmbedder(dims=8)
    calls = []
    orig = inner.embed_passages
    monkeypatch.setattr(
        inner, "embed_passages", lambda texts: (calls.append(list(texts)), orig(texts))[1]
    )
    e = CachedEmbedder(inner, Cache(tmp_path))
    e.embed_passages(["x", "y"])
    e.embed_passages(["y", "z"])
    assert calls == [["x", "y"], ["z"]]


def test_openai_compat_embedder_calls_client():
    class _Item:
        def __init__(self, v):
            self.embedding = v

    class _Resp:
        def __init__(self, n):
            self.data = [_Item([1.0, 0.0]) for _ in range(n)]

    class _Emb:
        def create(self, **kw):
            return _Resp(len(kw["input"]))

    class _Client:
        embeddings = _Emb()

    spec = EmbeddingSpec(
        model="text-embedding-3-large", revision="2026", dims=2, query_prefix="q: "
    )
    e = OpenAICompatEmbedder(spec, client=_Client())
    out = e.embed_queries(["a", "b"])
    assert out.shape == (2, 2) and np.allclose(out[0], [1.0, 0.0])


import importlib.util

import pytest


def test_sentence_transformers_requires_known_dimensions(monkeypatch):
    # Some model modules cannot report dimensions; fail at the adapter boundary with context.
    import sys
    from types import SimpleNamespace

    from triplum.embed.sentence_transformers import SentenceTransformersEmbedder

    model = SimpleNamespace(get_embedding_dimension=lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(
            SentenceTransformer=lambda *args, **kwargs: model,
        ),
    )
    with pytest.raises(ValueError, match="embedding dimensions.*unknown-dims"):
        SentenceTransformersEmbedder.from_model("unknown-dims", device="cpu", revision="pinned")


@pytest.mark.model
@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None, reason="extra not installed"
)
def test_sentence_transformers_adapter_small_model():
    from triplum.embed.sentence_transformers import SentenceTransformersEmbedder

    e = SentenceTransformersEmbedder.from_model(
        "sentence-transformers/all-MiniLM-L6-v2", max_seq_length=128, padding_side="left"
    )
    v = e.embed_passages(["hello world", "hello there"])
    assert v.shape == (2, e.spec.dims) and e.spec.runtime.startswith("sentence-transformers:")
    assert e.spec.max_seq_length == 128 and e.spec.padding_side == "left"
    assert e.spec.revision not in ("", "unknown")
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)


@pytest.mark.model
@pytest.mark.skipif(importlib.util.find_spec("fastembed") is None, reason="extra not installed")
def test_fastembed_adapter_small_model():
    from triplum.embed.fastembed import FastEmbedEmbedder

    e = FastEmbedEmbedder.from_model("BAAI/bge-small-en-v1.5")
    v = e.embed_queries(["hello world"])
    assert v.shape == (1, e.spec.dims) and e.spec.runtime == "onnx"
