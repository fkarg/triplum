"""Principal tokens for FTS5 and principal-set hashes for vec0 partitions."""

from __future__ import annotations

import hashlib
from typing import Iterable


def principal_token(principal: str) -> str:
    """Alphanumeric token safe for the unicode61 tokenizer."""
    return "p" + hashlib.sha256(principal.encode()).hexdigest()[:20]


def acl_hash(principals: Iterable[str]) -> str:
    """Hash of the sorted active principal set of a document."""
    joined = "\0".join(sorted(set(principals)))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def acl_tokens(principals: Iterable[str]) -> str:
    return " ".join(principal_token(p) for p in sorted(set(principals)))
