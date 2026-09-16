import importlib.util

import pytest

from triplum.rerank.fake import FakeReranker
from triplum.rerank.protocol import RerankSpec


def test_rerank_spec_hash():
    a = RerankSpec(model="m", revision="r")
    assert a.hash() == RerankSpec(model="m", revision="r").hash()


def test_fake_reranker_prefers_overlap():
    r = FakeReranker()
    s = r.score("cat on mat", ["the cat sat on the mat", "revenue grew"])
    assert s.shape == (2,) and s[0] > s[1]


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None, reason="extra not installed"
)
def test_cross_encoder_small_model():
    from triplum.rerank.cross_encoder import CrossEncoderReranker

    r = CrossEncoderReranker.from_model("cross-encoder/ms-marco-MiniLM-L-6-v2")
    s = r.score(
        "what is the capital of France", ["Paris is the capital of France.", "Bananas are yellow."]
    )
    assert s[0] > s[1]
