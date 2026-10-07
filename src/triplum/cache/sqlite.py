"""SQLite storage with one input-keyed table per computation fingerprint."""

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
    A lock timeout is a storage error and makes its owning Cache fail until closed;
    it is not a skipped write. Set timeout for expected writer contention.
    """

    def __init__(self, path: str | Path, *, timeout: float = 30.0) -> None:
        self._read_lock = Lock()
        self._write_lock = Lock()
        self._writer = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
        try:
            mode = self._writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode != "wal":
                raise ValueError("SQLite cache requires a filesystem database supporting WAL")
            self._reader = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
        except BaseException:
            self._writer.close()
            raise

    def get(self, key: CacheKey, /) -> bytes | None:
        """Lookup by input ID in the computation table; absent tables are misses."""
        table = "cache_" + key.process.hex()
        with self._read_lock:
            try:
                row = self._reader.execute(
                    f'SELECT value FROM "{table}" WHERE input=?', (key.input,)
                ).fetchone()
            except sqlite3.OperationalError as error:
                if str(error) == f"no such table: {table}":
                    return None
                raise
            return None if row is None else row[0]

    def put_many(self, entries: Sequence[tuple[CacheKey, bytes]], /) -> None:
        """Commit a batch, creating/recreating computation tables as needed.

        Table names contain only validated digest hex. Inputs and payloads are bound
        SQL parameters. All writes still share SQLite's single-writer transaction.
        """
        groups: dict[bytes, list[tuple[bytes, bytes]]] = {}
        for key, value in entries:
            groups.setdefault(key.process, []).append((key.input, value))
        with self._write_lock, self._writer:
            self._writer.execute("BEGIN IMMEDIATE")
            for process, values in groups.items():
                table = "cache_" + process.hex()
                self._writer.execute(
                    f'CREATE TABLE IF NOT EXISTS "{table}" ('
                    "input BLOB NOT NULL PRIMARY KEY, value BLOB NOT NULL)"
                )
                self._writer.executemany(
                    f'INSERT INTO "{table}" (input, value) VALUES (?, ?) '
                    "ON CONFLICT (input) DO UPDATE SET value=excluded.value",
                    values,
                )

    def close(self) -> None:
        """Close connections after the owning Cache has drained its writer."""
        with self._write_lock, self._read_lock:
            self._writer.close()
            self._reader.close()
