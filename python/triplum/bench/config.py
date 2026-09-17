"""Frozen configs. `hash()` of a PipelineConfig is part of the run identity (design D8). The
dump of a config is its identity, so a config is a valid stage argument as it is."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict

from triplum.cache import canonical_json, content_key
from triplum.extract.protocol import ResolverSpec


class Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))

    @classmethod
    def from_json(cls, s: str) -> Self:
        """Inverse of to_json; used by `triplum bench rerun` to replay a stored configuration."""
        return cls.model_validate_json(s)


def replace[C: Config](cfg: C, **updates: object) -> C:
    """A copy with fields replaced, the `dataclasses.replace` the configs used to have."""
    return cfg.model_copy(update=updates)


class EmbedderConfig(Config):
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


class LLMConfig(Config):
    kind: str  # fake | openai | cli
    model: str = "fake-1"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 256
    argv: tuple[str, ...] = ()
    json_field: str | None = None
    perturb: bool = False  # fake only: the answer depends on the seed, for replicate tests


class RerankerConfig(Config):
    kind: str  # fake | cross_encoder
    model: str = "fake"


class PipelineConfig(Config):
    name: str  # a key of triplum.retrieve.pipelines.PIPELINES
    reader: LLMConfig
    top_k: int = 5
    candidates: int = 20
    embedder: EmbedderConfig | None = None
    reranker: RerankerConfig | None = None

    def hash(self) -> str:
        return content_key("pipeline", self.model_dump(mode="json"))[:16]


class ExtractorConfig(Config):
    kind: str = "rules"  # rules | small_model
    model: str = ""  # small_model: the GLiNER model id; rules: the spaCy pipeline
    entity_types: tuple[str, ...] = ()  # small_model: the span vocabulary
    relation_types: tuple[str, ...] = ()  # small_model: the relation vocabulary


class ExtractConfig(Config):
    """One extraction run: build the graph for a dataset with an extractor and a resolver,
    score it against the gold triples. `hash()` of the extractor and resolver parts is in the
    run identity; everything that changes the graph is in the graph identity."""

    dataset: str
    extractor: ExtractorConfig = ExtractorConfig()
    resolver: ResolverSpec = ResolverSpec("none")
    n: int | None = None
    fixture: bool = False
    principals: tuple[str, ...] = ("public",)
    force: bool = False
    store_path: str | None = None
    runstore_path: str | None = None
    cache_root: str | None = None

    def hash(self) -> str:
        return content_key(
            "extract",
            [self.extractor.model_dump(mode="json"), self.model_dump(mode="json")["resolver"]],
        )[:16]


class RunConfig(Config):
    dataset: str
    pipeline: PipelineConfig
    n: int | None = None
    fixture: bool = False
    judge: LLMConfig | None = None
    principals: tuple[str, ...] = ("public",)
    seed: int = 0
    replicates: int = 1
    force: bool = False
    resume: bool = False
    store_path: str | None = None
    runstore_path: str | None = None
    cache_root: str | None = None
