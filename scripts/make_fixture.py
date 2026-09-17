"""Build the 20-question smoke fixtures from the fetched dataset files.

Keeps the first 20 questions, every chunk they need (gold and, where the dataset ships them, the
candidate distractors recorded in `metadata`), and a deterministic fill of further chunks, so
retrieval on the fixture keeps the gold/distractor structure of the full corpus.
Run: uv run python scripts/make_fixture.py [dataset ...]   (default: every registered dataset)
"""

from __future__ import annotations

import sys

from triplum.eval.datasets import base, registry


def main(names: list[str]) -> None:
    base.FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name in names or registry.names():
        spec = registry.get(name)
        if not spec.fixture:
            print(name, "has no fixture")
            continue
        ds = registry.load(name)
        frames = base.subset(
            base.Frames(ds.questions, ds.documents, ds.grants, ds.chunks, ds.triples)
        )
        path = base.write_fixture(name, frames)
        print(name, frames.questions.height, "questions", frames.chunks.height, "chunks", path.name)


if __name__ == "__main__":
    main(sys.argv[1:])
