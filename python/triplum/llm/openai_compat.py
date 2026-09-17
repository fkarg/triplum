"""OpenAI-compatible chat completions: OpenAI, OpenRouter, vLLM, Ollama, LM Studio, ...

The API key is read by the SDK from the environment; never pass it as a literal.
"""

from __future__ import annotations

import json
import os
from typing import Any

from triplum.llm.protocol import DEFAULT_PARAMS, Completion, GenParams, Message, Usage, request_hash


class OpenAICompatLLM:
    adapter = "openai_compat"
    seed_sensitive = True

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        client: Any | None = None,
        max_parse_retries: int = 1,
    ) -> None:
        self.model = model
        self.max_parse_retries = max_parse_retries
        # The endpoint is part of the effective request (design D6): same model behind a
        # different base_url must not share cache entries.
        self.adapter = f"openai_compat:{base_url or 'default'}"
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env))
        self.client = client

    def _call(self, messages: list[Message], schema: dict | None, params: GenParams):
        kw: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.seed is not None:
            kw["seed"] = params.seed
        if schema is not None:
            kw["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": False},
            }
        return self.client.chat.completions.create(**kw)

    def complete(self, messages, *, schema=None, params=DEFAULT_PARAMS) -> Completion:
        attempts = 0
        while True:
            resp = self._call(messages, schema, params)
            text = resp.choices[0].message.content or ""
            parsed = None
            if schema is not None:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    attempts += 1
                    if attempts <= self.max_parse_retries:
                        messages = [
                            *messages,
                            Message("assistant", text),
                            Message("user", "Return only valid JSON matching the schema."),
                        ]
                        continue
            u = resp.usage
            details = getattr(u, "prompt_tokens_details", None)
            cached_in = getattr(details, "cached_tokens", 0) if details else 0
            return Completion(
                text=text,
                parsed=parsed,
                usage=Usage(
                    input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(u, "completion_tokens", 0) or 0,
                    cached_input_tokens=cached_in or 0,
                ),
                model=getattr(resp, "model", self.model) or self.model,
                request_hash=request_hash(self.adapter, self.model, messages, schema, params),
                raw=resp.model_dump() if hasattr(resp, "model_dump") else {},
            )
