import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from triplum.datatype import Chunk, Source, Viewer
from triplum.steps.chunking import FixedSize
from triplum.store import MemoryStore, RecordStore, SQLAlchemyStore

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")
OTHER = UUID("01900000-0000-7000-8000-000000000002")
PUBLIC = Viewer(principals=frozenset({"public"}))


def _source(origin: str, text: str, external_id: str | None = None) -> Source:
    return Source(collection_id=COLLECTION, origin=origin, text=text, external_id=external_id)


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
    store.add_sources([a, b], allow=["public"])
    store.replace_chunks(a.id, iter(chunks))

    assert store.source(a.id, viewer=PUBLIC) == a
    assert store.source(b.id, viewer=PUBLIC) == b
    assert sorted(store.sources(collection_id=COLLECTION, viewer=PUBLIC), key=lambda s: s.text) == [
        a,
        b,
    ]
    assert store.chunks(a.id, viewer=PUBLIC) == chunks
    assert store.chunks(b.id, viewer=PUBLIC) == []


def test_re_adding_equal_records_keeps_one_copy(store: RecordStore):
    # Ids are derived from content, so a record with the same id is normally an equal record.
    a = _source("a", "abc")
    store.add_sources([a, _source("a", "abc")], allow=["public"])
    store.replace_chunks(a.id, FixedSize(2)(a))
    store.add_sources([_source("a", "abc")], allow=["public"])
    store.replace_chunks(a.id, FixedSize(2)(_source("a", "abc")))
    assert list(store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == [a]
    assert store.chunks(a.id, viewer=PUBLIC) == FixedSize(2)(a)


def test_a_different_source_under_a_known_id_is_rejected(store: RecordStore):
    a = _source("a", "abc")
    b = _source("b", "xyz")
    stale = a.model_copy(update={"text": "abd"})  # skips validation, so keeps a's id
    store.add_sources([a], allow=["public"])
    with pytest.raises(ValueError, match="different source"):
        store.add_sources([b, stale], allow=["public"])
    c = _source("c", "123")
    with pytest.raises(ValueError, match="different source"):
        store.add_sources([c, c.model_copy(update={"text": "124"})], allow=["public"])
    assert list(store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == [a]


def test_changing_the_chunker_replaces_a_sources_chunks(store: RecordStore):
    a = _source("a", "abcdef")
    b = _source("b", "uvwxyz")
    store.add_sources([a, b], allow=["public"])
    store.replace_chunks(a.id, FixedSize(2)(a))
    store.replace_chunks(b.id, FixedSize(2)(b))
    store.replace_chunks(a.id, FixedSize(4)(a))
    assert [c.text for c in store.chunks(a.id, viewer=PUBLIC)] == ["abcd", "ef"]
    assert store.chunks(b.id, viewer=PUBLIC) == FixedSize(2)(b)
    store.replace_chunks(a.id, [])
    assert store.chunks(a.id, viewer=PUBLIC) == []
    assert store.source(a.id, viewer=PUBLIC) == a


def test_chunks_are_returned_in_ordinal_order(store: RecordStore):
    a = _source("a", "abcd")
    later_first = [_chunk(a, 0, 2, "cd"), _chunk(a, 1, 0, "ab")]
    store.add_sources([a], allow=["public"])
    store.replace_chunks(a.id, later_first)
    assert store.chunks(a.id, viewer=PUBLIC) == later_first


def test_missing_source_is_a_key_error(store: RecordStore):
    with pytest.raises(KeyError):
        store.source(uuid4(), viewer=PUBLIC)


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
    store.add_sources([a, other], allow=["public"])
    previous = FixedSize(2)(a)
    store.replace_chunks(a.id, previous)
    with pytest.raises(ValueError, match=message):
        store.replace_chunks(a.id, [make(a, other)])
    assert store.chunks(a.id, viewer=PUBLIC) == previous


def test_a_different_chunk_under_a_stored_id_is_rejected(store: RecordStore):
    a = _source("a", "abc")
    store.add_sources([a], allow=["public"])
    first = FixedSize(2)(a)
    store.replace_chunks(a.id, first)
    stale = first[0].model_copy(update={"start": 1, "text": "bc"})  # keeps the stored id
    with pytest.raises(ValueError, match="different chunk"):
        store.replace_chunks(a.id, [stale])
    assert store.chunks(a.id, viewer=PUBLIC) == first


def test_a_chunk_under_another_sources_stored_id_is_rejected(store: RecordStore):
    a = _source("a", "abc")
    b = _source("b", "abc")
    store.add_sources([a, b], allow=["public"])
    store.replace_chunks(a.id, FixedSize(3)(a))
    taken = FixedSize(3)(b)[0].model_copy(update={"id": store.chunks(a.id, viewer=PUBLIC)[0].id})
    with pytest.raises(ValueError, match="different chunk"):
        store.replace_chunks(b.id, [taken])
    assert store.chunks(a.id, viewer=PUBLIC) == FixedSize(3)(a)
    assert store.chunks(b.id, viewer=PUBLIC) == []


def test_an_external_id_is_unique_within_its_collection(store: RecordStore):
    held = _source("a", "abc", "d1")
    store.add_sources([held], allow=["public"])
    fresh = _source("b", "xyz")
    clash = _source("c", "other", "d1")
    with pytest.raises(ValueError, match="'d1' is already held"):
        store.add_sources([fresh, clash], allow=["public"])
    within = _source("e", "e", "d2")
    with pytest.raises(ValueError, match="'d2' is already held"):
        store.add_sources(
            [within, _source("f", "f", "d2")],
            allow=["public"],
        )
    assert list(store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == [held]

    elsewhere = Source(collection_id=OTHER, origin="c", text="other", external_id="d1")
    unset = [_source("g", "1"), _source("h", "2")]
    store.add_sources([held, elsewhere, *unset], allow=["public"])  # an equal re-add is not a clash
    assert sorted(s.origin for s in store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == [
        "a",
        "g",
        "h",
    ]
    assert list(store.sources(collection_id=OTHER, viewer=PUBLIC)) == [elsewhere]


def test_the_same_source_with_another_external_id_is_rejected(store: RecordStore):
    unset = _source("a", "abc")
    store.add_sources([unset], allow=["public"])
    keyed = _source("a", "abc", "d1")
    assert keyed.id == unset.id
    with pytest.raises(ValueError, match="different source"):
        store.add_sources([keyed], allow=["public"])


def test_an_unreadable_source_looks_missing(store: RecordStore):
    public, team = _source("p", "pub"), _source("t", "team")
    store.add_sources([public], allow=["public"])
    store.add_sources([team], allow=["team", "admins"])
    store.replace_chunks(team.id, FixedSize(2)(team))
    missing = uuid4()

    def error(read: Callable[[], object]) -> tuple:
        with pytest.raises(KeyError) as raised:
            read()
        return raised.value.args

    assert error(lambda: store.source(team.id, viewer=PUBLIC)) == (team.id,)
    assert error(lambda: store.chunks(team.id, viewer=PUBLIC)) == (team.id,)
    assert error(lambda: store.chunks(missing, viewer=PUBLIC)) == (missing,)
    assert list(store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == [public]

    both = Viewer(principals=frozenset({"public", "team", "admins"}))
    assert sorted(store.sources(collection_id=COLLECTION, viewer=both), key=lambda s: s.text) == [
        public,
        team,
    ]
    assert store.chunks(team.id, viewer=both) == FixedSize(2)(team)
    assert (
        list(store.sources(collection_id=COLLECTION, viewer=Viewer(principals=frozenset()))) == []
    )


def test_a_bare_string_is_not_a_set_of_principals(store: RecordStore):
    # A str is an Iterable[str]: "team" used to allow the principals "t", "e", "a" and "m".
    with pytest.raises(TypeError, match="not the string 'team'"):
        store.add_sources([_source("a", "abc")], allow="team")
    assert (
        list(
            store.sources(
                collection_id=COLLECTION, viewer=Viewer(principals=frozenset({"t", "team"}))
            )
        )
        == []
    )


def test_a_source_nobody_may_read(store: RecordStore):
    hidden = _source("h", "hidden")
    store.add_sources([hidden], allow=[])
    everyone = Viewer(principals=frozenset({"public", "team"}))
    assert list(store.sources(collection_id=COLLECTION, viewer=everyone)) == []
    with pytest.raises(KeyError):
        store.source(hidden.id, viewer=everyone)


def test_re_adding_a_source_with_other_access_is_rejected(store: RecordStore):
    a = _source("a", "abc")
    store.add_sources([a], allow=["team", "public"])
    store.add_sources([a], allow=["public", "team", "team"])  # same set: no change
    fresh = _source("b", "new")
    with pytest.raises(ValueError, match="other access"):
        store.add_sources([fresh, a], allow=["public"])
    assert list(
        store.sources(
            collection_id=COLLECTION, viewer=Viewer(principals=frozenset({"public", "team"}))
        )
    ) == [a]
    assert list(
        store.sources(collection_id=COLLECTION, viewer=Viewer(principals=frozenset({"team"})))
    ) == [a]


def test_a_failing_source_iterable_stores_nothing(store: RecordStore):
    def failing() -> Iterator[Source]:
        yield _source("a", "abc")
        raise RuntimeError("loader failed")

    with pytest.raises(RuntimeError):
        store.add_sources(failing(), allow=["public"])
    assert list(store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == []


def test_a_failing_chunk_iterable_keeps_the_previous_chunks(store: RecordStore):
    a = _source("a", "abc")
    store.add_sources([a], allow=["public"])
    previous = FixedSize(2)(a)
    store.replace_chunks(a.id, previous)

    def failing() -> Iterator[Chunk]:
        yield FixedSize(3)(a)[0]
        raise RuntimeError("chunker failed")

    with pytest.raises(RuntimeError):
        store.replace_chunks(a.id, failing())
    assert store.chunks(a.id, viewer=PUBLIC) == previous


def test_sql_store_persists_across_instances(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'records.db'}"
    a = _source("a", "abc", "d1")
    with closing(SQLAlchemyStore(url)) as first:
        first.add_sources([a], allow=["public"])
        first.replace_chunks(a.id, FixedSize(2)(a))
    with closing(SQLAlchemyStore(url)) as second:
        assert second.source(a.id, viewer=PUBLIC) == a
        assert [c.text for c in second.chunks(a.id, viewer=PUBLIC)] == ["ab", "c"]


def test_in_memory_sql_store_is_shared_across_threads():
    a = _source("a", "abc")
    with closing(SQLAlchemyStore()) as store, ThreadPoolExecutor(1) as pool:
        store.add_sources([a], allow=["public"])
        assert pool.submit(store.source, a.id, viewer=PUBLIC).result() == a


def test_sql_store_persists_explicit_record_fingerprints(tmp_path: Path):
    path = tmp_path / "records.db"
    source = _source("a.md", "abc")
    chunks = FixedSize(2)(source)
    store = SQLAlchemyStore(f"sqlite:///{path}")
    try:
        store.add_sources([source], allow=["public"])
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
        store.add_sources([source], allow=["public"])
        store.replace_chunks(source.id, FixedSize(2)(source))
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE source SET text = 'abd'")
            connection.execute("UPDATE chunk SET ordinal = ordinal + 1")
        with pytest.raises(ValidationError, match="does not match"):
            store.source(source.id, viewer=PUBLIC)
        with pytest.raises(ValidationError, match="does not match"):
            list(store.sources(collection_id=COLLECTION, viewer=PUBLIC))
        with pytest.raises(ValidationError, match="does not match"):
            store.chunks(source.id, viewer=PUBLIC)
    finally:
        store.close()


def test_sql_access_is_checked_before_a_row_is_read(tmp_path: Path):
    path = tmp_path / "records.db"
    hidden = _source("a.md", "abc")
    store = SQLAlchemyStore(f"sqlite:///{path}")
    try:
        store.add_sources([hidden], allow=["team"])
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE source SET text = 'abd'")
        # A corrupt row the viewer may not read must not fail differently from a missing one.
        with pytest.raises(KeyError):
            store.source(hidden.id, viewer=PUBLIC)
        with pytest.raises(KeyError):
            store.chunks(hidden.id, viewer=PUBLIC)
        assert list(store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == []
    finally:
        store.close()


def test_sql_writes_respect_foreign_keys(tmp_path: Path):
    # Access rows were flushed before their source rows, failing wherever foreign keys are
    # enforced (always on PostgreSQL); SQLite enforces them only with this pragma.
    store = SQLAlchemyStore(f"sqlite:///{tmp_path / 'records.db'}")
    event.listen(store.engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    store.engine.dispose()  # drop the connection opened before the listener existed
    try:
        a = _source("a", "abc")
        store.add_sources([a], allow=["public", "team"])
        store.replace_chunks(a.id, FixedSize(2)(a))
        assert store.chunks(a.id, viewer=PUBLIC) == FixedSize(2)(a)
        with store.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        store.close()


def test_sources_lists_one_collections_readable_sources(store: RecordStore):
    # Owner (Q33): a sources query selects a collection; access still applies within it.
    mine, mine_hidden = _source("a", "a"), _source("b", "b")
    theirs = Source(collection_id=OTHER, origin="a", text="a")
    theirs_hidden = Source(collection_id=OTHER, origin="b", text="b")
    store.add_sources([mine, theirs], allow=["public"])
    store.add_sources([mine_hidden, theirs_hidden], allow=["team"])
    assert list(store.sources(collection_id=COLLECTION, viewer=PUBLIC)) == [mine]
    assert list(store.sources(collection_id=OTHER, viewer=PUBLIC)) == [theirs]
    team = Viewer(principals=frozenset({"team"}))
    assert list(store.sources(collection_id=OTHER, viewer=team)) == [theirs_hidden]
    unknown = UUID("01900000-0000-7000-8000-000000000009")
    assert list(store.sources(collection_id=unknown, viewer=PUBLIC)) == []


def test_reads_without_a_viewer_do_not_filter_by_access(store: RecordStore):
    # Owner (2026-11-08): access control is deferred; an omitted viewer reads everything.
    public, team, nobody = _source("p", "pub"), _source("t", "team"), _source("n", "none")
    store.add_sources([public], allow=["public"])
    store.add_sources([team], allow=["team"])
    store.add_sources([nobody], allow=[])
    store.replace_chunks(team.id, FixedSize(2)(team))
    assert sorted(store.sources(collection_id=COLLECTION), key=lambda s: s.text) == [
        nobody,
        public,
        team,
    ]
    assert store.source(nobody.id) == nobody
    assert store.chunks(team.id) == FixedSize(2)(team)
    with pytest.raises(KeyError):
        store.source(uuid4())
