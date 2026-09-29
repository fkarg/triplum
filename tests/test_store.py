from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from triplum.datatype import Chunk, Source
from triplum.steps.chunking import FixedSize
from triplum.store import MemoryStore, RecordStore, SQLAlchemyStore


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest) -> RecordStore:
    return MemoryStore() if request.param == "memory" else SQLAlchemyStore()


def test_sources_and_chunks_round_trip(store: RecordStore):
    a = Source(origin="a.md", text="abcdefg")
    b = Source(origin="https://example.org", text="xy")
    chunks = FixedSize(3)(a)
    store.add_sources([a, b])
    store.add_chunks(reversed(chunks))

    assert store.source(a.id) == a
    assert store.source(b.id) == b
    assert sorted(store.sources(), key=lambda s: s.text) == [a, b]
    assert store.chunks(a.id) == chunks
    assert store.chunks(b.id) == []


def test_adding_the_same_id_replaces(store: RecordStore):
    a = Source(origin="a", text="old")
    store.add_sources([a])
    store.add_sources([a.model_copy(update={"text": "new"})])
    assert store.source(a.id).text == "new"
    assert len(list(store.sources())) == 1


def test_missing_source_is_a_key_error(store: RecordStore):
    with pytest.raises(KeyError):
        store.source(uuid4())


def test_chunk_needs_its_source_and_nothing_of_the_batch_is_stored(store: RecordStore):
    a = Source(origin="a", text="abc")
    store.add_sources([a])
    orphan = Chunk(source_id=uuid4(), origin="b", start=0, text="x")
    with pytest.raises(KeyError):
        store.add_chunks([*FixedSize(2)(a), orphan])
    assert store.chunks(a.id) == []


def test_sql_store_persists_across_instances(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'records.db'}"
    a = Source(origin="a", text="abc")
    first = SQLAlchemyStore(url)
    first.add_sources([a])
    first.add_chunks(FixedSize(2)(a))

    second = SQLAlchemyStore(url)
    assert second.source(a.id) == a
    assert [c.text for c in second.chunks(a.id)] == ["ab", "c"]


def test_in_memory_sql_store_is_shared_across_threads():
    store = SQLAlchemyStore()
    a = Source(origin="a", text="abc")
    store.add_sources([a])
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(store.source, a.id).result() == a
