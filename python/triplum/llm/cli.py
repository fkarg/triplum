"""Local CLI harness as an LLM: the prompt goes to stdin, the answer comes from stdout.

Must be invoked statelessly (no ambient session, tools or filesystem context) to satisfy the
cache contract (design D6). Preset for Claude Code: `claude -p --output-format json`, answer in
the `result` field. Usage counts are approximated from whitespace tokens because CLIs do not
report them uniformly.
"""

from __future__ import annotations

import json
import subprocess

from triplum.llm.protocol import Completion, GenParams, Message, Usage, request_hash

CLAUDE_PRESET = {"argv": ["claude", "-p", "--output-format", "json"], "json_field": "result"}


def render_prompt(messages: list[Message]) -> str:
    return "\n\n".join(f"[{m.role}]\n{m.content}" for m in messages)


class CliLLM:
    adapter = "cli"

    def __init__(
        self, model: str, argv: list[str], json_field: str | None = None, timeout_s: int = 600
    ) -> None:
        self.model = model
        self.argv = argv
        self.json_field = json_field
        self.timeout_s = timeout_s

    def complete(self, messages, *, schema=None, params=GenParams()) -> Completion:
        prompt = render_prompt(messages)
        if schema is not None:
            prompt += "\n\nRespond with JSON only, matching this schema:\n" + json.dumps(schema)
        proc = subprocess.run(
            self.argv, input=prompt, capture_output=True, text=True, timeout=self.timeout_s, check=True
        )
        text = proc.stdout.strip()
        if self.json_field is not None:
            text = str(json.loads(text)[self.json_field])
        parsed = json.loads(text) if schema is not None else None
        return Completion(
            text=text,
            parsed=parsed,
            usage=Usage(input_tokens=len(prompt.split()), output_tokens=max(1, len(text.split()))),
            model=self.model,
            request_hash=request_hash(self.adapter, self.model, messages, schema, params),
        )
