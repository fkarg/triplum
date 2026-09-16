"""Frozen configs. `hash()` of a PipelineConfig is part of the run identity (design D8)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from triplum.cache import content_key


@dataclass(frozen=True)
class EmbedderConfig:
    kind: str  # fake | openai | st | fastembed
    model: str = "fake"
    dims: int = 64
    revision: str = ""
    query_prefix: str = ""
    passage_prefix: str = ""
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"


@dataclass(frozen=True)
class LLMConfig:
    kind: str  # fake | openai | cli
    model: str = "fake-1"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 256
    argv: tuple[str, ...] = ()
    json_field: str | None = None


@dataclass(frozen=True)
class RerankerConfig:
    kind: str  # fake | cross_encoder
    model: str = "fake"


@dataclass(frozen=True)
class PipelineConfig:
    name: str  # closed_book | bm25 | dense | hybrid | oracle
    reader: LLMConfig
    top_k: int = 5
    candidates: int = 20
    embedder: EmbedderConfig | None = None
    reranker: RerankerConfig | None = None

    def hash(self) -> str:
        return content_key("pipeline", asdict(self))[:16]


@dataclass(frozen=True)
class RunConfig:
    dataset: str
    pipeline: PipelineConfig
    n: int | None = None
    fixture: bool = False
    judge: LLMConfig | None = None
    principals: tuple[str, ...] = ("public",)
    seed: int = 0
    force: bool = False
    store_path: str | None = None
    runstore_path: str | None = None
    cache_root: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)
