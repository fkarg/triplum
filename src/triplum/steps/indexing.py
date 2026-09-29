"""Toy indexing: Markdown files, fixed character slices, and a list as the store."""

from pathlib import Path

from triplum.datatype import Chunk
from triplum.steps.chunking import FixedSize
from triplum.steps.conversion import Utf8File
from triplum.utils.data import DataLoader, RecordDataset


def index_folder(folder: Path, chunk_size: int = 1000) -> list[Chunk]:
    """Read top-level .md files and return chunks in file/offset order.

    The returned list is the in-memory store. Every call starts fresh. Files are read eagerly;
    empty files produce no chunks. There is no Markdown parsing, overlap or embedding.
    """
    chunker = FixedSize(chunk_size)
    convert = Utf8File()
    folder = folder.resolve()
    if not folder.is_dir():
        raise NotADirectoryError(folder)

    dataset = RecordDataset(
        [s for path in sorted(folder.glob("*.md")) if path.is_file() for s in convert(path)]
    )
    store: list[Chunk] = []
    for source in DataLoader(dataset, batch_size=None):
        store.extend(chunker(source))
    return store
