# Datasets and the DataLoader

A **dataset** gives access to records of one type, such as `Source`. A **`DataLoader`** consumes
a dataset one record or one batch at a time. The split is deliberate: the dataset decides *what*
the records are, the loader only decides *how many at once*. A loader never converts records.

## Batch records without a download

Start with an in-memory dataset to see the boundary between records and batching:

```python
from triplum.datatype import Collection, Source
from triplum.utils.data import DataLoader, RecordDataset

collection = Collection(name="Greetings")
records = RecordDataset(
    [
        Source(collection_id=collection.id, origin="first", text="Hello"),
        Source(collection_id=collection.id, origin="second", text="World"),
        Source(collection_id=collection.id, origin="third", text="Again"),
    ]
)
for batch in DataLoader(records, batch_size=2):
    print([source.text for source in batch])
```

```text
['Hello', 'World']
['Again']
```

The loader keeps record order and includes the final, smaller batch. With `batch_size=None`, it
yields individual records instead. Neither form converts or changes the records.

## Load a benchmark corpus

This loads the [MultiHop-RAG](https://huggingface.co/datasets/yixuantt/MultiHopRAG) corpus of
609 news articles (licence: ODC-BY 1.0) and iterates over it as sources. The first run downloads
the corpus file.

```python
from triplum.datasets.multihoprag import MultiHopRAGCorpus
from triplum.datatype import Collection
from triplum.utils.data import DataLoader

collection = Collection(name="MultiHop-RAG")
corpus = MultiHopRAGCorpus(collection_id=collection.id)
print(len(corpus))  # 609

for source in DataLoader(corpus, batch_size=None):
    print(source.origin)  # https://mashable.com/article/cyber-monday-deals-amazon-2023
    break

for batch in DataLoader(corpus, batch_size=256):
    print(len(batch))  # 256, 256, 97
```

1. `MultiHopRAGCorpus(collection_id=collection.id)` fetches the pinned `corpus.json` into
   `multihoprag/corpus.json` under the [datasets folder](#where-downloads-go), unless a copy with
   the pinned SHA-256 hash is already there, then parses it. It is a `Dataset[Source]`: one
   `Source` per article, in that collection. `origin` is the article URL; `text` is the title, a
   blank line, then the body.
2. `DataLoader(corpus, batch_size=None)` yields the records one by one, unchanged.
3. `DataLoader(corpus, batch_size=256)` yields lists of up to 256 sources. The last batch keeps
   the remainder.

To download ahead of time, pass the module's `ENTRY` to `download()`; it returns the dataset's
folder. Both the constructor and `download()` take an optional `root` folder in place of the
default datasets folder.

```python
from triplum.datasets.files import download
from triplum.datasets.multihoprag import ENTRY

print(download(ENTRY))  # ~/.cache/triplum/datasets/multihoprag
```

## Where downloads go

Downloaded datasets live in `$XDG_CACHE_HOME/triplum/datasets`, or `~/.cache/triplum/datasets`
when `XDG_CACHE_HOME` is unset or not an absolute path. The
[computation cache](../infrastructure/cache.md) keeps its database in the same `triplum` folder.
Both are re-creatable: deleting the folder only costs a new download.

- Each file is fetched once, on first use, from a pinned URL and checked against a pinned
  SHA-256 hash. Later uses verify the local copy and skip the download.
- Each download is written to its own temporary `.part` file and renamed only when its hash
  matches, so an interrupted, unexpected or concurrent download never replaces a good file. A
  download whose hash does not match raises `ValueError`.
- An existing file whose hash does not match also raises `ValueError`, naming the expected and
  actual digests, and is left untouched; it is not downloaded again. This holds for dataset
  constructors too. To recover, run `triplum datasets remove NAME`, then download again.
- Files are downloaded in the entry's order; files installed before a failure stay.
- Passing `root` to a dataset or to `download()` keeps the files under that folder instead.

### Declare a downloadable dataset

Each dataset module declares its files and licence terms in one `ENTRY`, beside its parser:

```python
from triplum.datasets.files import DatasetEntry, PinnedFile

ENTRY = DatasetEntry(
    name="multihoprag",  # also the folder name under the datasets folder
    files=[
        PinnedFile(
            name="corpus.json",  # a plain file name inside that folder
            url="https://huggingface.co/datasets/yixuantt/MultiHopRAG/resolve/main/corpus.json",
            sha256="20b61b5ab84de84a927420c5d265b7ec8d859ae49980699958a787ade9e4d28f",
            bytes=6785567,
        )
    ],
    licence="ODC-BY 1.0",
    commercial_reuse="Permitted with attribution",
)
```

`triplum.datasets.catalogue.CATALOGUE` maps each name to its entry; it is the list the
command-line tools work on. The dataset rows of the [licences page](../licences.md) are
generated from these entries, so the recorded terms live in one place.

### Manage downloads from the command line

`triplum datasets` lists, downloads, verifies and removes catalogued datasets, and prints their
recorded licence terms. It always uses the datasets folder; there is no `--root` option.
The commands wrap importable functions: `download`, and `dataset_status`, `verify_dataset` and
`remove_dataset` in `triplum.datasets.admin`, which take a `root` like `download` does.

```sh
triplum datasets list
triplum datasets download NAME
triplum datasets verify NAME
triplum datasets remove NAME [--yes]
triplum datasets licence NAME
```

Every command accepts `--json` for structured output on stdout and `--no-input`. A name may be
shortened or slightly misspelled: an exact match wins, then a unique prefix, substring or close
typo. Any match other than an exact one is reported on stderr. An ambiguous or unknown name lists
the choices and does nothing. Progress, errors and these reports go to stderr; errors exit
nonzero without a traceback.

The output below comes from a fresh, temporary `XDG_CACHE_HOME`. `list` shows each dataset as
`missing`, `partial` or `present`, with its bytes on disk and its expected size:

```text
$ triplum datasets list
hotpotqa  missing  /tmp/demo/triplum/datasets/hotpotqa
  hotpotqa.json  missing, expected 8183058 bytes
  hotpotqa_corpus.json  missing, expected 6414109 bytes
multihoprag  missing  /tmp/demo/triplum/datasets/multihoprag
  corpus.json  missing, expected 6785567 bytes
$ triplum datasets download multihoprag
Downloading multihoprag if missing…
/tmp/demo/triplum/datasets/multihoprag
$ triplum datasets licence hotpot
triplum: dataset 'hotpot' matched 'hotpotqa'
hotpotqa: HotpotQA content CC BY-SA 4.0; HippoRAG protocol files (commit 191f2811) MIT
Commercial reuse: Permitted with attribution; adaptations must be shared under CC BY-SA 4.0; retain HippoRAG's MIT copyright notice
```

`list` never downloads or hashes, so `present` only means every file exists, not that it is
verified. `verify` hashes every file, reports each missing, mismatched or unreadable one, and
exits nonzero if there is any. It never downloads or repairs. After overwriting the downloaded
corpus with other bytes:

```text
$ triplum datasets verify multi
triplum: dataset 'multi' matched 'multihoprag'
multihoprag: all files verified
$ echo garbage > /tmp/demo/triplum/datasets/multihoprag/corpus.json
$ triplum datasets verify multihoprag
/tmp/demo/triplum/datasets/multihoprag/corpus.json: sha256 233d4809807d21d1b24ae54639eede42f519dcbe35ca71d51bd051bca59c6a68, expected 20b61b5ab84de84a927420c5d265b7ec8d859ae49980699958a787ade9e4d28f
$ triplum datasets remove multihoprag
Removed 8 bytes of multihoprag.
```

- `download` does what a constructor does on first use: verified files are kept, missing ones
  are fetched, and a mismatched file stops the command, untouched. The first failure stops it.
- `remove` deletes only the dataset's declared files, then its folder if that is empty. Other
  files, and the computation cache, are untouched; files that are already missing are fine.
  When the files present add up to more than 5,000,000,000 bytes, it asks first on a terminal.
  `--yes` skips the question. Without a terminal, or with `--no-input`, it refuses unless `--yes`
  is given.
- Removing is not cancelling: a download running at the same time may put files back.
- `licence` prints the recorded terms and what they imply for commercial reuse, without
  downloading anything.
- If a download fails TLS verification, point `SSL_CERT_FILE` at your system's CA bundle. Do not
  disable verification.

## Load HotpotQA

[`HotpotQA`][triplum.datasets.hotpotqa.HotpotQA] is a [benchmark](benchmark-inputs.md): a corpus
and questions over it. It reads the 1,000-question sample of
[HotpotQA](https://hotpotqa.github.io/) (licence: CC BY-SA 4.0) that
[HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) publishes for its retrieval results,
with 9,811 Wikipedia passages. The first run downloads both files.

```python
from triplum.datasets.hotpotqa import HotpotQA
from triplum.datatype import Collection

collection = Collection(name="HotpotQA")
benchmark = HotpotQA(gold="passage")
corpus = benchmark.corpus(collection.id)
questions = benchmark.questions()
print(len(corpus), len(questions))

question = questions[0]
print(question.input.text)
print(question.answers)
for span in question.evidence[0]:
    print(span.document, span.start, span.end)
print(repr(corpus[0].text[:60]))
```

```text
9811 1000
what is one of the stars of  The Newcomers known for
['superhero roles as the Marvel Comics']
The Newcomers (film) 0 396
Chris Evans (actor) 0 293
'Vaada Poda Nanbargal\nVaada Poda Nanbargal is a 2011 Indian T'
```

- The files come from HippoRAG's repository at a fixed commit and are hash-checked like every
  [download](#where-downloads-go). They are parsed and checked once, at construction. A
  supporting fact that names no passage or sentence raises `ValueError`.
- Each passage becomes one Source with text `title`, a newline, then the passage text, which is
  HippoRAG's passage format. `origin` and `external_id` are the Wikipedia title, unique in this
  corpus, and evidence uses it as the document key.
- Each question has one evidence set and its single answer. `metadata` keeps HotpotQA's `type`
  and `level`.

### Choose the gold unit

`gold` chooses what one gold item is:

- `gold="sentence"`, the default, gives one span per supporting sentence: HotpotQA's native
  supporting facts.
- `gold="passage"` gives one span per supporting passage, covering its whole Source text. This
  is the unit HippoRAG's passage recall counts.

The two modes give different [recall](recall.md), even when each passage is one chunk. 350 of
the 1,000 questions have several supporting sentences in one passage. With sentence gold, each
sentence is one item, so such a passage weighs more in the question's recall than a passage
holding one supporting sentence. With passage gold, every supporting passage weighs the same.
Use passage gold to compare with HippoRAG's published numbers.

## A local example: Markdown files

[`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder] reads your own notes: one `Source`
per `.md` file in a folder. Given a folder `notes/` with `returns.md` and `shipping.md`:

```python
from pathlib import Path

from triplum.datasets.markdownfolder import MarkdownFolder
from triplum.datatype import Collection
from triplum.utils.data import DataLoader

collection = Collection(name="Research notes")
notes = MarkdownFolder(Path("notes"), collection_id=collection.id)
print(len(notes))

for source in DataLoader(notes, batch_size=None):
    print(Path(source.origin).name, repr(source.text[:20]))
```

Output:

```text
2
returns.md '# Returns\n\nReturns a'
shipping.md '# Shipping\n\nOrders s'
```

The example prints only each file's name; `source.origin` retains its absolute path.

- Only `.md` files directly in the folder count; subfolders are not searched. Files come in
  sorted name order.
- The file list is fixed when you create the dataset; a file added later needs a new
  `MarkdownFolder`. Contents are read, as UTF-8, each time a record is accessed.
- `origin` is the absolute path of the file, as a string.
- Every source belongs to the collection given as `collection_id`.
- Its `fingerprint()` hashes the collection and every file's name and bytes, so it reads the
  whole folder.

## Two kinds of dataset

- **`Dataset`**: indexed. Implement `__len__`, `__getitem__` and `fingerprint()`. Use it when
  records can be counted and fetched by position, as with the corpus above. `RecordDataset`
  wraps an in-memory list of Pydantic records.
- **`IterableDataset`**: streaming. Implement `__iter__` and `fingerprint()`. Use it when there
  is no length or random access, for example a stream that can only be read once.

Neither class imposes a schema; each dataset chooses its record type.

## Fingerprints

Every dataset must implement `fingerprint()`: a stable string identifying its logical content.
Two datasets with equal fingerprints promise the same records in the same order. A name or a URL
that can change is not enough; the MultiHop-RAG corpus uses the pinned file hash and its
collection. Computing the fingerprint must not consume the dataset, and batch size is not part of
it. Fingerprints are meant to let expensive later steps be cached by their inputs.

## What the loader does

- `batch_size=None` passes each record through unchanged.
- An integer `batch_size` yields lists of that size (the default is 1), or whatever `collate_fn`
  builds from each list.
- It is lazy: it does not prefetch, does not replay a one-shot stream, and lets errors from the
  dataset propagate.

Turning a dataset's records into sources, when they are not sources already, is
[conversion](conversion.md), not the loader's job.

## Reference

- [`Dataset`][triplum.utils.data.dataset.Dataset],
  [`IterableDataset`][triplum.utils.data.dataset.IterableDataset] and
  [`RecordDataset`][triplum.utils.data.dataset.RecordDataset]
- [`DataLoader`][triplum.utils.data.loader.DataLoader]
- [`triplum.datasets.multihoprag`][triplum.datasets.multihoprag],
  [`HotpotQA`][triplum.datasets.hotpotqa.HotpotQA] and
  [`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder]
- [`datasets_home`][triplum.datasets.files.datasets_home],
  [`DatasetEntry`][triplum.datasets.files.DatasetEntry],
  [`PinnedFile`][triplum.datasets.files.PinnedFile],
  [`download`][triplum.datasets.files.download] and
  [`fetch`][triplum.datasets.files.fetch]
- [`triplum.datasets.catalogue`][triplum.datasets.catalogue] and
  [`triplum.datasets.admin`][triplum.datasets.admin]

Next: [Conversion](conversion.md).
