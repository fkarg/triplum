"""Markdown files in a local folder as `Source` records."""

import hashlib
from pathlib import Path

from triplum.datatype import Source
from triplum.utils.cache import content_key
from triplum.utils.data import Dataset


class MarkdownFolder(Dataset[Source]):
    """Top-level `.md` files of a folder, one `Source` per file, in sorted name order.

    The file list is fixed at construction; file contents are read on access, as UTF-8 with
    newlines unchanged. `origin` is the absolute file path. The fingerprint reads every file.
    """

    def __init__(self, folder: Path) -> None:
        folder = folder.resolve()
        if not folder.is_dir():
            raise NotADirectoryError(folder)
        self.paths = sorted(p for p in folder.glob("*.md") if p.is_file())

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, index: int) -> Source:
        path = self.paths[index]
        return Source(origin=path, text=path.read_bytes().decode("utf-8"))

    def fingerprint(self) -> str:
        return content_key(
            "markdown-folder",
            [[p.name, hashlib.sha256(p.read_bytes()).hexdigest()] for p in self.paths],
        )
