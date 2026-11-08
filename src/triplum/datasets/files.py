"""Pinned dataset files: fetched once, kept only when their sha256 matches."""

import hashlib
import http.client
import os
import shutil
import stat
import tempfile
import urllib.request
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from triplum.utils.paths import cache_home


def plain_name(name: str) -> str:
    """`name` if it names an entry directly inside a folder; otherwise `ValueError`."""
    if name in ("", ".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"{name!r} must be a plain name, not a path")
    return name


class PinnedFile(BaseModel):
    """One file of a dataset, at a fixed URL with a fixed content hash."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="File name inside the dataset's folder; no subfolders.")
    url: str = Field(description="Where the file is downloaded from.")
    sha256: str = Field(description="Hex SHA-256 of the file's bytes.")
    bytes: int = Field(ge=0, description="The file's size in bytes.")

    @field_validator("name")
    @classmethod
    def _plain(cls, name: str) -> str:
        return plain_name(name)


class DatasetEntry(BaseModel):
    """A downloadable dataset: its files and recorded licence terms.

    The entry is the one record of these terms; the licences page is generated from it.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Catalogue key and folder name under the datasets folder.")
    files: list[PinnedFile] = Field(description="The files, in download order.")
    licence: str = Field(min_length=1, description="The recorded licence terms.")
    commercial_reuse: str = Field(
        min_length=1,
        description='What the terms imply for commercial reuse; "unknown" when not established.',
    )

    @field_validator("name")
    @classmethod
    def _plain(cls, name: str) -> str:
        return plain_name(name)


TIMEOUT = 60  # seconds without data before a download fails


def datasets_home() -> Path:
    """The default folder for downloaded datasets, beside the computation cache; not created."""
    return cache_home() / "datasets"


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def existing(path: Path) -> Path | None:
    """`path` if a readable regular file is there, `None` if nothing is.

    Anything else (a directory, broken link, unreadable file or folder) raises: it is not
    missing, and treating it as missing would hide the problem.
    """
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    try:
        regular = stat.S_ISREG(path.stat().st_mode)
    except FileNotFoundError:
        regular = False
    if not regular:
        raise ValueError(f"{path} is not a file")
    path.open("rb").close()
    return path


def fetch(url: str, path: Path, sha256: str) -> Path:
    """Download `url` to `path` unless it is already there; return `path`.

    Each call downloads into its own temporary file beside `path` and renames it only after its
    hash matches, so `path` never receives a partial or unexpected download, also when processes
    race. An existing `path` must be a file with this hash; anything else raises `ValueError`
    and is left untouched (remove it to download again), as does a download that does not match.
    """
    if existing(path) is not None:
        actual = sha256_of(path)
        if actual != sha256:
            raise ValueError(
                f"{path} has sha256 {actual}, expected {sha256}; remove it to download again"
            )
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".part")
    os.close(handle)
    part = Path(name)
    try:
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as response, part.open("wb") as out:
                shutil.copyfileobj(response, out)
        except (OSError, http.client.HTTPException) as error:
            raise OSError(f"downloading {url} to {path} failed: {error}") from error
        actual = sha256_of(part)
        if actual != sha256:
            raise ValueError(
                f"downloading {url} to {path} failed: sha256 {actual}, expected the pinned {sha256}"
            )
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
    return path


def download(entry: DatasetEntry, root: Path | None = None) -> Path:
    """Fetch the entry's files into `root/<name>`, in order; return that folder.

    `root` defaults to `datasets_home()`. Files fetched before a failure stay.
    """
    folder = (datasets_home() if root is None else root) / entry.name
    for file in entry.files:
        fetch(file.url, folder / file.name, file.sha256)
    return folder
