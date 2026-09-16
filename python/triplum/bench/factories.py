"""Build model objects from configs, wrapped in the disk cache. API keys stay in the environment."""

from __future__ import annotations

from pathlib import Path

from triplum.bench.config import EmbedderConfig, LLMConfig, RerankerConfig
from triplum.cache import Cache
from triplum.embed.cached import CachedEmbedder
from triplum.embed.fake import FakeEmbedder
from triplum.embed.protocol import EmbeddingSpec
from triplum.llm.cached import CachedLLM
from triplum.llm.fake import FakeLLM
from triplum.llm.protocol import GenParams


def make_embedder(cfg: EmbedderConfig, cache_root: Path | str | None):
    cache = Cache(cache_root)
    if cfg.kind == "fake":
        return CachedEmbedder(FakeEmbedder(dims=cfg.dims), cache)
    if cfg.kind == "openai":
        from triplum.embed.openai_compat import OpenAICompatEmbedder

        spec = EmbeddingSpec(
            model=cfg.model,
            revision=cfg.revision or "api",
            dims=cfg.dims,
            query_prefix=cfg.query_prefix,
            passage_prefix=cfg.passage_prefix,
            runtime="api",
        )
        return CachedEmbedder(
            OpenAICompatEmbedder(spec, base_url=cfg.base_url, api_key_env=cfg.api_key_env), cache
        )
    if cfg.kind == "st":
        from triplum.embed.sentence_transformers import SentenceTransformersEmbedder

        return CachedEmbedder(
            SentenceTransformersEmbedder.from_model(
                cfg.model, query_prefix=cfg.query_prefix, passage_prefix=cfg.passage_prefix
            ),
            cache,
        )
    if cfg.kind == "fastembed":
        from triplum.embed.fastembed import FastEmbedEmbedder

        return CachedEmbedder(
            FastEmbedEmbedder.from_model(
                cfg.model, query_prefix=cfg.query_prefix, passage_prefix=cfg.passage_prefix
            ),
            cache,
        )
    raise ValueError(f"unknown embedder kind {cfg.kind}")


def make_llm(cfg: LLMConfig, cache_root: Path | str | None):
    cache = Cache(cache_root)
    if cfg.kind == "fake":
        return CachedLLM(FakeLLM(model=cfg.model), cache)
    if cfg.kind == "openai":
        from triplum.llm.openai_compat import OpenAICompatLLM

        return CachedLLM(
            OpenAICompatLLM(cfg.model, base_url=cfg.base_url, api_key_env=cfg.api_key_env), cache
        )
    if cfg.kind == "cli":
        from triplum.llm.cli import CliLLM

        return CachedLLM(CliLLM(cfg.model, list(cfg.argv), json_field=cfg.json_field), cache)
    raise ValueError(f"unknown llm kind {cfg.kind}")


def gen_params(cfg: LLMConfig) -> GenParams:
    return GenParams(temperature=cfg.temperature, max_tokens=cfg.max_tokens)


def make_reranker(cfg: RerankerConfig | None):
    if cfg is None:
        return None
    if cfg.kind == "fake":
        from triplum.rerank.fake import FakeReranker

        return FakeReranker()
    if cfg.kind == "cross_encoder":
        from triplum.rerank.cross_encoder import CrossEncoderReranker

        return CrossEncoderReranker.from_model(cfg.model)
    raise ValueError(f"unknown reranker kind {cfg.kind}")
