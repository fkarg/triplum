"""Build model objects from configs, wrapped in the disk cache. API keys stay in the environment."""

from __future__ import annotations

from pathlib import Path

from triplum.bench.config import EmbedderConfig, ExtractorConfig, LLMConfig, RerankerConfig
from triplum.cache import Cache
from triplum.embed.cached import CachedEmbedder
from triplum.embed.fake import FakeEmbedder
from triplum.embed.protocol import EmbeddingSpec, render_query_prefix
from triplum.extract.cached import CachedExtractor
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
            query_prefix=render_query_prefix(cfg.query_template, cfg.instruction),
            passage_prefix=cfg.passage_prefix,
            runtime="api",
            instruction=cfg.instruction,
        )
        return CachedEmbedder(
            OpenAICompatEmbedder(spec, base_url=cfg.base_url, api_key_env=cfg.api_key_env), cache
        )
    if cfg.kind == "st":
        from triplum.embed.sentence_transformers import SentenceTransformersEmbedder

        return CachedEmbedder(
            SentenceTransformersEmbedder.from_model(
                cfg.model,
                query_template=cfg.query_template,
                passage_prefix=cfg.passage_prefix,
                instruction=cfg.instruction,
                max_seq_length=cfg.max_seq_length,
                padding_side=cfg.padding_side,
                trust_remote_code=cfg.trust_remote_code,
                revision=cfg.revision or None,
            ),
            cache,
        )
    if cfg.kind == "fastembed":
        from triplum.embed.fastembed import FastEmbedEmbedder

        return CachedEmbedder(
            FastEmbedEmbedder.from_model(
                cfg.model,
                query_prefix=render_query_prefix(cfg.query_template, cfg.instruction),
                passage_prefix=cfg.passage_prefix,
            ),
            cache,
        )
    raise ValueError(f"unknown embedder kind {cfg.kind}")


def make_llm(cfg: LLMConfig, cache_root: Path | str | None):
    cache = Cache(cache_root)
    if cfg.kind == "fake":
        return CachedLLM(FakeLLM(model=cfg.model, perturb=cfg.perturb), cache)
    if cfg.kind == "openai":
        from triplum.llm.openai_compat import OpenAICompatLLM

        return CachedLLM(
            OpenAICompatLLM(cfg.model, base_url=cfg.base_url, api_key_env=cfg.api_key_env), cache
        )
    if cfg.kind == "cli":
        from triplum.llm.cli import CliLLM

        return CachedLLM(CliLLM(cfg.model, list(cfg.argv), json_field=cfg.json_field), cache)
    raise ValueError(f"unknown llm kind {cfg.kind}")


def gen_params(cfg: LLMConfig, seed: int | None = None) -> GenParams:
    """The seed is part of the effective request, so it reaches the provider and the cache key."""
    return GenParams(temperature=cfg.temperature, max_tokens=cfg.max_tokens, seed=seed)


def make_reranker(cfg: RerankerConfig | None, cache_root: Path | str | None = None):
    if cfg is None:
        return None
    from triplum.rerank.cached import CachedReranker

    if cfg.kind == "fake":
        from triplum.rerank.fake import FakeReranker

        return CachedReranker(FakeReranker(), Cache(cache_root))
    if cfg.kind == "cross_encoder":
        from triplum.rerank.cross_encoder import CrossEncoderReranker

        return CachedReranker(CrossEncoderReranker.from_model(cfg.model), Cache(cache_root))
    raise ValueError(f"unknown reranker kind {cfg.kind}")


FAMILIES = (
    "gpt",
    "o1",
    "o3",
    "o4",
    "claude",
    "gemini",
    "gemma",
    "muse",
    "llama",
    "qwen",
    "mistral",
    "deepseek",
)


def model_family(model: str) -> str:
    m = model.lower()
    for fam in FAMILIES:
        if fam in m:
            return fam
    return m.split("/")[-1].split("-")[0]


def make_extractor(cfg: ExtractorConfig, cache_root: Path | str | None) -> CachedExtractor:
    cache = Cache(cache_root)
    if cfg.kind == "rules":
        from triplum.extract.rules import MODEL, RulesExtractor

        return CachedExtractor(RulesExtractor(cfg.model or MODEL), cache)
    if cfg.kind == "small_model":
        from triplum.extract.small_model import SmallModelExtractor

        return CachedExtractor(
            SmallModelExtractor(
                cfg.model or None,
                entity_types=list(cfg.entity_types),
                relation_types=list(cfg.relation_types),
            ),
            cache,
        )
    raise ValueError(f"unknown extractor kind {cfg.kind!r}")
