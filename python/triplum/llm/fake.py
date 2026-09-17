"""Deterministic LLM for tests. Default responder echoes a hash of the last user message."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from triplum.llm.protocol import DEFAULT_PARAMS, Completion, Message, Usage, request_hash

Responder = Callable[[list[Message], dict | None], str]


def _default_responder(messages: list[Message], schema: dict | None) -> str:
    last = messages[-1].content
    digest = hashlib.sha256(last.encode()).hexdigest()[:8]
    if schema is not None:
        return json.dumps({"answer": digest})
    return f"fake-answer-{digest}"


def _perturbed(text: str, seed: int, schema: dict | None) -> str:
    """The same answer with a seed-dependent suffix, so a replicate with another seed reads
    differently and a replicate with the same seed reads the same."""
    tag = f"{seed % 997}"
    if schema is not None:
        obj = json.loads(text)
        obj["answer"] = f"{obj.get('answer', '')} {tag}".strip()
        return json.dumps(obj)
    return f"{text} {tag}"


class FakeLLM:
    adapter = "fake"

    def __init__(
        self, responder: Responder | None = None, model: str = "fake-1", perturb: bool = False
    ) -> None:
        self.responder = responder  # None: use the module-level default, resolved at call time
        self.model = model
        # A perturbing fake answers differently per seed, so replicate tests see variance
        # where a real provider would show it; it is seed-sensitive exactly then.
        self.perturb = perturb
        self.seed_sensitive = perturb
        if perturb:
            self.adapter = "fake:perturb"  # its own cache entries: the plain fake must not hit them

    def complete(self, messages, *, schema=None, params=DEFAULT_PARAMS) -> Completion:
        text = (self.responder or _default_responder)(messages, schema)
        if self.perturb and params.seed is not None:
            text = _perturbed(text, params.seed, schema)
        parsed = json.loads(text) if schema is not None else None
        n_in = sum(len(m.content.split()) for m in messages)
        return Completion(
            text=text,
            parsed=parsed,
            usage=Usage(input_tokens=n_in, output_tokens=max(1, len(text.split()))),
            model=self.model,
            request_hash=request_hash(self.adapter, self.model, messages, schema, params),
        )
