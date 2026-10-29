"""Naive ingestion: Markdown files in a folder become `Source` and `Chunk` records in a store."""

import sys
from pathlib import Path

from triplum.datasets.markdownfolder import MarkdownFolder
from triplum.datatype import Collection
from triplum.steps.chunking import FixedSize
from triplum.store import SQLAlchemyStore
from triplum.utils.data import DataLoader

if __name__ == "__main__":
    collection = Collection(name="notes")
    dataset = MarkdownFolder(Path(sys.argv[1]), collection_id=collection.id)
    # In memory. To keep records across runs, use a SQLite file and a fixed collection id:
    # IDs repeat only within the same collection.
    store = SQLAlchemyStore()
    chunker = FixedSize(1000)
    for source in DataLoader(dataset, batch_size=None):
        store.add_sources([source])
        store.replace_chunks(source.id, chunker(source))
        print(source.origin, len(store.chunks(source.id)), "chunks")
