"""Naive ingestion: Markdown files in a folder become `Source` and `Chunk` records in a store."""

import sys
from pathlib import Path

from triplum.datasets.markdownfolder import MarkdownFolder
from triplum.steps.chunking import FixedSize
from triplum.store import SQLAlchemyStore
from triplum.utils.data import DataLoader

if __name__ == "__main__":
    dataset = MarkdownFolder(Path(sys.argv[1]))
    store = SQLAlchemyStore()  # e.g. SQLAlchemyStore("sqlite:///naive.db") to keep the records
    chunker = FixedSize(1000)
    for source in DataLoader(dataset, batch_size=None):
        store.add_sources([source])
        store.add_chunks(chunker(source))
        print(source.origin, len(store.chunks(source.id)), "chunks")
