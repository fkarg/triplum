import sqlite3
from pathlib import Path

import pytest

from triplum.cache import Cache, CacheKey, SQLiteBackend
from triplum.cache.admin import cache_stats, clear_cache

P = (b"p" * 32).hex()
Q = (b"q" * 32).hex()


def populate(path: Path) -> None:
    with Cache(SQLiteBackend(path)) as cache:
        cache.put(CacheKey(bytes.fromhex(P), b"a" * 32), b"one")
        cache.put(CacheKey(bytes.fromhex(P), b"b" * 32), b"four")
        cache.put(CacheKey(bytes.fromhex(Q), b"a" * 32), b"five!")


def test_missing_stats_and_clear_do_not_create_database(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "cache.sqlite"
    stats = cache_stats(path, details=True)
    assert not stats.exists
    assert stats.computations == ()
    assert stats.database_bytes == stats.wal_bytes == stats.reusable_bytes == 0
    assert clear_cache(path) == 0
    assert not path.parent.exists()


def test_stats_fast_and_exact_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    populate(path)
    fast = cache_stats(path)
    assert fast.exists and fast.database_bytes > 0
    assert [(row.computation, row.entries, row.payload_bytes) for row in fast.computations] == [
        (P, None, None),
        (Q, None, None),
    ]
    exact = cache_stats(path, details=True)
    assert [(row.computation, row.entries, row.payload_bytes) for row in exact.computations] == [
        (P, 2, 7),
        (Q, 1, 5),
    ]
    assert cache_stats(path, computation=Q, details=True).computations == (exact.computations[1],)


def test_targeted_clear_isolates_computation_and_preserves_other_tables(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    populate(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('keep')")
        connection.commit()
        assert clear_cache(path, computation=P) == 1
        assert [row.computation for row in cache_stats(path).computations] == [Q]
        assert clear_cache(path) == 1
        assert cache_stats(path).computations == ()
        assert connection.execute("SELECT value FROM unrelated").fetchall() == [("keep",)]
        assert path.is_file()
    finally:
        connection.close()


def test_existing_writer_recreates_cleared_table(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    key = CacheKey(bytes.fromhex(P), b"a" * 32)
    with Cache(SQLiteBackend(path)) as cache:
        cache.put(key, b"before")
        cache.flush()
        assert clear_cache(path, computation=P) == 1
        assert cache.get(key) is None
        cache.put(key, b"after")
        cache.flush()
        assert cache.get(key) == b"after"
        assert cache_stats(path, details=True).computations[0].payload_bytes == 5


def test_clear_preserves_unrecognized_table(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE cache_entries (old_value BLOB)")
        connection.execute("INSERT INTO cache_entries VALUES (?)", (b"old",))
        connection.commit()
        assert clear_cache(path) == 0
        assert connection.execute("SELECT old_value FROM cache_entries").fetchall() == [(b"old",)]
    finally:
        connection.close()


@pytest.mark.parametrize("identifier", ["label", "f" * 63, "z" * 64, "abc'; DROP TABLE other;"])
def test_opaque_selector_validation_before_storage_access(tmp_path: Path, identifier: str) -> None:
    path = tmp_path / "missing.sqlite"
    with pytest.raises(ValueError, match="64"):
        cache_stats(path, computation=identifier)
    with pytest.raises(ValueError, match="64"):
        clear_cache(path, computation=identifier)
    assert not path.exists()


def test_unknown_computation_is_not_an_error_or_creation(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    populate(path)
    absent = "a" * 64
    assert cache_stats(path, computation=absent).computations == ()
    assert clear_cache(path, computation=absent) == 0
