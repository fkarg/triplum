from pathlib import Path

import pytest

from triplum.cache import CacheKey, SQLiteBackend


def test_persistence_and_full_key_isolation(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    keys = [
        CacheKey(b"p" * 32, b"i" * 32),
        CacheKey(b"q" * 32, b"i" * 32),
        CacheKey(b"p" * 32, b"j" * 32),
    ]
    backend = SQLiteBackend(path)
    assert backend.get(keys[0]) is None
    backend.put_many(list(zip(keys, [b"", b"process", b"input"], strict=True)))
    backend.close()
    reopened = SQLiteBackend(path)
    try:
        assert [reopened.get(key) for key in keys] == [b"", b"process", b"input"]
        reopened.put_many([(keys[0], b"replaced")])
        assert reopened.get(keys[0]) == b"replaced"
    finally:
        reopened.close()


def test_other_connection_sees_committed_writes(tmp_path: Path) -> None:
    first = SQLiteBackend(tmp_path / "cache.sqlite")
    second = SQLiteBackend(tmp_path / "cache.sqlite")
    key = CacheKey(b"p" * 32, b"i" * 32)
    try:
        first.put_many([(key, b"shared")])
        assert second.get(key) == b"shared"
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize("process,input_id", [(b"short", b"i" * 32), (b"p" * 32, b"")])
def test_key_rejects_truncated_digests(process: bytes, input_id: bytes) -> None:
    with pytest.raises(ValueError):
        CacheKey(process, input_id)


def test_one_table_per_computation_with_only_input_as_row_key(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "cache.sqlite"
    backend = SQLiteBackend(path)
    key = CacheKey(b"p" * 32, b"i" * 32)
    connection = sqlite3.connect(path)
    try:
        assert backend.get(key) is None
        assert (
            connection.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall() == []
        )
        backend.put_many([(key, b"value")])
        tables = connection.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
        assert tables == [("cache_" + (b"p" * 32).hex(),)]
        columns = connection.execute(f'PRAGMA table_info("{tables[0][0]}")').fetchall()
        assert [(column[1], column[5]) for column in columns] == [("input", 1), ("value", 0)]
    finally:
        backend.close()
        connection.close()
