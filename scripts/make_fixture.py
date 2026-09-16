"""Build the 20-question smoke fixtures from the fetched HippoRAG files.

Keeps the first 20 questions and every corpus passage that appears in their candidate contexts,
so retrieval on the fixture has the same gold/distractor structure as the full corpus.
Run: uv run python scripts/make_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

from triplum.eval.datasets import hipporag as hr

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
N = 20


def candidate_keys(name: str, q: dict) -> set[tuple]:
    if name == "musique":
        return {(p["title"], p["paragraph_text"]) for p in q["paragraphs"]}
    return {(t,) for t, _ in q["context"]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in hr.FILES:
        qp, cp = hr.fetch(name)
        questions = json.loads(qp.read_text())[:N]
        corpus = json.loads(cp.read_text())
        keep = set().union(*(candidate_keys(name, q) for q in questions))
        sub = [r for r in corpus if hr.gold_key(name, r["title"], r["text"]) in keep]
        (OUT / f"{name}_questions.json").write_text(json.dumps(questions, ensure_ascii=False))
        (OUT / f"{name}_corpus.json").write_text(json.dumps(sub, ensure_ascii=False))
        print(name, len(questions), "questions", len(sub), "passages")


if __name__ == "__main__":
    main()
