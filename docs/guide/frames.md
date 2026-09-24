# Corpus frames

Before writing documents to a store, convert them to a `CorpusBatch` with `corpus_batch`:

```python
from triplum.data.corpus import Document
from triplum.datasets.collate import corpus_batch

batch = corpus_batch([Document(id="note-1", source="notes", text="Alice met Bob.")])
assert batch.documents["id"].to_list() == ["note-1"]
assert batch.grants["principal"].to_list() == ["public"]
assert batch.chunks["text"].to_list() == ["Alice met Bob."]
```

The three frames contain document details, who can read each document, and source-defined text
segments. With no segments supplied, this example has one chunk containing the whole text.
For larger sources, pass `corpus_batch` as the loader's `collate_fn` to convert one list at a time.

Next: [write and read the batch](store.md). The [schema reference](../api/data.md) lists every
column.
