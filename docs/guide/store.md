# Read from a store

The store checks document grants when it reads chunks. Here, each viewer sees only the document
granted to that principal:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from triplum.data.corpus import Document
from triplum.data.viewer import Viewer
from triplum.datasets.collate import corpus_batch
from triplum.store.sqlite.store import SqliteStore

batch = corpus_batch(
    [
        Document(id="public-note", source="notes", text="Alice met Bob.", grants=("public",)),
        Document(id="private-note", source="notes", text="Bob moved to Oslo.", grants=("alice",)),
    ]
)

with TemporaryDirectory() as directory:
    store = SqliteStore(Path(directory) / "corpus.db")
    try:
        store.put_documents(batch.documents, batch.grants)
        store.put_chunks(batch.chunks)
        ids = batch.chunks["id"].to_list()
        public = store.get_chunks(ids, Viewer.of("public"))
        alice = store.get_chunks(ids, Viewer.of("alice"))
        assert public["text"].to_list() == ["Alice met Bob."]
        assert alice["text"].to_list() == ["Bob moved to Oslo."]
    finally:
        store.close()
```

`put_documents` writes document details and grants; `put_chunks` writes their text segments.
`get_chunks` takes chunk IDs and a viewer, then returns only chunks that viewer may read.

Next: [search local documents](search.md) or [run a baseline benchmark](benchmark.md).
