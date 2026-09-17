"""The spaCy rule extractor, one sentence per rule. Skipped without the `extract` extra."""

import polars as pl
import pytest
from triplum.eval.datasets.base import CHUNK_SCHEMA, DOC_SCHEMA
from triplum.extract import extract
from triplum.extract.protocol import normalise

pytest.importorskip("spacy")
pytest.importorskip("en_core_web_sm")


@pytest.fixture(scope="module")
def rules():
    from triplum.extract.rules import RulesExtractor

    return RulesExtractor()


def run(rules, *sentences: str) -> list[tuple]:
    """(subject, predicate, object, status, reason) per claim, surfaces cut from the text."""
    chunks = pl.DataFrame(
        [(i + 1, "d", None, 0, 0, len(s), s) for i, s in enumerate(sentences)],
        schema=CHUNK_SCHEMA,
        orient="row",
    )
    _, claims = rules.run(chunks)
    out = []
    for c in claims.iter_rows(named=True):
        t = sentences[c["chunk_id"] - 1]
        out.append(
            (
                t[c["subj_start"] : c["subj_end"]],
                c["predicate"],
                t[c["obj_start"] : c["obj_end"]],
                c["status"],
                c["reason"],
            )
        )
    return out


def test_active_passive_prepositional_copula_apposition(rules):
    assert run(rules, "Alice Smith founded Acme Corp in March 1999.") == [
        ("Alice Smith", "found", "Acme Corp", "accepted", "active"),
        ("Alice Smith", "found_in", "March 1999", "accepted", "prep"),
    ]
    assert run(rules, "Acme Corp was founded by Alice Smith and Bob Jones.") == [
        ("Alice Smith", "found", "Acme Corp", "accepted", "passive"),
        ("Bob Jones", "found", "Acme Corp", "accepted", "passive"),
    ]
    assert run(rules, "Alice Smith is a chemist.") == [
        ("Alice Smith", "be", "a chemist", "accepted", "copula")
    ]
    assert run(rules, "Acme Corp, a company in Berlin, grew quickly.") == [
        ("Acme Corp", "be", "a company", "accepted", "apposition")
    ]
    assert run(rules, "Alice Smith set up Acme Corp.") == [
        ("Alice Smith", "set_up", "Acme Corp.", "accepted", "active")
    ]


def test_negation_modality_and_subordinate_clauses_are_recorded_not_materialised(rules):
    assert run(rules, "Alice Smith did not found Acme Corp.")[0][3] == "negated"
    assert run(rules, "Alice Smith may found Acme Corp.")[0][3] == "modal"
    assert run(rules, "If Alice Smith founds Acme Corp, Bob Jones leaves Berlin.") == [
        ("Alice Smith", "found", "Acme Corp", "subordinate", "active"),
        ("Bob Jones", "leave", "Berlin", "accepted", "active"),
    ]
    assert run(rules, "Bob Jones said that Alice Smith founded Acme Corp.") == [
        ("Alice Smith", "found", "Acme Corp.", "subordinate", "active")
    ]
    assert run(rules, "Alice Smith, who founded Acme Corp, lives in Berlin.") == [
        ("who", "found", "Acme Corp", "subordinate", "active"),
        ("Alice Smith", "live_in", "Berlin", "accepted", "prep"),
    ]


def test_conjunct_verbs_share_the_subject(rules):
    assert run(rules, "Alice Smith founded Acme Corp and joined Globex in 2001.") == [
        ("Alice Smith", "found", "Acme Corp", "accepted", "active"),
        ("Alice Smith", "join", "Globex", "accepted", "active"),
        ("Alice Smith", "join_in", "2001", "accepted", "prep"),
    ]


def test_pronouns_and_bare_heads_are_ungrounded(rules):
    assert run(rules, "She founded Acme Corp.") == [
        ("She", "found", "Acme Corp.", "ungrounded", "pronoun")
    ]
    assert run(rules, "Acme Corp employs 300 people.") == [
        ("Acme Corp", "employ", "people", "ungrounded", "no span")
    ]


def test_literals_are_typed_and_parsed(rules):
    chunks = pl.DataFrame(
        [(1, "d", None, 0, 0, 60, "Acme Corp raised $5 million in March 1999 and is profitable.")],
        schema=CHUNK_SCHEMA,
        orient="row",
    )
    spans, _ = rules.run(chunks)
    lits = {
        r["text"]: (r["datatype"], r["value"])
        for r in spans.filter(pl.col("kind") == "literal").iter_rows(named=True)
    }
    assert lits == {
        "$5 million": ("money", "$5 million"),
        "March 1999": ("date", "1999-03-01"),
        "profitable": ("string", "profitable"),
    }
    docs = pl.DataFrame([("d", "t", None, 0, None)], schema=DOC_SCHEMA, orient="row")
    ex = extract(chunks, docs, rules, 1)
    lit_facts = ex.facts.filter(
        pl.col("object_literal").is_not_null() & ~pl.col("predicate").is_in(["label", "type"])
    )
    assert {
        (r["predicate"], r["object_literal"], r["object_datatype"])
        for r in lit_facts.iter_rows(named=True)
    } == {
        ("raise", "$5 million", "money"),
        ("raise_in", "1999-03-01", "date"),
        ("be", "profitable", "string"),
    }
    assert ex.facts.filter(pl.col("predicate") == "type")["object_literal"].to_list() == ["ORG"]


def test_literal_value_never_uses_the_clock():
    from triplum.extract.rules import literal_value

    assert literal_value("yesterday", "date") == ("string", "yesterday")
    assert literal_value("1,250", "number") == ("number", "1250")
    assert literal_value("three", "number") == ("string", "three")
    assert literal_value("2.5", "number") == ("number", "2.5")


def test_trailing_punctuation_does_not_split_an_entity():
    assert normalise("Acme Corp.") == normalise("Acme Corp") == "acme corp"


def test_rules_spec_is_pinned(rules):
    assert rules.spec.name == "rules" and rules.spec.model == "en_core_web_sm"
    assert rules.spec.revision == "3.8.0"


def test_appositions_inside_reported_speech_are_subordinate(rules):
    assert run(rules, "Bob Jones said that Alice Smith, a chemist, founded Acme Corp.") == [
        ("Alice Smith", "be", "a chemist", "subordinate", "apposition"),
        ("Alice Smith", "found", "Acme Corp.", "subordinate", "active"),
    ]
