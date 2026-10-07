"""Inspect and clear committed SQLite cache entries without opening a cache owner."""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from triplum.cache.defaults import default_cache_path


@dataclass(frozen=True)
class ComputationStats:
    computation: str
    entries: int | None
    payload_bytes: int | None


@dataclass(frozen=True)
class CacheStats:
    path: Path
    exists: bool
    database_bytes: int
    wal_bytes: int
    reusable_bytes: int
    computations: tuple[ComputationStats, ...]


def _selector(computation: str | None) -> str | None:
    if computation is None:
        return None
    if re.fullmatch(r"[0-9a-fA-F]{64}", computation) is None:
        raise ValueError("computation must be a full 64-character hexadecimal fingerprint")
    return "cache_" + computation.lower()


def _tables(connection: sqlite3.Connection, selected: str | None) -> list[str]:
    return [
        name
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        )
        if re.fullmatch(r"cache_[0-9a-f]{64}", name) and (selected is None or name == selected)
    ]


def cache_stats(
    path: str | Path | None = None, *, computation: str | None = None, details: bool = False
) -> CacheStats:
    """Inspect committed tables; details scans entries for exact counts/payload bytes.

    File sizes are observations, not transactionally coupled to the table snapshot.
    Runtime hits, skipped writes and other owners' pending entries are unavailable.
    SQLite may create WAL/SHM sidecars, requiring a writable containing directory
    when those files do not already exist, even with this read-only connection.
    """
    selected = _selector(computation)
    resolved = default_cache_path() if path is None else Path(path)
    if not resolved.exists():
        return CacheStats(resolved, False, 0, 0, 0, ())
    connection = sqlite3.connect(resolved.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("BEGIN")
        rows = []
        for table in _tables(connection, selected):
            entries, payload_bytes = None, None
            if details:
                entries, payload_bytes = connection.execute(
                    f'SELECT COUNT(*), COALESCE(SUM(length(value)), 0) FROM "{table}"'
                ).fetchone()
            rows.append(ComputationStats(table.removeprefix("cache_"), entries, payload_bytes))
        reusable = (
            connection.execute("PRAGMA freelist_count").fetchone()[0]
            * connection.execute("PRAGMA page_size").fetchone()[0]
        )
        try:
            wal_bytes = Path(str(resolved) + "-wal").stat().st_size
        except FileNotFoundError:
            wal_bytes = 0
        return CacheStats(resolved, True, resolved.stat().st_size, wal_bytes, reusable, tuple(rows))
    finally:
        connection.close()


def clear_cache(path: str | Path | None = None, *, computation: str | None = None) -> int:
    """Drop selected committed tables and return their count.

    Freed pages are reusable; the file is not unlinked or vacuumed. Active owners may
    repopulate tables immediately. Stop writers first for a lasting empty cache.
    Only computation tables are recognized; unrelated and former tables are preserved.
    """
    selected = _selector(computation)
    resolved = default_cache_path() if path is None else Path(path)
    if not resolved.exists():
        return 0
    connection = sqlite3.connect(resolved.resolve().as_uri() + "?mode=rw", uri=True, timeout=30.0)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            tables = _tables(connection, selected)
            for table in tables:
                connection.execute(f'DROP TABLE "{table}"')
        return len(tables)
    finally:
        connection.close()
