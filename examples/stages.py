"""Two stages of your own: fetched on the second call, recomputed when an input changes, and
every artifact knows what it was built from. Edit `words` and run again: it recomputes and
`longest` after it; edit only `longest` and `words` is fetched."""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import polars as pl
from triplum.bench.runstore import RunStore
from triplum.data.corpus import Document
from triplum.stage import Run, active, stage
from triplum.utils.data import RecordDataset


@stage
def words(docs: RecordDataset[Document], min_len: int) -> Iterator[pl.DataFrame]:
    """A streamed stage: one frame per document, written to its artifact as it is pulled."""
    print("  computing words")
    for d in docs:
        ws = [w for w in d.text.split() if len(w) >= min_len]
        yield pl.DataFrame({"doc": [d.id] * len(ws), "word": ws})


@stage
def longest(frames: Iterator[pl.DataFrame]) -> pl.DataFrame:
    """A value stage over the stream; its artifact is one frame."""
    print("  computing longest")
    df = pl.concat(list(frames))
    return df.sort(pl.col("word").str.len_chars(), descending=True).head(1)


docs = RecordDataset(
    [
        Document(id="a", source="demo", text="Graphs help retrieval and evaluation"),
        Document(id="b", source="demo", text="Bob is tall"),
    ]
)
root = Path(tempfile.mkdtemp())
meta = {
    "kind": "qa",
    "dataset": "demo",
    "config_hash": "",
    "config_json": "{}",
    "code_version": "",
    "dirty": 0,
    "code_hash": "",
    "corpus_hash": "",
    "questions_hash": "",
    "n": 0,
    "seed": 0,
    "viewer_json": "[]",
    "host": "",
}
with RunStore(root / "runs.db") as rs:
    run_id = rs.start_run(meta)
    with active(Run(store=rs, root=root, run_id=run_id, seed=0)):
        print("first call")
        print(longest(words(docs, 4)))
        print("second call, same inputs")
        print(longest(words(docs, 4)))
        print("third call, another min_len")
        print(longest(words(docs, 3)))
    inv = rs.invocations(run_id)
    print(inv.select("id", "stage", "fetched", "status"))
    last = inv.row(-1, named=True)
    print(
        "lineage of the last artifact:", [r["stage"] for r in rs.lineage(last["key"], last["code"])]
    )

print("outside a run the same calls are plain functions:")
print(longest(words(docs, 4)))
