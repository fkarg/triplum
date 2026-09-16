"""One LLM protocol. Adapters implement `complete`; pipelines never import a provider SDK."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from triplum.cache import content_key


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class GenParams:
    temperature: float = 0.0
    max_tokens: int = 1024
    seed: int | None = None


DEFAULT_PARAMS = GenParams()


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    text: str
    parsed: Any | None
    usage: Usage
    model: str
    request_hash: str
    cached: bool = False
    raw: dict = field(default_factory=dict)


def request_payload(
    adapter: str, model: str, messages: list[Message], schema: dict | None, params: GenParams
) -> dict:
    """The full effective request (design D6). Everything that changes the answer is in here."""
    return {
        "adapter": adapter,
        "model": model,
        "messages": [asdict(m) for m in messages],
        "schema": schema,
        "params": asdict(params),
    }


def request_hash(adapter: str, model: str, messages, schema, params) -> str:
    return content_key("llm", request_payload(adapter, model, messages, schema, params))


class LLM(Protocol):
    adapter: str
    model: str

    def complete(
        self,
        messages: list[Message],
        *,
        schema: dict | None = None,
        params: GenParams = DEFAULT_PARAMS,
    ) -> Completion: ...
