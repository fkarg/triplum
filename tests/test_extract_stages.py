"""The frame builders and resolvers, with a fake extractor: no spaCy needed."""

import polars as pl
import pytest
from triplum.cache import Cache
from triplum.data.schema import TS_MAX
from triplum.eval.datasets.base import CHUNK_SCHEMA, DOC_SCHEMA
from triplum.extract import ResolverSpec, extract, resolve
from triplum.extract.cached import CachedExtractor
from triplum.extract.fake import FakeExtractor
from triplum.extract.protocol import entity_id, normalise

DOCS = pl.DataFrame(
    [("d1", "t", None, 100, None), ("d2", "t", None, 200, None)], schema=DOC_SCHEMA, orient="row"
)
CHUNKS = pl.DataFrame(
    [
        (1, "d1", None, 0, 0, 30, "Alice founded Acme Corp in 1999."),
        (2, "d1", None, 0, 30, 60, "Alice's firm grew."),
        (3, "d2", None, 0, 0, 30, "Acme Corporation hired Alice."),
    ],
    schema=CHUNK_SCHEMA,
    orient="row",
)
# (chunk, start, end, text, label, kind, datatype, value)
SPANS = [
    (1, 0, 5, "Alice", "PERSON", "entity", None, None),
    (1, 14, 23, "Acme Corp", "ORG", "entity", None, None),
    (1, 27, 31, "1999", "DATE", "literal", "date", "1999-01-01"),
    (2, 0, 7, "Alice's", "PERSON", "entity", None, None),
    (3, 0, 16, "Acme Corporation", "ORG", "entity", None, None),
    (3, 23, 28, "Alice", "PERSON", "entity", None, None),
]
# (chunk, sent_start, sent_end, subj_start, subj_end, predicate, obj_start, obj_end, status, reason)
CLAIMS = [
    (1, 0, 32, 0, 5, "found", 14, 23, "accepted", "active"),
    (1, 0, 32, 0, 5, "found_in", 27, 31, "accepted", "prep"),
    (1, 0, 32, 27, 31, "be", 0, 5, "accepted", "copula"),  # literal subject
    (1, 0, 32, 0, 5, "be", 0, 5, "accepted", "apposition"),  # self loop
    (1, 0, 32, 0, 5, "see", 90, 95, "accepted", "active"),  # object is not a span
    (3, 0, 29, 0, 16, "hire", 23, 28, "accepted", "active"),
    (3, 0, 29, 0, 16, "fire", 23, 28, "negated", "active"),
]


def test_normalise_and_entity_id():
    assert normalise("The Bush’s ") == "bush"
    assert normalise("  Acme   Corp") == "acme corp"
    assert entity_id("d1", "Alice") == entity_id("d1", "alice's")
    assert entity_id("d1", "Alice") != entity_id("d2", "Alice")


def test_extract_builds_the_graph_frames():
    ex = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), recorded_at=7)
    alice1, acme1 = entity_id("d1", "Alice"), entity_id("d1", "Acme Corp")
    assert set(ex.entities["id"]) == {
        alice1,
        acme1,
        entity_id("d2", "Acme Corporation"),
        entity_id("d2", "Alice"),
    }
    # Alice in d1 has two mentions (chunks 1 and 2), one entity, two label facts (one surface each)
    assert ex.mentions.filter(pl.col("entity_id") == alice1).height == 2
    labels = ex.facts.filter((pl.col("subject_id") == alice1) & (pl.col("predicate") == "label"))
    assert sorted(labels["object_literal"]) == ["Alice", "Alice's"]
    types = ex.facts.filter((pl.col("subject_id") == alice1) & (pl.col("predicate") == "type"))
    assert types["object_literal"].to_list() == ["PERSON", "PERSON"]  # one per mention chunk
    claims = ex.facts.filter(~pl.col("predicate").is_in(["label", "type"]))
    rows = {
        (r["predicate"], r["object_id"], r["object_literal"]) for r in claims.iter_rows(named=True)
    }
    assert rows == {
        ("found", acme1, None),
        ("found_in", None, "1999-01-01"),
        ("hire", entity_id("d2", "Alice"), None),
    }
    found = claims.filter(pl.col("predicate") == "found").row(0, named=True)
    assert found["valid_from"] == 100 and found["valid_to"] == TS_MAX and found["recorded_at"] == 7
    assert found["confidence"] is None and found["object_datatype"] is None
    date = claims.filter(pl.col("predicate") == "found_in").row(0, named=True)
    assert date["object_datatype"] == "date"
    # every fact has exactly one single-chunk support group
    sup = ex.fact_support.group_by("fact_id").len()
    assert set(sup["len"]) == {1} and sup.height == ex.facts.height
    assert set(ex.fact_support["extractor"]) == {FakeExtractor(SPANS, CLAIMS).spec.hash()}
    assert ex.claims["status"].to_list() == [
        "accepted",
        "accepted",
        "ungrounded",
        "ungrounded",
        "ungrounded",
        "accepted",
        "negated",
    ]
    assert ex.claims["reason"][2:5].to_list() == [
        "subject is a literal",
        "subject and object are one span",
        "argument is not a span",
    ]


def test_extract_is_deterministic_and_ids_survive_recorded_at():
    a = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1)
    b = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1)
    c = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 2)
    assert a.hash() == b.hash() != c.hash()
    assert a.facts["id"].to_list() == c.facts["id"].to_list()
    assert set(c.facts["recorded_at"]) == {2}
    # a different observed_at gives different assertions, same ids
    docs = DOCS.with_columns(pl.col("observed_at") + 1)
    d = extract(CHUNKS, docs, FakeExtractor(SPANS, CLAIMS), 1)
    assert d.facts["id"].to_list() == a.facts["id"].to_list()
    assert d.facts["valid_from"].to_list() != a.facts["valid_from"].to_list()


def test_exact_resolver_links_across_documents_only():
    ex = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1)
    r = resolve(ex, CHUNKS, ResolverSpec("exact"), 1)
    same = r.facts.filter(pl.col("predicate") == "same_as")
    assert same.height == 1  # Alice d1 <-> Alice d2; Acme Corp != Acme Corporation
    fid = same["id"][0]
    sup = r.fact_support.filter(pl.col("fact_id") == fid)
    assert sorted(sup["chunk_id"]) == [1, 3] and set(sup["group_no"]) == {0}
    assert same["valid_from"][0] == 0 and same["confidence"][0] is None
    canon = dict(r.entities.select("id", "canonical_id").iter_rows())
    a1, a2 = sorted([entity_id("d1", "Alice"), entity_id("d2", "Alice")])
    assert canon[a2] == a1 and canon[a1] is None
    assert canon[entity_id("d1", "Acme Corp")] is None
    assert resolve(ex, CHUNKS, ResolverSpec("none"), 1) is ex


def test_fuzzy_resolver_needs_the_same_type():
    pytest.importorskip("rapidfuzz")
    ex = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1)
    r = resolve(ex, CHUNKS, ResolverSpec("fuzzy", threshold=0.6), 1)
    same = r.facts.filter(pl.col("predicate") == "same_as")
    pairs = {tuple(sorted(p)) for p in same.select("subject_id", "object_id").iter_rows()}
    assert (
        tuple(sorted([entity_id("d1", "Acme Corp"), entity_id("d2", "Acme Corporation")])) in pairs
    )
    assert same.height == 2
    # the same threshold with different types would not link: give Acme Corporation a PERSON type
    spans = [s if s[3] != "Acme Corporation" else (*s[:4], "PERSON", *s[5:]) for s in SPANS]
    ex2 = extract(CHUNKS, DOCS, FakeExtractor(spans, CLAIMS), 1)
    r2 = resolve(ex2, CHUNKS, ResolverSpec("fuzzy", threshold=0.6), 1)
    assert r2.facts.filter(pl.col("predicate") == "same_as").height == 1


def test_cached_extractor_replays_per_chunk(tmp_path):
    inner = FakeExtractor(SPANS, CLAIMS)
    cached = CachedExtractor(inner, Cache(tmp_path))
    spans, claims = cached.run(CHUNKS)
    assert inner.calls == 1 and cached.misses == 3
    spans2, claims2 = CachedExtractor(inner, Cache(tmp_path)).run(CHUNKS)
    assert inner.calls == 1
    assert spans.equals(spans2) and claims.equals(claims2)
    assert spans.equals(inner.spans) and claims.equals(inner.claims)
    # a partial hit runs the inner extractor on the missing chunks only
    more = pl.concat(
        [
            CHUNKS,
            pl.DataFrame(
                [(4, "d2", None, 0, 30, 40, "New text.")], schema=CHUNK_SCHEMA, orient="row"
            ),
        ]
    )
    CachedExtractor(inner, Cache(tmp_path)).run(more)
    assert inner.calls == 2


def test_resolving_twice_keeps_the_canonical_ids():
    ex = extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1)
    once = resolve(ex, CHUNKS, ResolverSpec("exact"), 1)
    twice = resolve(once, CHUNKS, ResolverSpec("exact"), 2)
    assert twice.facts.height == once.facts.height
    assert twice.entities.sort("id").equals(once.entities.sort("id"))


def test_build_is_extract_then_resolve():
    from triplum.extract import build

    a = build(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), ResolverSpec("exact"), 1)
    b = resolve(
        extract(CHUNKS, DOCS, FakeExtractor(SPANS, CLAIMS), 1), CHUNKS, ResolverSpec("exact"), 1
    )
    assert a.hash() == b.hash()


def test_small_model_spec_serialises_vocabularies_unambiguously():
    import json

    from triplum.extract.protocol import ExtractorSpec

    a = ExtractorSpec("small_model", "1", params=(("entity_types", json.dumps(["a,b", "c"])),))
    b = ExtractorSpec("small_model", "1", params=(("entity_types", json.dumps(["a", "b,c"])),))
    assert a.hash() != b.hash()
