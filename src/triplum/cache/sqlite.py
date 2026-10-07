"""SQLite storage for exact compound-key lookups and batched writes."""

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from threading import Lock

from triplum.cache.protocols import CacheBackend, CacheKey


class SQLiteBackend(CacheBackend):
    """A persistent WAL database with separate, serialized reader/writer connections.

    Supply a local filesystem path, not a SQLite URI or in-memory database. The caller
    owns the containing directory. timeout bounds SQLite lock contention, not queue
    admission. Multiple owners may share the file; their pending writes are private.
    """

    def __init__(self, path: str | Path, *, timeout: float = 30.0) -> None:
        self._read_lock = Lock()
        self._write_lock = Lock()
        self._writer = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
        try:
            mode = self._writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode != "wal":
                raise ValueError("SQLite cache requires a filesystem database supporting WAL")
            self._writer.execute(
                "CREATE TABLE IF NOT EXISTS cache_entries ("
                "process BLOB NOT NULL, input BLOB NOT NULL, format TEXT NOT NULL, "
                "value BLOB NOT NULL, PRIMARY KEY (process, input, format))"
            )
            self._writer.commit()
            self._reader = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
        except BaseException:
            self._writer.close()
            raise

    def get(self, key: CacheKey, /) -> bytes | None:
        """Fetch one complete value; None denotes absence, including for empty bytes."""
        with self._read_lock:
            row = self._reader.execute(
                "SELECT value FROM cache_entries WHERE process=? AND input=? AND format=?",
                (key.process, key.input, key.format),
            ).fetchone()
            return None if row is None else row[0]

    def put_many(self, entries: Sequence[tuple[CacheKey, bytes]], /) -> None:
        """Commit a FIFO batch; later writes to the same key replace earlier ones."""
        with self._write_lock, self._writer:
            self._writer.execute("BEGIN IMMEDIATE")
            self._writer.executemany(
                "INSERT INTO cache_entries (process, input, format, value) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (process, input, format) DO UPDATE SET value=excluded.value",
                ((key.process, key.input, key.format, value) for key, value in entries),
            )

    def close(self) -> None:
        """Close connections after the owning Cache has drained its writer."""
        with self._write_lock, self._read_lock:
            self._writer.close()
            self._reader.close()
