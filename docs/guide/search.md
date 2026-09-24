# Search local documents

Put text files in a folder, load them as documents, then search their content. Each file is one
document and one full-text segment. The SQLite store builds its text index as segments are written.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from triplum.data.viewer import Viewer
from triplum.datasets.collate import corpus_batch
from triplum.ingest.files import FolderCorpus
from triplum.store.sqlite.store import SqliteStore
from triplum.utils.data import DataLoader

with TemporaryDirectory() as directory:
    folder = Path(directory)
    (folder / "notes.md").write_text(
        "Alice moved to Ghent.\n\nBob stayed in Oslo.", encoding="utf-8"
    )
    (folder / "other.txt").write_text("Carol lives in Paris.", encoding="utf-8")

    store = SqliteStore(folder / "index.sqlite")
    try:
        source = FolderCorpus(folder)
        batches = DataLoader(source, batch_size=32, collate_fn=corpus_batch)
        store.ingest_corpus(source.fingerprint(), "local", batches)
        matches = store.search_text("Oslo", Viewer.of("public"))
        assert matches["document_id"].to_list() == ["notes.md"]
        assert "Bob stayed in Oslo" in matches["text"][0]
    finally:
        store.close()
```

`search_text` matches any query term and returns visible files in document ID order, up to its
`limit` (10 by default). It does not rank results. The same folder source also reads PDFs with a
text layer and `.docx` paragraphs; it does not perform OCR or read Word tables. Markdown and plain
text are read as UTF-8 and invalid bytes raise an error.
