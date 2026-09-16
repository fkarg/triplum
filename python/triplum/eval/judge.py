"""Binary correctness judge. The judge model must come from a different family than the reader;
the runner records both ids."""

from __future__ import annotations

from triplum.llm.protocol import LLM, Message

PROMPT_VERSION = "judge-v1"
SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}},
    "required": ["correct"],
}


def judge_correct(llm: LLM, question: str, golds: list[str], answer: str) -> bool:
    msgs = [
        Message(
            "system",
            "You grade short answers. Given the question, the gold answer(s) and a candidate, "
            "say whether the candidate is correct (same meaning; extra words are fine).",
        ),
        Message("user", f"Question: {question}\nGold: {' | '.join(golds)}\nCandidate: {answer}"),
    ]
    c = llm.complete(msgs, schema=SCHEMA)
    return bool(isinstance(c.parsed, dict) and c.parsed.get("correct") is True)
