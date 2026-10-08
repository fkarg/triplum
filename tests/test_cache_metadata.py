"""Names label computation variants without changing cache identity."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from triplum.cache import Cache, CacheKey, SQLiteBackend, cached
from triplum.cache.admin import cache_stats, clear_cache
from triplum.datatype import FingerprintedDataModel


class Text(FingerprintedDataModel):
    text: str


def normalize(value: Text) -> Text:
    return Text(text=value.text.lower())


def unrelated(value: Text) -> Text:
    return value


def populate(path: Path) -> None:
    with Cache(SQLiteBackend(path)) as cache:
        for digest in ("a" * 64, "b" * 64):
            assert cached(normalize, cache=cache, process_id=digest)(Text(text="HELLO")) == Text(
                text="hello"
            )
        cached(unrelated, cache=cache, process_id="c" * 64)(Text(text="other"))
        cache.put(CacheKey(bytes.fromhex("d" * 64), b"i" * 32), b"manual")


def test_names_locations_and_clear_across_all_fingerprints(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    populate(path)
    name = f"{normalize.__module__}.{normalize.__qualname__}"
    rows = cache_stats(path, details=True).computations
    assert [(row.name, row.source_path, row.source_line) for row in rows[:2]] == [
        (name, normalize.__code__.co_filename, normalize.__code__.co_firstlineno),
    ] * 2
    assert rows[-1].name is None
    assert len(cache_stats(path, name=name).computations) == 2
    assert clear_cache(path, name=name) == 2
    remaining = cache_stats(path, details=True).computations
    assert [row.computation for row in remaining] == ["c" * 64, "d" * 64]
    assert clear_cache(path, name=name) == 0


def test_metadata_does_not_change_keys_and_first_location_is_retained(tmp_path: Path) -> None:
    from triplum.cache import ComputationMetadata

    path = tmp_path / "cache.sqlite"
    old = ComputationMetadata("app.normalize", "old.py", 10)
    new = ComputationMetadata("app.normalize", "new.py", 20)
    first = CacheKey(b"a" * 32, b"i" * 32, metadata=old)
    second = CacheKey(b"a" * 32, b"i" * 32, metadata=new)
    assert first == second == CacheKey(b"a" * 32, b"i" * 32)
    assert hash(first) == hash(second)
    with Cache(SQLiteBackend(path)) as cache:
        cache.put(first, b"first")
        assert cache.get(second) == b"first"
        cache.flush()
        cache.put(second, b"second")
    row = cache_stats(path).computations[0]
    assert (row.name, row.source_path, row.source_line) == ("app.normalize", "old.py", 10)
    assert clear_cache(path) == 1
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT COUNT(*) FROM cache_computations").fetchone() == (0,)
    # A live writer can recreate both the result table and its descriptive metadata.
    with Cache(SQLiteBackend(path)) as cache:
        cache.put(second, b"again")
    assert cache_stats(path).computations[0].source_path == "new.py"


def test_cli_name_selection_details_and_ambiguity(tmp_path: Path, capsys) -> None:
    from triplum.cli import main

    path = tmp_path / "cache.sqlite"
    populate(path)
    assert main(["cache", "stats", "--path", str(path), "--details"]) == 0
    output = capsys.readouterr().out
    assert f"{normalize.__module__}.{normalize.__qualname__}" in output
    assert f"{normalize.__code__.co_filename}:{normalize.__code__.co_firstlineno}" in output
    with pytest.raises(SystemExit) as error:
        main(["cache", "clear", "--path", str(path), "--name", "test_cache_metadata"])
    assert error.value.code == 2
    assert "ambiguous" in capsys.readouterr().err
    assert len(cache_stats(path).computations) == 4
    assert main(["cache", "clear", "--path", str(path), "--name", "normalize", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"cleared_computations": 2}
    with pytest.raises(SystemExit):
        main(["cache", "clear", "--path", str(path), "--name", "unknown"])
    assert "choices:" in capsys.readouterr().err


def test_legacy_cache_without_metadata_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(f"CREATE TABLE cache_{'a' * 64} (input BLOB PRIMARY KEY, value BLOB)")
        connection.execute(f"INSERT INTO cache_{'a' * 64} VALUES (?, ?)", (b"i" * 32, b"old"))
    assert cache_stats(path, details=True).computations[0].name is None
    assert clear_cache(path, name="app.normalize") == 0
    assert clear_cache(path) == 1


def test_names_and_fingerprints_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="either"):
        cache_stats(tmp_path / "missing", computation="a" * 64, name="app.normalize")
    with pytest.raises(ValueError, match="either"):
        clear_cache(tmp_path / "missing", computation="a" * 64, name="app.normalize")


def test_cached_step_records_its_compute_method(tmp_path: Path) -> None:
    from triplum.cache import CachedStep

    class Normalize(CachedStep[Text, Text]):
        def fingerprint_config(self) -> dict[str, object]:
            return {}

        def compute(self, value: Text) -> Text:
            return normalize(value)

    path = tmp_path / "step.sqlite"
    with Cache(SQLiteBackend(path)) as cache:
        assert Normalize(cache=cache)(Text(text="HELLO")) == Text(text="hello")
    row = cache_stats(path).computations[0]
    assert row.name == f"{Normalize.compute.__module__}.{Normalize.compute.__qualname__}"
    assert row.source_line == Normalize.compute.__code__.co_firstlineno


def test_synthetic_source_location_is_optional() -> None:
    from triplum.cache import ComputationMetadata

    namespace = {"__name__": "dynamic_example"}
    exec(compile("def transform(value): return value", "<generated>", "exec"), namespace)  # noqa: S102 - controlled fixture
    assert ComputationMetadata.from_callable(namespace["transform"]) == ComputationMetadata(
        "dynamic_example.transform"
    )
