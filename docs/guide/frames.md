# Corpus frames

The store accepts three frames together: document details, reader grants, and text chunks.
`corpus_batch` converts a list of `Document` records to those frames.

```python
from triplum.data.corpus import Document
from triplum.datasets.collate import corpus_batch

batch = corpus_batch([Document(id="note-1", source="notes", text="Alice met Bob.")])
assert batch.documents.height == 1
assert batch.grants.height == 1
assert batch.chunks["text"].to_list() == ["Alice met Bob."]
```

The [schema reference](../api/data.md) defines the column layouts.
