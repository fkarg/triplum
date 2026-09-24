"""Pinned files: exact URL, path under the data root, sha256 and size, fetched on first use.

`Files` binds a pinned set to `Settings`: local paths without I/O, a status without
downloading, a fetch that downloads what is missing through a `.part` file and verifies every
file against its pinned hash once per instance, and a fingerprint from the pinned digests.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from triplum.cache import content_key
from triplum.settings import Settings

MANIFEST = Path(__file__).with_name("manifest.json")
LARGE_BYTES = 300 << 20  # a dataset above this total download size only fetches when named

State = Literal["not downloaded", "partial", "verified", "invalid"]


class HashMismatch(RuntimeError):
    pass


class File(BaseModel, frozen=True):
    url: str
    name: str  # path under the data root
    sha256: str
    bytes: int | None = None


def manifest_files(dataset: str) -> tuple[File, ...]:
    """Pinned files for a dataset from `manifest.json` (url, sha256 and bytes as verified on
    2026-09-17), stored under `<dataset>/<upstream path>` in the data root."""
    entries = json.loads(MANIFEST.read_text())[dataset]
    return tuple(
        File(url=e["url"], name=f"{dataset}/{e['name']}", sha256=e["sha256"], bytes=e["bytes"])
        for e in entries
    )


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(p: Path, expected: str) -> str:
    got = sha256_file(p)
    if got != expected:
        raise HashMismatch(f"{p}: expected sha256 {expected}, got {got}")
    return got


class Files:
    def __init__(self, files: tuple[File, ...], settings: Settings | None = None) -> None:
        self.files = files
        self.settings = settings or Settings()
        self._verified: dict[str, Path] | None = None

    @property
    def bytes(self) -> int:
        return sum(f.bytes or 0 for f in self.files)

    @property
    def large(self) -> bool:
        return self.bytes > LARGE_BYTES

    def paths(self) -> dict[str, Path]:
        """Local path per pinned name; no I/O."""
        return {f.name: self.settings.data / f.name for f in self.files}

    def status(self) -> State:
        """Inspect local files without downloading or creating directories."""
        local = self.paths()
        present = [p.exists() for p in local.values()]
        if not any(present):
            return "not downloaded"
        if not all(present):
            return "partial"
        ok = all(sha256_file(local[f.name]) == f.sha256 for f in self.files)
        return "verified" if ok else "invalid"

    def fetch(self) -> dict[str, Path]:
        """Download missing files, then verify every file against its pinned hash; verified
        once per instance, so a source that reads several times pays the hash once."""
        if self._verified is not None:
            return self._verified
        local = self.paths()
        for f in self.files:
            p = local[f.name]
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_name(p.name + ".part")
                urllib.request.urlretrieve(self.settings.mirrored(f.url), tmp)
                os.replace(tmp, p)
            verify(p, f.sha256)
        self._verified = local
        return local

    def fingerprint(self) -> str:
        return content_key("files", [(f.name, f.sha256) for f in self.files])
