# stage: checkpointed, content-addressed processing steps

Snapshot 2026-09-18. A stage is a plain function wrapped by `stage`. Under a `Run` it gets a
data key from its arguments, records the code it executed as a manifest, publishes its output
as an artifact and writes an invocation row; a rerun fetches the artifact when the key matches
and the manifest, and every input artifact's manifest, still hashes the same. Without a `Run`
the wrapper is the function. Contract: [`specs/2026-09-17-stages.md`](../specs/2026-09-17-stages.md).
The example below runs as a test.

```python
import tempfile
from collections.abc import Iterator
from pathlib import Path

import polars as pl
from triplum.bench.runstore import RunStore
from triplum.data.corpus import Document
from triplum.stage import Run, active, stage
from triplum.utils.data import RecordDataset


class Calls:
    """A counter for this example. Not a plain dict: a module-level dict is plain data, so the
    manifest would capture its value and every call would invalidate the last."""

    words = 0
    longest = 0


@stage
def words(docs: RecordDataset[Document], min_len: int) -> Iterator[pl.DataFrame]:
    """A streamed stage: one frame per document, written to its artifact as it is pulled."""
    Calls.words += 1
    for d in docs:
        ws = [w for w in d.text.split() if len(w) >= min_len]
        yield pl.DataFrame({"doc": [d.id] * len(ws), "word": ws})


@stage
def longest(frames: Iterator[pl.DataFrame]) -> pl.DataFrame:
    """A value stage over the stream; its artifact is one frame."""
    Calls.longest += 1
    df = pl.concat(list(frames))
    return df.sort(pl.col("word").str.len_chars(), descending=True).head(1)


docs = RecordDataset(
    [
        Document(id="a", source="demo", text="Graphs help retrieval and evaluation"),
        Document(id="b", source="demo", text="Bob is tall"),
    ]
)
root = Path(tempfile.mkdtemp())
with RunStore(root / "runs.db") as rs:
    run_id = rs.start_run(
        {
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
    )
    with active(Run(store=rs, root=root, run_id=run_id, seed=0)):
        assert longest(words(docs, 4))["word"][0] == "evaluation"
        assert longest(words(docs, 4))["word"][0] == "evaluation"  # both stages fetched
        assert longest(words(docs, 3))["word"][0] == "evaluation"  # new input: computed again
    inv = rs.invocations(run_id)
    assert inv["fetched"].to_list() == [0, 0, 1, 1, 0, 0]
    assert (Calls.words, Calls.longest) == (2, 2)
    # every artifact knows what it was built from
    last = inv.row(-1, named=True)
    assert [r["stage"].rsplit(":", 1)[-1] for r in rs.lineage(last["key"], last["code"])] == [
        "longest",
        "words",
    ]

# outside a run the same calls are plain functions: nothing is cached or recorded
assert longest(words(docs, 4))["word"][0] == "evaluation" and Calls.words == 3
```

Edit `words` (its body, a helper it calls, or a module constant it reads) and rerun: `words`
recomputes and `longest` after it; edit `longest` alone and `words` is fetched. With
`--replicates` on the CLI, stages that take a seed-sensitive adapter rerun per replicate and
`triplum bench variance` shows which stage the spread came from.

::: triplum.stage.stage

::: triplum.stage.identity

::: triplum.stage.fingerprint

::: triplum.stage.trace

::: triplum.stage.artifacts

::: triplum.stage.run
