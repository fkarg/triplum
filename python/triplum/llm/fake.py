"""Deterministic LLM for tests. Default responder echoes a hash of the last user message."""

from __future__ import annotations

import hashlib
import json
from typing import Callable

from triplum.llm.protocol import Completion, GenParams, Message, Usage, request_hash

Responder = Callable[[list[Message], dict | None], str]


def _default_responder(messages: list[Message], schema: dict | None) -> str:
    last = messages[-1].content
    digest = hashlib.sha256(last.encode()).hexdigest()[:8]
    if schema is not None:
        return json.dumps({"answer": digest})
    return f"fake-answer-{digest}"


class FakeLLM:
    adapter = "fake"

    def __init__(self, responder: Responder = _default_responder, model: str = "fake-1") -> None:
        self.responder = responder
        self.model = model

    def complete(self, messages, *, schema=None, params=GenParams()) -> Completion:
        text = self.responder(messages, schema)
        parsed = json.loads(text) if schema is not None else None
        n_in = sum(len(m.content.split()) for m in messages)
        return Completion(
            text=text,
            parsed=parsed,
            usage=Usage(input_tokens=n_in, output_tokens=max(1, len(text.split()))),
            model=self.model,
            request_hash=request_hash(self.adapter, self.model, messages, schema, params),
        )
