# Datasets: built-in sources and your own

Snapshot 2026-09-17. A dataset in triplum is a source of records with an identity, shaped like
PyTorch's: implement `IterableDataset` for a stream, `Dataset` for indexed access, and
`fingerprint()` for identity. A benchmark composes up to three independent sources, a corpus,
questions and gold triples, and the consumer decides how to batch them. Nothing reads a file
until it is iterated, and the built-in sources download and verify their files on first use.
Every example on this page runs as a test against the committed fixtures.

## Records

Three record types cross the boundary between a source and the pipeline. They are pydantic
models, validated once when the source yields them.

- `Document` (`triplum.data.corpus`): id, source, text, the segments the source ships as units
  (passages, paragraphs, turns, pages) as character spans into the text, grants, `observed_at`
  and metadata. A document with no segments given is one segment over its whole text.
- `Question` (`triplum.eval.inputs`): id, question, answer, aliases, the gold chunk ids,
  question type, whether it is answerable, an optional as-of instant, metadata.
- `Triple` (`triplum.eval.inputs`): subject, predicate, object, attributed to a question or a
  document.

Identity is chosen by the source and never by position in a parse. A document id is the
upstream key where one exists, else a content key; a chunk id is `chunk_id(document_id,
ordinal)`, so a question can name its gold from what its own record carries and never needs to
see the corpus. The store still speaks the canonical frames; `datasets.collate` projects record
lists onto them.

```python
from triplum.data.corpus import Document, Segment, chunk_id
from triplum.datasets import collate

text = "Graphs help retrieval.\n\nThey also help evaluation."
paper = Document(
    id="notes/graphs.md",
    source="notes",
    text=text,
    segments=(Segment(ordinal=0, start=0, end=22), Segment(ordinal=1, start=24, end=len(text))),
)
batch = collate.corpus_batch([paper])
assert batch.chunks["id"].to_list() == [chunk_id(paper.id, 0), chunk_id(paper.id, 1)]
assert batch.chunks["text"].to_list() == ["Graphs help retrieval.", "They also help evaluation."]
```

## Built-in benchmarks

The catalog in `triplum.datasets.registry` names every built-in benchmark. Loading one
constructs its sources and nothing else: the identity is known before any file exists locally,
which is what lets a run be found in the run store without parsing a dataset.

```python
from triplum.datasets import registry

benchmark = registry.load("hotpotqa")
assert benchmark.corpus is not None and benchmark.qa is not None
assert len(benchmark.corpus.fingerprint()) == 64  # no download, no parse
assert "hotpotqa" in registry.names(default_only=True)
```

Iterating a source fetches its pinned files, verifies their sha256 and yields records.
`registry.load(name, n=20)` selects the first twenty questions with `Take` and never truncates
the corpus; the committed fixtures are the way to get a small corpus. `triplum data` lists the
catalog with file states, `triplum data fetch` pre-fetches, and `triplum data verify <name>`
reads a whole dataset and checks that document ids are unique and every gold chunk exists.

The fixtures are the same benchmarks cut to twenty questions with their gold and candidate
chunks and a seeded fill of distractors, committed under `tests/fixtures`:

```python
from triplum.bench.inputs import materialize
from triplum.datasets import registry

inputs = materialize(registry.load_fixture("musique", n=5))
assert inputs.qa is not None and inputs.qa.height == 5
assert inputs.corpus.chunks.height > 5
gold = {cid for ids in inputs.qa["gold_chunk_ids"].to_list() for cid in ids}
assert gold <= set(inputs.corpus.chunks["id"])
```

`materialize` is the explicit eager bridge the current runner uses: it consumes every source
through a `DataLoader` with the matching collator, runs the cross-source integrity checks, and
reports the source fingerprints as the corpus and evaluation identities.

## Your own source

An in-memory benchmark needs no registry entry. `RecordDataset` holds a list of records and
identifies itself by their content; the runner takes the composition through `data=`.

```python
import tempfile
from pathlib import Path

from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
from triplum.bench.inputs import Benchmark
from triplum.bench.runner import run_benchmark
from triplum.data.corpus import Document, chunk_id
from triplum.eval.inputs import Question
from triplum.utils.data import RecordDataset

documents = [
    Document(id="d1", source="demo", text="Alice met Bob in Ghent."),
    Document(id="d2", source="demo", text="Bob is tall."),
]
questions = [
    Question(
        id="q1", question="Where did Alice meet Bob?", answer="Ghent", gold=(chunk_id("d1", 0),)
    )
]
mine = Benchmark(name="demo", corpus=RecordDataset(documents), qa=RecordDataset(questions))

root = Path(tempfile.mkdtemp())
cfg = RunConfig(
    dataset="demo",
    pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")),
    cache_root=str(root),
)
run_id = run_benchmark(cfg, data=mine)
assert run_id
```

A streaming source implements `__iter__` and a fingerprint that identifies the stream without
consuming it: a revision, a snapshot id, the parameters of a generator. The consumer batches.

```python
from collections.abc import Iterator

from triplum.data.corpus import Document
from triplum.datasets import collate
from triplum.utils.data import DataLoader, IterableDataset


class Ticker(IterableDataset[Document]):
    """One document per line of a captured feed; the capture id is the identity."""

    def __init__(self, lines: list[str], capture: str) -> None:
        self.lines, self.capture = lines, capture

    def __iter__(self) -> Iterator[Document]:
        for i, line in enumerate(self.lines):
            yield Document(id=f"{self.capture}:{i}", source="ticker", text=line, observed_at=i)

    def fingerprint(self) -> str:
        return f"ticker:{self.capture}"


feed = Ticker(["one", "two", "three"], capture="2026-09-17T10:00Z")
batches = list(DataLoader(feed, batch_size=2, collate_fn=collate.corpus_batch))
assert [b.chunks.height for b in batches] == [2, 1]
```

A folder of PDF, Word, Markdown or text files is a source too, by path, with an optional
`questions.jsonl` beside the files (`triplum.ingest.files`). Its identity is the hash of the
file bytes, so a copy of the folder elsewhere is the same corpus, and no PDF is parsed to
compute it.

```python
import tempfile
from pathlib import Path

from triplum.bench.inputs import materialize
from triplum.datasets import registry

folder = Path(tempfile.mkdtemp())
(folder / "a.md").write_text("# A\n\nFirst paragraph.\n", encoding="utf-8")
(folder / "b.txt").write_text("Second file.", encoding="utf-8")
inputs = materialize(registry.load(str(folder)))
assert inputs.corpus.documents["id"].to_list() == ["a.md", "b.txt"]
```

### Contributing a built-in source

A built-in module defines one class per part over pinned files, using the helpers in
`triplum.datasets.base`: `ListSource` for a file that decodes to a list of records,
`InlineCorpus` for a corpus that is the union of passages shipped inside question records,
`Pinned` plus `IterableDataset` for anything that streams. The class declares its logical key
(module docstring), bumps `version` when what it yields changes, and the module exports
`ENTRIES` with name, family, licence and a builder. Register the module in
`datasets/registry.py`, pin the files in `datasets/manifest.json`, add the licence row, run
`scripts/make_fixture.py <name>` and add a parser test on source-shaped records
(`tests/test_dataset_parsers.py`). The earlier source design and reviews are in the
[temporary foundation note](notes/previous-foundation.md).

## Settings

`triplum.settings.Settings` reads `TRIPLUM_DATA` (where pinned files live), `TRIPLUM_CACHE`
(the cache root) and `TRIPLUM_MIRRORS` (a JSON object of URL prefixes to replace at fetch
time). Pass a `Settings` to a source or a registry call to override the environment. Settings
never enter an identity: verified bytes are the same wherever they came from.
