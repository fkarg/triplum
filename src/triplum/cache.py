"""Content-addressed disk cache shared by LLM, embedder and reranker adapters.

Keys are sha256 over (kind, canonical JSON payload). One file per entry, sharded by the first two
hex characters. The cache is per machine (design D6a); nothing requires it to exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_key(kind: str, payload: Any) -> str:
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"\0")
    h.update(canonical_json(payload).encode())
    return h.hexdigest()


def default_root() -> Path:
    from triplum.settings import Settings

    return Settings().cache


class Cache:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / key

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.parent / f"{key}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def get_json(self, key: str) -> Any | None:
        raw = self.get(key)
        return None if raw is None else json.loads(raw)

    def put_json(self, key: str, obj: Any) -> None:
        self.put(key, canonical_json(obj).encode())
