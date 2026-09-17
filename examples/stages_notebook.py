import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import tempfile
    from collections.abc import Iterator
    from pathlib import Path

    import marimo as mo
    import polars as pl
    from triplum.bench.runstore import RunStore
    from triplum.data.corpus import Document
    from triplum.stage import Run, active, stage
    from triplum.utils.data import RecordDataset

    return Document, Iterator, Path, RecordDataset, Run, RunStore, active, mo, pl, stage, tempfile


@app.cell
def _(mo):
    mo.md(
        """
        # Stages in a notebook

        A stage is a plain function. Under a run it gets a data key from its arguments, records
        the code it executed, publishes its output and is fetched next time. Edit a cell and
        rerun: only the stages whose code or inputs changed recompute.
        """
    )


@app.cell
def _(Iterator, RecordDataset, Document, pl, stage):
    @stage
    def words(docs: RecordDataset[Document], min_len: int) -> Iterator[pl.DataFrame]:
        for d in docs:
            ws = [w for w in d.text.split() if len(w) >= min_len]
            yield pl.DataFrame({"doc": [d.id] * len(ws), "word": ws})

    @stage
    def longest(frames: Iterator[pl.DataFrame]) -> pl.DataFrame:
        df = pl.concat(list(frames))
        return df.sort(pl.col("word").str.len_chars(), descending=True).head(1)

    return longest, words


@app.cell
def _(Document, Path, RecordDataset, RunStore, tempfile):
    docs = RecordDataset(
        [
            Document(id="a", source="demo", text="Graphs help retrieval and evaluation"),
            Document(id="b", source="demo", text="Bob is tall"),
        ]
    )
    root = Path(tempfile.mkdtemp())
    rs = RunStore(root / "runs.db")
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
    return docs, root, rs, run_id


@app.cell
def _(Run, active, docs, longest, root, rs, run_id, words):
    with active(Run(store=rs, root=root, run_id=run_id, seed=0)):
        result = longest(words(docs, 4))
    result


@app.cell
def _(rs, run_id):
    rs.invocations(run_id).select("id", "stage", "fetched", "status", "wall_s")


if __name__ == "__main__":
    app.run()
