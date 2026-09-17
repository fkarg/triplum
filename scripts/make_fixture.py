"""Build the 20-question smoke fixtures from the fetched dataset files.

Keeps the first 20 questions, every chunk they need (gold and, where the dataset ships them, the
candidate distractors recorded in `metadata`), and a deterministic fill of further chunks, so
retrieval on the fixture keeps the gold/distractor structure of the full corpus.
Run: uv run python scripts/make_fixture.py [dataset ...]   (default: every registered dataset)
"""

from __future__ import annotations

import sys

import polars as pl
from triplum.bench.inputs import materialize
from triplum.datasets import base, registry


def main(names: list[str]) -> None:
    base.FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name in names or registry.names():
        spec = registry.get(name)
        if not spec.fixture:
            print(name, "has no fixture")
            continue
        ds = registry.load(name)
        # Long-document sets (transcripts, articles) get fewer fillers to keep the fixture small.
        inputs = materialize(ds)
        mean_chars = inputs.corpus.chunks.select(pl.col("text").str.len_chars().mean()).item() or 0
        distractors = 5 if mean_chars > 5000 else 40
        frames = base.subset(
            ds,
            distractors=distractors,
        )
        path = base.write_fixture(name, frames)
        selected = materialize(frames)
        print(
            name,
            selected.qa.height if selected.qa is not None else 0,
            "questions",
            selected.corpus.chunks.height,
            "chunks",
            path.name,
        )


if __name__ == "__main__":
    main(sys.argv[1:])
