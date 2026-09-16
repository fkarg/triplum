"""Binary correctness judge. The judge model must come from a different family than the reader;
the runner records both ids."""

from __future__ import annotations

from triplum.cache import content_key
from triplum.llm.protocol import DEFAULT_PARAMS, LLM, Completion, GenParams, Message

SYSTEM = (
    "You grade short answers. Given the question, the gold answer(s) and a candidate, "
    "say whether the candidate is correct (same meaning; extra words are fine)."
)
SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}},
    "required": ["correct"],
}


PROMPT_HASH = content_key("judge_prompt", {"system": SYSTEM, "schema": SCHEMA})[:16]


def judge_correct(
    llm: LLM, question: str, golds: list[str], answer: str, params: GenParams = DEFAULT_PARAMS
) -> tuple[bool, Completion]:
    msgs = [
        Message("system", SYSTEM),
        Message("user", f"Question: {question}\nGold: {' | '.join(golds)}\nCandidate: {answer}"),
    ]
    c = llm.complete(msgs, schema=SCHEMA, params=params)
    return bool(isinstance(c.parsed, dict) and c.parsed.get("correct") is True), c
