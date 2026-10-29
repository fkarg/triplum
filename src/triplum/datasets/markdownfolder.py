"""Markdown files in a local folder as `Source` records."""

import hashlib
from pathlib import Path
from uuid import UUID

from triplum.datatype import Source
from triplum.utils.cache import content_key
from triplum.utils.data import Dataset


class MarkdownFolder(Dataset[Source]):
    """Top-level `.md` files of a folder, one `Source` per file, in sorted name order.

    The file list is fixed at construction; file contents are read on access, as UTF-8 with
    newlines unchanged. `origin` is the absolute file path. The fingerprint covers each absolute
    path and file content, and the collection, so it reads every file.
    """

    def __init__(self, folder: Path, *, collection_id: UUID) -> None:
        self.collection_id = collection_id
        folder = folder.resolve()
        if not folder.is_dir():
            raise NotADirectoryError(folder)
        self.paths = sorted(p for p in folder.glob("*.md") if p.is_file())

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, index: int) -> Source:
        path = self.paths[index]
        text = path.read_bytes().decode("utf-8")
        return Source(collection_id=self.collection_id, origin=str(path), text=text)

    def fingerprint(self) -> str:
        return content_key(
            "markdown-folder",
            [
                str(self.collection_id),
                [[str(p), hashlib.sha256(p.read_bytes()).hexdigest()] for p in self.paths],
            ],
        )
