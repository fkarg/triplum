import math
from collections.abc import Iterator
from uuid import UUID

import pytest
from pydantic import ValidationError

from triplum.datatype import Chunk, Source, Viewer
from triplum.steps.chunking import FixedSize, WholeText
from triplum.steps.retrieval import BM25, BM25S_DEFAULT, HIPPORAG1, BM25Settings
from triplum.store import MemoryStore, RecordStore, SQLAlchemyStore

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")
OTHER = UUID("01900000-0000-7000-8000-000000000002")
PUBLIC = Viewer(principals=frozenset({"public"}))
TEAM = Viewer(principals=frozenset({"public", "team"}))


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest) -> Iterator[RecordStore]:
    if request.param == "memory":
        yield MemoryStore()
        return
    sql = SQLAlchemyStore()
    yield sql
    sql.close()


def _add(
    store: RecordStore, text: str, *, allow: str = "public", collection: UUID = COLLECTION
) -> Source:
    source = Source(collection_id=collection, origin=text, text=text)
    store.add_sources([source], allow=[allow])
    store.replace_chunks(source.id, WholeText()(source))
    return source


def _texts(hits) -> list[str]:
    return [hit.chunk.text for hit in hits]


def test_hidden_chunks_never_appear_or_displace_visible_ones(store: RecordStore):
    _add(store, "cat cat cat", allow="team")  # the best match, hidden from PUBLIC
    _add(store, "cat dog")
    _add(store, "cat dog eel fox")
    retriever = BM25(store, collection_id=COLLECTION, viewer=TEAM)

    assert _texts(retriever("cat", viewer=PUBLIC, k=2)) == ["cat dog", "cat dog eel fox"]
    assert _texts(retriever("cat", viewer=TEAM, k=2)) == ["cat cat cat", "cat dog"]
    assert retriever("cat", viewer=Viewer(principals=frozenset()), k=2) == []


def test_an_index_covers_one_collection_with_its_own_statistics(store: RecordStore):
    # Owner (Q33): queries select one collection; statistics and hits come only from it.
    alone = MemoryStore()
    for target in (store, alone):
        _add(target, "cat dog")
        _add(target, "cat dog eel fox")
    _add(store, "cat cat cat", collection=OTHER)  # a stronger match in another collection
    _add(store, " ".join(["eel"] * 50), collection=OTHER)  # would shift avgdl and N
    _add(store, "cat dog", collection=OTHER)  # a rerun's copy of the same text

    hits = BM25(store, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=2)
    # Global scoring then filtering changes the scores; filtering after top-k leaves fewer hits.
    reference = BM25(alone, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=2)
    assert [hit.score for hit in hits] == [hit.score for hit in reference]
    assert _texts(hits) == ["cat dog", "cat dog eel fox"]
    assert {hit.chunk.collection_id for hit in hits} == {COLLECTION}
    unknown = UUID("01900000-0000-7000-8000-000000000009")
    assert BM25(store, collection_id=unknown, viewer=PUBLIC)("cat", viewer=PUBLIC, k=2) == []


def test_only_the_corpus_viewers_sources_are_indexed(store: RecordStore):
    _add(store, "cat dog", allow="team")
    _add(store, "cat eel")
    retriever = BM25(store, collection_id=COLLECTION, viewer=PUBLIC)
    assert _texts(retriever("cat", viewer=TEAM, k=5)) == ["cat eel"]


@pytest.mark.parametrize("reverse", [False, True])
def test_equal_scores_are_ordered_by_source_id(store: RecordStore, reverse: bool):
    texts = ["cat dog", "cat eel", "cat fox"]
    sources = [_add(store, t) for t in (reversed(texts) if reverse else texts)]
    hits = BM25(store, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=3)
    assert len({hit.score for hit in hits}) == 1
    assert [hit.chunk.source_id for hit in hits] == sorted(s.id for s in sources)


def test_chunks_of_one_source_tie_in_ordinal_order(store: RecordStore):
    source = Source(collection_id=COLLECTION, origin="s", text="cat1cat2cat3")
    store.add_sources([source], allow=["public"])
    store.replace_chunks(source.id, FixedSize(4)(source))
    hits = BM25(
        store,
        collection_id=COLLECTION,
        viewer=PUBLIC,
        settings=BM25Settings(k1=1.2, b=0.75, token_pattern="[a-z]+"),
    )("cat", viewer=PUBLIC, k=3)
    assert [hit.chunk.ordinal for hit in hits] == [0, 1, 2]


def test_scores_follow_lucene_bm25_with_the_preset_parameters(store: RecordStore):
    _add(store, "cat dog")
    _add(store, "dog eel fox")
    [hit] = BM25(store, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=5)
    # N=2, df=1, tf=1, dl=2, avgdl=2.5; k1=1.2, b=0.75 (HIPPORAG1).
    idf = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
    tf = 1 / (1 + 1.2 * (1 - 0.75 + 0.75 * 2 / 2.5))
    assert hit.score == pytest.approx(idf * tf, rel=1e-6)


@pytest.mark.parametrize(
    ("query", "expected"),
    [("zebra", []), ("", []), ("!!! ...", []), ("CAT", ["cat dog"])],
    ids=["unknown", "empty", "punctuation", "lowercased"],
)
def test_only_queries_sharing_a_token_match(store: RecordStore, query: str, expected: list[str]):
    _add(store, "cat dog")
    assert (
        _texts(BM25(store, collection_id=COLLECTION, viewer=PUBLIC)(query, viewer=PUBLIC, k=5))
        == expected
    )


@pytest.mark.parametrize(
    "pattern",
    [r"(\w)(\w+)", r"(\w)\w+", r"\w*", r"\b|\w+"],
    ids=["two-groups", "one-group", "empty-matches", "only-empty-or-word"],
)
def test_tokens_are_whole_matches_even_with_capture_groups(store: RecordStore, pattern: str):
    _add(store, "cat dog")
    _add(store, "cow eel")
    settings = BM25Settings(k1=1.2, b=0.75, token_pattern=pattern)
    # Group captures would make "c" (or a tuple) the token and match "cow" too; an indexed
    # empty token would match every chunk, or crash bm25s on queries.
    assert _texts(
        BM25(store, collection_id=COLLECTION, viewer=PUBLIC, settings=settings)(
            "cat", viewer=PUBLIC, k=5
        )
    ) == ["cat dog"]


@pytest.mark.parametrize(("k1", "b"), [(-0.1, 0.75), (1.2, -0.1), (1.2, 1.1)])
def test_scoring_parameters_that_could_hide_matches_are_rejected(k1: float, b: float):
    with pytest.raises(ValidationError):
        BM25Settings(k1=k1, b=b)


def test_fewer_hits_than_k_when_few_chunks_match(store: RecordStore):
    _add(store, "cat dog")
    _add(store, "eel fox")
    assert _texts(
        BM25(store, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=10)
    ) == ["cat dog"]


def test_an_empty_or_tokenless_corpus_returns_nothing(store: RecordStore):
    assert BM25(store, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=1) == []
    _add(store, "!!!")
    assert BM25(store, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=1) == []


@pytest.mark.parametrize("k", [0, -1])
def test_k_below_one_raises(store: RecordStore, k: int):
    _add(store, "cat")
    with pytest.raises(ValueError, match="k must be at least 1"):
        BM25(store, collection_id=COLLECTION, viewer=PUBLIC)("cat", viewer=PUBLIC, k=k)


def test_the_index_is_a_snapshot(store: RecordStore):
    source = _add(store, "cat dog")
    retriever = BM25(store, collection_id=COLLECTION, viewer=PUBLIC)
    _add(store, "cat eel")
    store.replace_chunks(source.id, FixedSize(3)(source))
    [hit] = retriever("cat", viewer=PUBLIC, k=5)
    assert hit.chunk == WholeText()(source)[0]


def test_presets_differ_in_one_character_tokens(store: RecordStore):
    _add(store, "vitamin c")
    _add(store, "vitamin d")
    assert _texts(
        BM25(store, collection_id=COLLECTION, viewer=PUBLIC, settings=HIPPORAG1)(
            "c", viewer=PUBLIC, k=2
        )
    ) == ["vitamin c"]
    assert (
        BM25(store, collection_id=COLLECTION, viewer=PUBLIC, settings=BM25S_DEFAULT)(
            "c", viewer=PUBLIC, k=2
        )
        == []
    )


def test_fingerprint_follows_settings(store: RecordStore):
    default = BM25(store, collection_id=COLLECTION, viewer=PUBLIC).fingerprint()
    assert (
        BM25(store, collection_id=COLLECTION, viewer=PUBLIC, settings=HIPPORAG1).fingerprint()
        == default
    )
    assert (
        BM25(store, collection_id=COLLECTION, viewer=PUBLIC, settings=BM25S_DEFAULT).fingerprint()
        != default
    )
    assert (
        BM25(
            store,
            collection_id=COLLECTION,
            viewer=PUBLIC,
            settings=BM25Settings(k1=1.2, b=0.75, lowercase=False),
        ).fingerprint()
        != default
    )


def test_whole_text_is_one_chunk_and_empty_text_none():
    source = Source(collection_id=COLLECTION, origin="s", text="abc")
    assert WholeText()(source) == [
        Chunk(
            collection_id=COLLECTION,
            source_id=source.id,
            origin="s",
            ordinal=0,
            start=0,
            text="abc",
        )
    ]
    assert WholeText()(Source(collection_id=COLLECTION, origin="e", text="")) == []
    assert WholeText().fingerprint() != FixedSize(3).fingerprint()
