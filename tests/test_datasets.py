import json
from dataclasses import replace

import polars as pl
import pytest
from triplum.bench.inputs import Benchmark, materialize
from triplum.datasets import base, registry
from triplum.datasets import hipporag as hr
from triplum.eval.inputs import QAEvaluation


def _never(paths, n) -> Benchmark:
    raise AssertionError("parser must not run")


def _mini_hotpot(tmp_path):
    questions = [
        {
            "_id": "q1",
            "question": "Who?",
            "answer": "Bob",
            "type": "bridge",
            "level": "hard",
            "supporting_facts": [["A", 0], ["B", 0]],
            "context": [["A", ["Alice met Bob."]], ["B", ["Bob is tall."]], ["C", ["Noise."]]],
        },
        {
            "_id": "q2",
            "question": "What?",
            "answer": "yes",
            "type": "comparison",
            "level": "hard",
            "supporting_facts": [["C", 0]],
            "context": [["C", ["Noise."]], ["D", ["Other."]]],
        },
    ]
    corpus = [
        {"idx": 0, "title": "A", "text": "Alice met Bob."},
        {"idx": 1, "title": "B", "text": "Bob is tall."},
        {"idx": 2, "title": "C", "text": "Noise."},
        {"idx": 3, "title": "D", "text": "Other."},
    ]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text(json.dumps(questions))
    cp.write_text(json.dumps(corpus))
    return qp, cp


def test_parse_hotpot_style(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    fr = materialize(hr.load_files("hotpotqa", qp, cp))
    assert fr.corpus.chunks.height == 4 and fr.corpus.documents.height == 4
    assert fr.extraction is None
    assert fr.qa is not None
    q = fr.qa.filter(fr.qa["id"] == "q1").row(0, named=True)
    assert q["answer"] == "Bob" and sorted(q["gold_chunk_ids"]) == [1, 2]
    assert q["aliases"] == ["Bob"] and q["answerable"] and q["as_of"] is None
    assert json.loads(q["metadata"])["candidate_chunk_ids"] == [1, 2, 3]
    assert fr.corpus.chunks.filter(fr.corpus.chunks["id"] == 1)["text"][0] == "A\nAlice met Bob."
    assert fr.corpus.grants["principal"].unique().to_list() == ["public"]


def test_parse_musique_style(tmp_path):
    questions = [
        {
            "id": "m1",
            "question": "Q",
            "answer": "X",
            "answer_aliases": ["Y"],
            "answerable": True,
            "paragraphs": [
                {"idx": 0, "title": "T", "paragraph_text": "one", "is_supporting": True},
                {"idx": 1, "title": "T", "paragraph_text": "two", "is_supporting": True},
                {"idx": 2, "title": "U", "paragraph_text": "three", "is_supporting": False},
            ],
            "question_decomposition": [],
        }
    ]
    corpus = [
        {"title": "T", "text": "one"},
        {"title": "T", "text": "two"},
        {"title": "U", "text": "three"},
    ]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text(json.dumps(questions))
    cp.write_text(json.dumps(corpus))
    inputs = materialize(hr.load_files("musique", qp, cp))
    assert inputs.qa is not None
    q = inputs.qa.row(0, named=True)
    assert sorted(q["gold_chunk_ids"]) == [1, 2] and q["aliases"] == ["X", "Y"]


def test_subset_by_n_keeps_order(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    inputs = materialize(hr.load_files("hotpotqa", qp, cp, n=1))
    assert inputs.qa is not None
    assert inputs.qa["id"].to_list() == ["q1"]


def test_verify_hash_mismatch_raises(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[]")
    with pytest.raises(base.HashMismatch):
        base.verify(p, "0" * 64)


def test_status_reports_missing_partial_verified_and_invalid_artifacts(tmp_path):
    empty = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    spec = base.Spec(
        "status-test",
        "test",
        (
            base.File("http://x/q", "t/questions.json", empty),
            base.File("http://x/c", "t/corpus.json", empty),
        ),
        "none",
        _never,
    )
    questions, corpus = tmp_path / "t" / "questions.json", tmp_path / "t" / "corpus.json"
    assert base.status(spec, tmp_path).state == "not downloaded"
    questions.parent.mkdir()
    questions.write_text("[]")
    assert base.status(spec, tmp_path).state == "partial"
    corpus.write_text("[]")
    assert base.status(spec, tmp_path).state == "verified"
    corpus.write_text("bad")
    assert base.status(spec, tmp_path).state == "invalid"
    assert not (tmp_path / "t" / "questions.json.part").exists()


def test_registry_specs_are_pinned_and_fixtures_load():
    for name, spec in registry.SPECS.items():
        assert spec.name == name and all(len(f.sha256) == 64 for f in spec.files)
        assert spec.files, name
        if not spec.fixture:
            continue
        ds = materialize(registry.load_fixture(name))
        assert ds.qa is not None or ds.extraction is not None, name
        for key, schema in base.CORPUS_SCHEMAS.items():
            assert dict(getattr(ds.corpus, key).schema) == schema, (name, key)
        if ds.extraction is not None:
            assert dict(ds.extraction.schema) == base.TRIPLE_SCHEMA
        assert len(ds.corpus_hash) == 64 and len(ds.evaluation_hash) == 64
        if ds.qa is None:
            continue
        assert dict(ds.qa.schema) == base.QUESTION_SCHEMA
        chunk_ids = set(ds.corpus.chunks["id"].to_list())
        for gold, q_answerable in zip(
            ds.qa["gold_chunk_ids"].to_list(), ds.qa["answerable"].to_list()
        ):
            assert set(gold) <= chunk_ids, name
            assert gold or ds.corpus.chunks.height == 0 or not q_answerable or spec.needs, name


def test_protocol_fixtures_have_twenty_questions():
    for name in ("hotpotqa", "musique", "twowiki"):
        ds = materialize(registry.load_fixture(name))
        assert ds.qa is not None
        assert ds.qa.height == 20 and ds.corpus.chunks.height > 20
        short = materialize(registry.load_fixture(name, n=3))
        assert short.qa is not None and short.qa.height == 3
    gold = materialize(registry.load_fixture("twowiki")).extraction
    assert gold is not None and gold.height > 0


def test_fixture_round_trip_and_hashes(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    frames = hr.load_files("hotpotqa", qp, cp)
    path = base.write_fixture("rt", base.subset(frames, n=1, distractors=1), tmp_path / "rt.json")
    ds = materialize(base.read_fixture("rt", path=path))
    assert ds.qa is not None
    assert ds.qa.height == 1 and ds.corpus.chunks.height == 4  # gold + candidates + one filler
    assert ds.corpus_hash != ds.evaluation_hash


def test_identity_follows_parsed_content_not_source_bytes(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    source = hr.load_files("hotpotqa", qp, cp)
    ds = materialize(source)
    retitled = replace(
        source,
        corpus=[
            ds.corpus._replace(
                chunks=ds.corpus.chunks.with_columns(pl.col("text").str.to_uppercase())
            )
        ],
    )
    assert materialize(retitled).corpus_hash != ds.corpus_hash
    assert materialize(retitled).evaluation_hash == ds.evaluation_hash
    assert ds.qa is not None
    fewer = replace(source, qa=QAEvaluation([ds.qa.head(1)]))
    assert materialize(fewer).corpus_hash == ds.corpus_hash
    assert materialize(fewer).evaluation_hash != ds.evaluation_hash
    private = replace(
        source,
        corpus=[
            ds.corpus._replace(
                grants=ds.corpus.grants.with_columns(pl.lit("staff").alias("principal"))
            )
        ],
    )
    assert materialize(private).corpus_hash != ds.corpus_hash


def test_large_is_derived_from_pinned_bytes():
    small = base.Spec("s", "t", (base.File("u", "a", "0" * 64, 10),), "none", _never)
    big = base.Spec(
        "b", "t", (base.File("u", "a", "0" * 64, base.LARGE_BYTES + 1),), "none", _never
    )
    assert not small.large and big.large and big.bytes == base.LARGE_BYTES + 1


def test_missing_gold_raises(tmp_path):
    questions = [
        {
            "_id": "q1",
            "question": "Who?",
            "answer": "Bob",
            "type": "bridge",
            "level": "hard",
            "supporting_facts": [["ZZZ", 0]],
            "context": [["A", ["x"]]],
        }
    ]
    corpus = [{"idx": 0, "title": "A", "text": "x"}]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text(json.dumps(questions))
    cp.write_text(json.dumps(corpus))
    with pytest.raises(base.GoldMappingError):
        materialize(hr.load_files("hotpotqa", qp, cp))


def test_duplicate_corpus_key_raises(tmp_path):
    corpus = [{"idx": 0, "title": "A", "text": "x"}, {"idx": 1, "title": "A", "text": "y"}]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text("[]")
    cp.write_text(json.dumps(corpus))
    with pytest.raises(base.GoldMappingError):
        materialize(hr.load_files("hotpotqa", qp, cp))


def test_question_row_dedups_aliases_and_sorts_gold():
    row = base.question_row("q", "?", "a", ["b", "a", "b"], [3, 1, 3])
    assert row[3] == ["a", "b"] and row[4] == [1, 3] and row[6] is True
    assert pl.DataFrame([row], schema=base.QUESTION_SCHEMA, orient="row").height == 1
