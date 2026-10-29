import sqlite3
from collections.abc import Callable, Iterator
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
def store(request: pytest.FixtureRequest) -> Iterator[RecordStore]:
    if request.param == "memory":
        yield MemoryStore()
        return
    sql = SQLAlchemyStore()
    yield sql
    sql.close()


def test_sources_and_chunks_round_trip(store: RecordStore):
    a = _source("a.md", "abcdefg")
    b = _source("https://example.org", "xy")
    chunks = FixedSize(3)(a)
    store.add_sources([a, b])
    store.replace_chunks(a.id, iter(chunks))

    assert store.source(a.id) == a
    assert store.source(b.id) == b
    assert sorted(store.sources(), key=lambda s: s.text) == [a, b]
    assert store.chunks(a.id) == chunks
    assert store.chunks(b.id) == []


def test_re_adding_equal_records_keeps_one_copy(store: RecordStore):
    # Ids are derived from content, so a record with the same id is normally an equal record.
    a = _source("a", "abc")
    store.add_sources([a, _source("a", "abc")])
    store.replace_chunks(a.id, FixedSize(2)(a))
    store.add_sources([_source("a", "abc")])
    store.replace_chunks(a.id, FixedSize(2)(_source("a", "abc")))
    assert list(store.sources()) == [a]
    assert store.chunks(a.id) == FixedSize(2)(a)


def test_a_different_source_under_a_known_id_is_rejected(store: RecordStore):
    a = _source("a", "abc")
    b = _source("b", "xyz")
    stale = a.model_copy(update={"text": "abd"})  # skips validation, so keeps a's id
    store.add_sources([a])
    with pytest.raises(ValueError, match="different source"):
        store.add_sources([b, stale])
    c = _source("c", "123")
    with pytest.raises(ValueError, match="different source"):
        store.add_sources([c, c.model_copy(update={"text": "124"})])
    assert list(store.sources()) == [a]


def test_changing_the_chunker_replaces_a_sources_chunks(store: RecordStore):
    a = _source("a", "abcdef")
    b = _source("b", "uvwxyz")
    store.add_sources([a, b])
    store.replace_chunks(a.id, FixedSize(2)(a))
    store.replace_chunks(b.id, FixedSize(2)(b))
    store.replace_chunks(a.id, FixedSize(4)(a))
    assert [c.text for c in store.chunks(a.id)] == ["abcd", "ef"]
    assert store.chunks(b.id) == FixedSize(2)(b)
    store.replace_chunks(a.id, [])
    assert store.chunks(a.id) == []
    assert store.source(a.id) == a


def test_chunks_are_returned_in_ordinal_order(store: RecordStore):
    a = _source("a", "abcd")
    later_first = [_chunk(a, 0, 2, "cd"), _chunk(a, 1, 0, "ab")]
    store.add_sources([a])
    store.replace_chunks(a.id, later_first)
    assert store.chunks(a.id) == later_first


def test_missing_source_is_a_key_error(store: RecordStore):
    with pytest.raises(KeyError):
        store.source(uuid4())


def test_replacing_chunks_needs_a_stored_source(store: RecordStore):
    def failing() -> Iterator[Chunk]:
        raise RuntimeError("must not be consumed")
        yield

    with pytest.raises(KeyError):
        store.replace_chunks(uuid4(), failing())


def _chunk(source: Source, ordinal: int, start: int, text: str, **fields: object) -> Chunk:
    return Chunk.model_validate(
        {
            "collection_id": source.collection_id,
            "source_id": source.id,
            "origin": source.origin,
            "ordinal": ordinal,
            "start": start,
            "text": text,
        }
        | fields
    )


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda s, o: _chunk(o, 0, 0, "ab"), "does not belong"),
        (lambda s, o: _chunk(s, 0, 0, "ab", origin="elsewhere"), "does not belong"),
        (lambda s, o: _chunk(s, 0, 0, "ab", collection_id=uuid4()), "does not belong"),
        (lambda s, o: _chunk(s, 1, 0, "ab"), "ordinal"),
        (lambda s, o: _chunk(s, 0, 99, ""), "slice"),
        (lambda s, o: _chunk(s, 0, 0, "xx"), "slice"),
        (lambda s, o: _chunk(s, 0, 0, "").model_copy(update={"start": -1}), "slice"),
    ],
)
def test_invalid_chunks_raise_and_keep_the_previous_chunks(
    store: RecordStore, make: Callable[[Source, Source], Chunk], message: str
):
    a = _source("a", "abc")
    other = _source("other", "abc")
    store.add_sources([a, other])
    previous = FixedSize(2)(a)
    store.replace_chunks(a.id, previous)
    with pytest.raises(ValueError, match=message):
        store.replace_chunks(a.id, [make(a, other)])
    assert store.chunks(a.id) == previous


def test_a_different_chunk_under_a_stored_id_is_rejected(store: RecordStore):
    a = _source("a", "abc")
    store.add_sources([a])
    first = FixedSize(2)(a)
    store.replace_chunks(a.id, first)
    stale = first[0].model_copy(update={"start": 1, "text": "bc"})  # keeps the stored id
    with pytest.raises(ValueError, match="different chunk"):
        store.replace_chunks(a.id, [stale])
    assert store.chunks(a.id) == first


def test_a_chunk_under_another_sources_stored_id_is_rejected(store: RecordStore):
    a = _source("a", "abc")
    b = _source("b", "abc")
    store.add_sources([a, b])
    store.replace_chunks(a.id, FixedSize(3)(a))
    taken = FixedSize(3)(b)[0].model_copy(update={"id": store.chunks(a.id)[0].id})
    with pytest.raises(ValueError, match="different chunk"):
        store.replace_chunks(b.id, [taken])
    assert store.chunks(a.id) == FixedSize(3)(a)
    assert store.chunks(b.id) == []


def test_a_failing_source_iterable_stores_nothing(store: RecordStore):
    def failing() -> Iterator[Source]:
        yield _source("a", "abc")
        raise RuntimeError("loader failed")

    with pytest.raises(RuntimeError):
        store.add_sources(failing())
    assert list(store.sources()) == []


def test_a_failing_chunk_iterable_keeps_the_previous_chunks(store: RecordStore):
    a = _source("a", "abc")
    store.add_sources([a])
    previous = FixedSize(2)(a)
    store.replace_chunks(a.id, previous)

    def failing() -> Iterator[Chunk]:
        yield FixedSize(3)(a)[0]
        raise RuntimeError("chunker failed")

    with pytest.raises(RuntimeError):
        store.replace_chunks(a.id, failing())
    assert store.chunks(a.id) == previous


def test_sql_store_persists_across_instances(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'records.db'}"
    a = _source("a", "abc")
    with closing(SQLAlchemyStore(url)) as first:
        first.add_sources([a])
        first.replace_chunks(a.id, FixedSize(2)(a))
    with closing(SQLAlchemyStore(url)) as second:
        assert second.source(a.id) == a
        assert [c.text for c in second.chunks(a.id)] == ["ab", "c"]


def test_in_memory_sql_store_is_shared_across_threads():
    a = _source("a", "abc")
    with closing(SQLAlchemyStore()) as store, ThreadPoolExecutor(1) as pool:
        store.add_sources([a])
        assert pool.submit(store.source, a.id).result() == a


def test_sql_store_persists_explicit_record_fingerprints(tmp_path: Path):
    path = tmp_path / "records.db"
    source = _source("a.md", "abc")
    chunks = FixedSize(2)(source)
    store = SQLAlchemyStore(f"sqlite:///{path}")
    try:
        store.add_sources([source])
        store.replace_chunks(source.id, chunks)
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("SELECT fingerprint FROM source").fetchall() == [
                (source.fingerprint(),)
            ]
            assert connection.execute(
                "SELECT fingerprint FROM chunk ORDER BY start"
            ).fetchall() == [(chunk.fingerprint(),) for chunk in chunks]
    finally:
        store.close()


def test_sql_rows_that_do_not_match_their_id_are_rejected_on_read(tmp_path: Path):
    path = tmp_path / "records.db"
    source = _source("a.md", "abc")
    store = SQLAlchemyStore(f"sqlite:///{path}")
    try:
        store.add_sources([source])
        store.replace_chunks(source.id, FixedSize(2)(source))
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
        store.close()
