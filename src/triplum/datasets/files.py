"""Pinned dataset files: fetched once, kept only when their sha256 matches."""

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

from triplum.utils.paths import cache_home


def datasets_home() -> Path:
    """The default folder for downloaded datasets, beside the computation cache; not created."""
    return cache_home() / "datasets"


def verified(path: Path, sha256: str) -> bool:
    """Whether `path` is a file whose content has this sha256."""
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == sha256


def fetch(url: str, path: Path, sha256: str) -> Path:
    """Download `url` to `path` unless a verified copy exists; return `path`.

    Each call downloads into its own temporary file beside `path` and renames it only after its
    hash matches, so `path` never holds a partial or unexpected file, also when processes race.
    A mismatch raises `ValueError`.
    """
    if verified(path, sha256):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".part")
    os.close(handle)
    part = Path(name)
    try:
        urllib.request.urlretrieve(url, part)
        if not verified(part, sha256):
            raise ValueError(f"{url} does not match the pinned sha256 {sha256}")
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
    return path
