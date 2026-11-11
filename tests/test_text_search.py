from collections.abc import Iterator
from uuid import UUID

import pytest

from triplum.datatype import Source, Viewer
from triplum.steps.chunking import FixedSize, WholeText
from triplum.store import FTS5Settings, MemoryStore, SQLAlchemyStore, SQLiteStore

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")
OTHER = UUID("01900000-0000-7000-8000-000000000002")
PUBLIC = Viewer(principals=frozenset({"public"}))


@pytest.fixture(params=["memory", "generic", "native"])
def store(request: pytest.FixtureRequest) -> Iterator[MemoryStore | SQLAlchemyStore]:
    instance = {"memory": MemoryStore, "generic": SQLAlchemyStore, "native": SQLiteStore}[
        request.param
    ]()
    yield instance
    if isinstance(instance, SQLAlchemyStore):
        instance.close()


def _add(store, text: str, *, collection: UUID = COLLECTION, allow=("public",)) -> Source:
    source = Source(collection_id=collection, origin=text, text=text)
    store.add_sources([source], allow=allow)
    store.replace_chunks(source.id, WholeText()(source))
    return source


def test_build_search_snapshot_and_empty_rebuild(store):
    source = _add(store, "cat dog")
    with pytest.raises(KeyError):
        store.search_text("cat", collection_id=COLLECTION, k=2)
    store.index_text(COLLECTION)
    before = store.search_text("cat", collection_id=COLLECTION, k=2)
    assert [h.chunk for h in before] == WholeText()(source)
    store.replace_chunks(source.id, FixedSize(3)(source))
    _add(store, "cat eel")
    assert store.search_text("cat", collection_id=COLLECTION, k=2) == before
    store.index_text(COLLECTION)
    assert {h.chunk.text for h in store.search_text("cat", collection_id=COLLECTION, k=2)} == {
        "cat",
        "cat eel",
    }
    for s in store.sources(collection_id=COLLECTION):
        store.replace_chunks(s.id, [])
    store.index_text(COLLECTION)
    assert store.search_text("cat", collection_id=COLLECTION, k=2) == []


def test_native_sqlite_snapshot_is_persistent(tmp_path):
    from triplum.store import SQLiteStore
    from triplum.store.sql.sqlite import FTS5Settings

    url = f"sqlite:///{tmp_path / 'records.sqlite'}"
    native = SQLiteStore(url)
    try:
        source = _add(native, "cat dog")
        native.index_text(COLLECTION)
        expected = native.search_text("cat", collection_id=COLLECTION, k=1)
        native.replace_chunks(source.id, FixedSize(3)(source))
    finally:
        native.close()
    reopened = SQLiteStore(url)
    try:
        assert reopened.search_text("cat", collection_id=COLLECTION, k=1) == expected
    finally:
        reopened.close()
    changed = SQLiteStore(url, text=FTS5Settings(tokenizer="porter unicode61"))
    try:
        with pytest.raises(ValueError, match="settings"):
            changed.search_text("cat", collection_id=COLLECTION, k=1)
        changed.index_text(COLLECTION)
        assert [
            h.chunk.text for h in changed.search_text("cat", collection_id=COLLECTION, k=1)
        ] == ["cat"]
    finally:
        changed.close()


@pytest.mark.parametrize("query", ["", "!!!", "unknown", '"', "*"])
def test_empty_and_nonmatching_queries(store, query):
    _add(store, "cat dog")
    store.index_text(COLLECTION)
    assert store.search_text(query, collection_id=COLLECTION, k=2) == []


@pytest.mark.parametrize(
    ("query", "texts"),
    [
        ("cat*", ["cat dog"]),
        ("cat.dog", ["cat dog"]),
        ("absent cat", ["cat dog"]),
        ("AND", ["AND operator"]),
    ],
)
def test_query_terms_are_literal_or_terms(store, query, texts):
    _add(store, "cat dog")
    _add(store, "AND operator")
    store.index_text(COLLECTION)
    assert [h.chunk.text for h in store.search_text(query, collection_id=COLLECTION, k=3)] == texts


def test_visibility_is_before_top_k_and_none_is_unrestricted(store):
    hidden = _add(store, "cat cat cat", allow=("team",))
    closed = _add(store, "cat cat dog", allow=())
    first = _add(store, "cat dog")
    second = _add(store, "cat dog eel")
    store.index_text(COLLECTION)
    assert [h.chunk.source_id for h in store.search_text("cat", collection_id=COLLECTION, k=3)] == [
        hidden.id,
        closed.id,
        first.id,
    ]
    assert [
        h.chunk.source_id
        for h in store.search_text("cat", collection_id=COLLECTION, viewer=PUBLIC, k=2)
    ] == [first.id, second.id]
    assert (
        store.search_text(
            "cat", collection_id=COLLECTION, viewer=Viewer(principals=frozenset()), k=2
        )
        == []
    )


def test_another_collection_cannot_change_scores_or_ranks(store):
    _add(store, "cat dog")
    _add(store, "cat dog eel fox")
    store.index_text(COLLECTION)
    expected = store.search_text("cat", collection_id=COLLECTION, k=5)
    _add(store, "cat cat cat", collection=OTHER)
    _add(store, " ".join(["eel"] * 50), collection=OTHER)
    store.index_text(OTHER)
    store.index_text(UUID(str(COLLECTION)))  # equal UUID value, separately constructed object
    assert store.search_text("cat", collection_id=UUID(str(COLLECTION)), k=5) == expected


@pytest.mark.parametrize("k", [0, -1])
def test_k_must_be_positive_even_for_unbuilt_index(store, k):
    with pytest.raises(ValueError, match="k must be at least 1"):
        store.search_text("cat", collection_id=COLLECTION, k=k)


def test_unbuilt_and_built_empty_collection_differ(store):
    with pytest.raises(KeyError):
        store.search_text("", collection_id=OTHER, k=1)
    store.index_text(OTHER)
    assert store.search_text("cat", collection_id=OTHER, k=1) == []


def test_ties_follow_source_then_numeric_ordinal(store):
    sources = [_add(store, "cat" * 12), _add(store, "cat" * 13)]
    expected = []
    for source in sources:
        chunks = FixedSize(3)(source)
        store.replace_chunks(source.id, chunks)
        expected.extend(chunks)
    store.index_text(COLLECTION)
    assert [h.chunk for h in store.search_text("cat", collection_id=COLLECTION, k=30)] == sorted(
        expected, key=lambda c: (c.source_id, c.ordinal)
    )


def test_metadata_is_not_searchable(store):
    source = Source(collection_id=COLLECTION, origin="metadataonly", text="cat")
    store.add_sources([source], allow=["public"])
    store.replace_chunks(source.id, WholeText()(source))
    store.index_text(COLLECTION)
    for query in ("metadataonly", source.id.hex, "0"):
        assert store.search_text(query, collection_id=COLLECTION, k=1) == []


def test_native_failed_rebuild_rolls_back_ddl_and_contents(tmp_path):
    from sqlalchemy import event

    native = SQLiteStore(f"sqlite:///{tmp_path / 'atomic.sqlite'}")
    try:
        source = _add(native, "cat dog")
        native.index_text(COLLECTION)
        expected = native.search_text("cat", collection_id=COLLECTION, k=2)
        native.replace_chunks(source.id, FixedSize(3)(source))

        def fail_repopulation(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith('INSERT INTO "chunk_text_'):
                raise RuntimeError("injected repopulation failure after DROP and CREATE")

        event.listen(native.engine, "before_cursor_execute", fail_repopulation)
        try:
            with pytest.raises(RuntimeError, match="injected"):
                native.index_text(COLLECTION)
        finally:
            event.remove(native.engine, "before_cursor_execute", fail_repopulation)
        assert native.search_text("cat", collection_id=COLLECTION, k=2) == expected
    finally:
        native.close()


@pytest.mark.parametrize("factory", [MemoryStore, SQLAlchemyStore])
def test_generic_failed_rebuild_keeps_previous_snapshot(monkeypatch, factory):
    store = factory()
    _add(store, "cat dog")
    store.index_text(COLLECTION)
    expected = store.search_text("cat", collection_id=COLLECTION, k=1)

    def unreadable(*args, **kwargs):
        raise RuntimeError("injected read failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "chunks", unreadable)
        with pytest.raises(RuntimeError, match="injected"):
            store.index_text(COLLECTION)
    assert store.search_text("cat", collection_id=COLLECTION, k=1) == expected
    if isinstance(store, SQLAlchemyStore):
        store.close()


def test_custom_settings_affect_tokenization_and_validate_persisted_pattern(tmp_path):
    from triplum.steps.retrieval import BM25S_DEFAULT

    for store in (MemoryStore(text=BM25S_DEFAULT), SQLAlchemyStore(text=BM25S_DEFAULT)):
        try:
            _add(store, "vitamin c")
            store.index_text(COLLECTION)
            assert store.search_text("c", collection_id=COLLECTION, k=1) == []
        finally:
            if isinstance(store, SQLAlchemyStore):
                store.close()
    url = f"sqlite:///{tmp_path / 'pattern.sqlite'}"
    original = SQLiteStore(url)
    try:
        _add(original, "vitamin c")
        original.index_text(COLLECTION)
    finally:
        original.close()
    changed = SQLiteStore(url, text=FTS5Settings(token_pattern=r"\w{2,}"))
    try:
        with pytest.raises(ValueError, match="settings"):
            changed.search_text("c", collection_id=COLLECTION, k=1)
        changed.index_text(COLLECTION)
        assert changed.search_text("c", collection_id=COLLECTION, k=1) == []
    finally:
        changed.close()


def test_twenty_question_fixture_agreement(store):
    from pathlib import Path

    from triplum.datasets.fixture import LegacyFixture
    from triplum.evaluation.recall import resolve_evidence, score_recall, summarize_recall
    from triplum.steps.retrieval import BM25

    fixture = LegacyFixture(Path(__file__).parent / "fixtures/hotpotqa.json")
    corpus = list(fixture.corpus(COLLECTION))
    store.add_sources(corpus, allow=["public"])
    for source in corpus:
        store.replace_chunks(source.id, WholeText()(source))
    store.index_text(COLLECTION)
    reference = BM25(store, collection_id=COLLECTION)
    keys = {s.external_id: s.id for s in corpus if s.external_id is not None}
    actual, baseline = [], []
    questions = list(fixture.questions())
    assert len(questions) == 20
    for question in questions:
        evidence = resolve_evidence(question, keys)
        hits = store.search_text(question.input.text, collection_id=COLLECTION, k=5)
        ref = reference(question.input.text, k=5)
        if not isinstance(store, SQLiteStore):
            assert hits == ref
        actual.append(score_recall(hits, evidence))
        baseline.append(score_recall(ref, evidence))
    for k in (2, 5):
        observed = summarize_recall(s[k] for s in actual).recall
        expected = summarize_recall(s[k] for s in baseline).recall
        assert observed is not None and expected is not None
        print(f"{type(store).__name__} R@{k} {observed:.3f} reference {expected:.3f}")
        assert abs(observed - expected) <= 0.05 + 1e-12


def test_native_store_rejects_other_database_urls():
    with pytest.raises(ValueError, match="SQLite"):
        SQLiteStore("postgresql://localhost/triplum")


def test_native_settings_and_search_share_a_read_snapshot(tmp_path):
    # A second store may rebuild between metadata validation and MATCH. The checked
    # tokenizer must describe the exact index searched, even when WAL permits a commit.
    from sqlalchemy import event

    url = f"sqlite:///{tmp_path / 'concurrent.sqlite'}"
    original = SQLiteStore(url)
    replacement = SQLiteStore(url, text=FTS5Settings(tokenizer="porter unicode61"))
    try:
        with original.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one() == "wal"
        _add(original, "running")
        original.index_text(COLLECTION)
        assert original.search_text("run", collection_id=COLLECTION, k=1) == []
        rebuilt = False

        def rebuild_after_metadata(connection, cursor, statement, parameters, context, executemany):
            nonlocal rebuilt
            if not rebuilt and statement.startswith("SELECT settings FROM text_index"):
                rebuilt = True
                replacement.index_text(COLLECTION)

        event.listen(original.engine, "after_cursor_execute", rebuild_after_metadata)
        try:
            assert original.search_text("run", collection_id=COLLECTION, k=1) == []
            assert rebuilt
        finally:
            event.remove(original.engine, "after_cursor_execute", rebuild_after_metadata)
        with pytest.raises(ValueError, match="settings"):
            original.search_text("run", collection_id=COLLECTION, k=1)
        assert [
            h.chunk.text for h in replacement.search_text("run", collection_id=COLLECTION, k=1)
        ] == ["running"]
    finally:
        original.close()
        replacement.close()


def test_native_tokenizer_preserves_accents_and_underscores():
    native = SQLiteStore()
    try:
        source = _add(native, "café cat_dog")
        native.index_text(COLLECTION)
        for query in ("café", "cat_dog"):
            assert [
                h.chunk for h in native.search_text(query, collection_id=COLLECTION, k=1)
            ] == WholeText()(source)
        for query in ("cafe", "cat", "dog"):
            assert native.search_text(query, collection_id=COLLECTION, k=1) == []
    finally:
        native.close()


@pytest.mark.parametrize("factory", [MemoryStore, SQLAlchemyStore])
def test_public_constructor_settings_annotations_resolve(factory):
    import inspect
    from typing import get_type_hints

    from triplum.steps.retrieval import BM25Settings

    assert inspect.signature(factory.__init__).parameters["text"].annotation == BM25Settings | None
    assert get_type_hints(factory.__init__)["text"] == BM25Settings | None


def test_native_rejects_nul_terms_without_changing_custom_tokenization():
    custom = SQLiteStore(text=FTS5Settings(token_pattern=r".+"))
    default = SQLiteStore()
    try:
        for store in (custom, default):
            _add(store, "cat dog")
            store.index_text(COLLECTION)
        with pytest.raises(ValueError, match="NUL"):
            custom.search_text("cat\x00dog", collection_id=COLLECTION, k=1)
        assert [
            h.chunk.text for h in default.search_text("cat\x00dog", collection_id=COLLECTION, k=1)
        ] == ["cat dog"]
    finally:
        custom.close()
        default.close()
