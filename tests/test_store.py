import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from triplum.datatype import Chunk, Source
from triplum.steps.chunking import FixedSize
from triplum.store import MemoryStore, RecordStore, SQLAlchemyStore

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")


def _source(origin: str, text: str) -> Source:
    return Source(collection_id=COLLECTION, origin=origin, text=text)


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest) -> RecordStore:
    return MemoryStore() if request.param == "memory" else SQLAlchemyStore()


def test_sources_and_chunks_round_trip(store: RecordStore):
    a = _source("a.md", "abcdefg")
    b = _source("https://example.org", "xy")
    chunks = FixedSize(3)(a)
    store.add_sources([a, b])
    store.add_chunks(reversed(chunks))

    assert store.source(a.id) == a
    assert store.source(b.id) == b
    assert sorted(store.sources(), key=lambda s: s.text) == [a, b]
    assert store.chunks(a.id) == chunks
    assert store.chunks(b.id) == []


def test_re_adding_equal_records_keeps_one_copy(store: RecordStore):
    # Ids are derived from content, so a record with the same id is an equal record.
    a = _source("a", "abc")
    store.add_sources([a])
    store.add_chunks(FixedSize(2)(a))
    store.add_sources([_source("a", "abc")])
    store.add_chunks(FixedSize(2)(_source("a", "abc")))
    assert list(store.sources()) == [a]
    assert store.chunks(a.id) == FixedSize(2)(a)


def test_missing_source_is_a_key_error(store: RecordStore):
    with pytest.raises(KeyError):
        store.source(uuid4())


def test_chunk_needs_its_source_and_nothing_of_the_batch_is_stored(store: RecordStore):
    a = _source("a", "abc")
    store.add_sources([a])
    orphan = Chunk(
        collection_id=COLLECTION, source_id=uuid4(), origin="b", ordinal=0, start=0, text="x"
    )
    with pytest.raises(KeyError):
        store.add_chunks([*FixedSize(2)(a), orphan])
    assert store.chunks(a.id) == []


def test_sql_store_persists_across_instances(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'records.db'}"
    a = _source("a", "abc")
    first = SQLAlchemyStore(url)
    first.add_sources([a])
    first.add_chunks(FixedSize(2)(a))

    second = SQLAlchemyStore(url)
    assert second.source(a.id) == a
    assert [c.text for c in second.chunks(a.id)] == ["ab", "c"]


def test_in_memory_sql_store_is_shared_across_threads():
    store = SQLAlchemyStore()
    a = _source("a", "abc")
    store.add_sources([a])
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(store.source, a.id).result() == a


def test_sql_store_persists_explicit_record_fingerprints(tmp_path: Path):
    path = tmp_path / "records.db"
    source = _source("a.md", "abc")
    chunks = FixedSize(2)(source)
    store = SQLAlchemyStore(f"sqlite:///{path}")
    try:
        store.add_sources([source])
        store.add_chunks(chunks)
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("SELECT fingerprint FROM source").fetchall() == [
                (source.fingerprint(),)
            ]
            assert connection.execute(
                "SELECT fingerprint FROM chunk ORDER BY start"
            ).fetchall() == [(chunk.fingerprint(),) for chunk in chunks]
    finally:
        store.engine.dispose()


def test_sql_rows_that_do_not_match_their_id_are_rejected_on_read(tmp_path: Path):
    path = tmp_path / "records.db"
    source = _source("a.md", "abc")
    store = SQLAlchemyStore(f"sqlite:///{path}")
    try:
        store.add_sources([source])
        store.add_chunks(FixedSize(2)(source))
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE source SET text = 'abd'")
            connection.execute("UPDATE chunk SET ordinal = ordinal + 1")
        with pytest.raises(ValidationError, match="does not match"):
            store.source(source.id)
        with pytest.raises(ValidationError, match="does not match"):
            list(store.sources())
        with pytest.raises(ValidationError, match="does not match"):
            store.chunks(source.id)
    finally:
        store.engine.dispose()
