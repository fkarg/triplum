"""Canonical JSON and SHA-256 content identity helpers; no storage or I/O."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_key(kind: str, payload: Any) -> str:
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"\0")
    h.update(canonical_json(payload).encode())
    return h.hexdigest()
