# Datasets and the DataLoader

A **dataset** gives access to records of one type, such as `Source`. A **`DataLoader`** consumes
a dataset one record or one batch at a time. The split is deliberate: the dataset decides *what*
the records are, the loader only decides *how many at once*. A loader never converts records.

## Example

This loads the [MultiHop-RAG](https://huggingface.co/datasets/yixuantt/MultiHopRAG) corpus of
609 news articles (licence: ODC-BY 1.0) and iterates over it as sources. The first run downloads
the corpus file.

```python
from pathlib import Path

from triplum.datasets.multihoprag import MultiHopRAGCorpus, download
from triplum.utils.data import DataLoader

corpus = MultiHopRAGCorpus(download(Path("data")))
print(len(corpus))  # 609

for source in DataLoader(corpus, batch_size=None):
    print(source.origin)  # https://mashable.com/article/cyber-monday-deals-amazon-2023
    break

for batch in DataLoader(corpus, batch_size=256):
    print(len(batch))  # 256, 256, 97
```

1. `download(Path("data"))` fetches the pinned `corpus.json` to `data/multihoprag/corpus.json`,
   checks its SHA-256 hash and returns the path. If a verified copy already exists, it skips the
   download.
2. `MultiHopRAGCorpus(path)` parses the file and is a `Dataset[Source]`: one `Source` per
   article. `origin` is the article URL; `text` is the title, a blank line, then the body.
3. `DataLoader(corpus, batch_size=None)` yields the records one by one, unchanged.
4. `DataLoader(corpus, batch_size=256)` yields lists of up to 256 sources. The last batch keeps
   the remainder.

## A local example: Markdown files

[`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder] reads your own notes: one `Source`
per `.md` file in a folder. Given a folder `notes/` with `returns.md` and `shipping.md`:

```python
from pathlib import Path

from triplum.datasets.markdownfolder import MarkdownFolder
from triplum.utils.data import DataLoader

notes = MarkdownFolder(Path("notes"))
print(len(notes))

for source in DataLoader(notes, batch_size=None):
    print(source.origin, repr(source.text[:20]))
```

Output:

```text
2
returns.md '# Returns\n\nReturns a'
shipping.md '# Shipping\n\nOrders s'
```

- Only `.md` files directly in the folder count; subfolders are not searched. Files come in
  sorted name order.
- The file list is fixed when you create the dataset; a file added later needs a new
  `MarkdownFolder`. Contents are read, as UTF-8, each time a record is accessed.
- `origin` is the absolute path of the file, as a string.
- Its `fingerprint()` hashes every file's name and bytes, so it reads the whole folder.

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
that can change is not enough; the MultiHop-RAG corpus uses the pinned file hash. Computing the
fingerprint must not consume the dataset, and batch size is not part of it. Fingerprints are meant
to let expensive later steps be cached by their inputs.

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
- [`triplum.datasets.multihoprag`][triplum.datasets.multihoprag] and
  [`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder]

Next: [Conversion](conversion.md).
