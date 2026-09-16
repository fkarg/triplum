"""Frozen configs. `hash()` of a PipelineConfig is part of the run identity (design D8)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from triplum.cache import content_key


@dataclass(frozen=True)
class EmbedderConfig:
    kind: str  # fake | openai | st | fastembed
    model: str = "fake"
    dims: int = 64
    revision: str = ""
    query_template: str = ""  # "Instruct: {instruction}\nQuery:" or a literal prefix
    passage_prefix: str = ""
    instruction: str = ""
    max_seq_length: int | None = None
    padding_side: str = ""
    trust_remote_code: bool = False
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
    resume: bool = False
    store_path: str | None = None
    runstore_path: str | None = None
    cache_root: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> RunConfig:
        """Inverse of to_json; used by `triplum bench rerun` to replay a stored configuration."""
        return _from_dict(cls, json.loads(s))


_NESTED = {
    "pipeline": PipelineConfig,
    "reader": LLMConfig,
    "judge": LLMConfig,
    "embedder": EmbedderConfig,
    "reranker": RerankerConfig,
}
_TUPLES = {"principals", "argv"}


def _from_dict(cls, d):
    if d is None:
        return None
    kw = {}
    for f in fields(cls):
        if f.name not in d:
            continue
        v = d[f.name]
        if f.name in _NESTED:
            v = _from_dict(_NESTED[f.name], v)
        elif f.name in _TUPLES and v is not None:
            v = tuple(v)
        kw[f.name] = v
    return cls(**kw)
