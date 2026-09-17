"""The graph side of the SQLite store under D4 visibility, on the two-principal corpus."""

import polars as pl
import pytest
from triplum.data.viewer import Viewer
from triplum.extract import ResolverSpec, extract, resolve
from triplum.extract.fake import FakeExtractor
from triplum.extract.protocol import entity_id
from triplum.store.sqlite.store import SqliteStore

# d1 (public, alice): chunk 1 "Alice founded Acme", chunk 2; d2 (alice): chunk 3 "Acme hired Bob".
SPANS = [
    (1, 0, 5, "Alice", "PERSON", "entity", None, None),
    (1, 14, 18, "Acme", "ORG", "entity", None, None),
    (3, 0, 4, "Acme", "ORG", "entity", None, None),
    (3, 11, 14, "Bob", "PERSON", "entity", None, None),
]
CLAIMS = [
    (1, 0, 20, 0, 5, "found", 14, 18, "accepted", "active"),
    (3, 0, 15, 0, 4, "hire", 11, 14, "accepted", "active"),
]
ALICE, ACME1, ACME2, BOB = (
    entity_id("d1", "Alice"),
    entity_id("d1", "Acme"),
    entity_id("d2", "Acme"),
    entity_id("d2", "Bob"),
)


@pytest.fixture
def graph_store(tmp_db, sample_corpus):
    docs, grants, chunks = sample_corpus
    store = SqliteStore(tmp_db)
    store.put_documents(docs, grants)
    store.put_chunks(chunks)
    ex = resolve(
        extract(chunks, docs, FakeExtractor(SPANS, CLAIMS), recorded_at=1000),
        chunks,
        ResolverSpec("exact"),
        recorded_at=1000,
    )
    store.put_graph(ex.entities, ex.facts, ex.fact_support, ex.mentions)
    return store, ex


def claims(df: pl.DataFrame) -> set[tuple]:
    return {
        (r["subject_id"], r["predicate"], r["object_id"])
        for r in df.filter(~pl.col("predicate").is_in(["label", "type"])).iter_rows(named=True)
    }


def test_public_sees_only_facts_supported_by_public_chunks(graph_store):
    store, _ = graph_store
    public, alice = Viewer.of("public"), Viewer.of("alice")
    assert claims(store.facts(public)) == {(ALICE, "found", ACME1)}
    # the same_as merge cites chunks 1 and 3; public cannot see chunk 3, so no merge
    assert claims(store.facts(alice)) == {
        (ALICE, "found", ACME1),
        (ACME2, "hire", BOB),
        (min(ACME1, ACME2), "same_as", max(ACME1, ACME2)),
    }
    # an entity touched only by hidden facts has no visible label either
    labels = store.facts(public).filter(pl.col("predicate") == "label")
    assert set(labels["subject_id"]) == {ALICE, ACME1}
    assert store.mentions([1, 3], public)["chunk_id"].to_list() == [1, 1]
    assert store.mentions([1, 3], alice)["chunk_id"].to_list() == [1, 1, 3, 3]


def test_neighbours_follow_visible_same_as_only(graph_store):
    store, _ = graph_store
    public, alice = Viewer.of("public"), Viewer.of("alice")
    assert claims(store.neighbours([ACME1], 1, public)) == {(ALICE, "found", ACME1)}
    assert claims(store.neighbours([ACME1], 1, alice)) == {
        (ALICE, "found", ACME1),
        (ACME2, "hire", BOB),
        (min(ACME1, ACME2), "same_as", max(ACME1, ACME2)),
    }
    # two hops from Alice reach Bob for alice, nothing beyond Acme for public
    assert BOB in set(store.neighbours([ALICE], 2, alice)["object_id"])
    assert claims(store.neighbours([ALICE], 2, public)) == {(ALICE, "found", ACME1)}
    assert store.neighbours([ALICE], 0, public).height == 0


def test_time_travel_hides_facts_not_yet_valid_or_recorded(graph_store, sample_corpus):
    store, _ = graph_store
    observed = int(sample_corpus[0]["observed_at"][0])
    before = store.facts(Viewer.of("alice", as_of_valid=observed - 1))
    assert set(before["predicate"]) == {"same_as"}  # valid from 0; the rest from observed_at
    assert store.facts(Viewer.of("alice", as_of_valid=observed, as_of_recorded=999)).height == 0
    assert store.facts(Viewer.of("alice", as_of_valid=observed, as_of_recorded=1000)).height > 0
    # a same_as fact is valid from 0 but still needs its recording instant
    early = store.facts(Viewer.of("alice", as_of_valid=0, as_of_recorded=1000))
    assert set(early["predicate"]) == {"same_as"}


def test_put_graph_rejects_unsupported_and_malformed_facts(graph_store):
    store, ex = graph_store
    with pytest.raises(ValueError, match="no support group"):
        store.put_graph(ex.entities, ex.facts, ex.fact_support.head(0), ex.mentions)
    both = ex.facts.with_columns(pl.lit("x").alias("object_literal"))
    with pytest.raises(ValueError, match="both or neither"):
        store.put_graph(ex.entities, both, ex.fact_support, ex.mentions)
    # writing the same graph twice is idempotent
    store.put_graph(ex.entities, ex.facts, ex.fact_support, ex.mentions)
    assert store.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == ex.facts.height
    canon = dict(store.conn.execute("SELECT id, canonical_id FROM entities"))
    assert canon[max(ACME1, ACME2)] == min(ACME1, ACME2)
