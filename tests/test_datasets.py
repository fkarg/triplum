import json

import polars as pl
import pytest
from triplum.eval.datasets import base, registry
from triplum.eval.datasets import hipporag as hr


def _never(paths, n) -> base.Frames:
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
    fr = hr.load_files("hotpotqa", qp, cp)
    assert fr.chunks.height == 4 and fr.documents.height == 4 and fr.triples.height == 0
    q = fr.questions.filter(fr.questions["id"] == "q1").row(0, named=True)
    assert q["answer"] == "Bob" and sorted(q["gold_chunk_ids"]) == [1, 2]
    assert q["aliases"] == ["Bob"] and q["answerable"] and q["as_of"] is None
    assert json.loads(q["metadata"])["candidate_chunk_ids"] == [1, 2, 3]
    assert fr.chunks.filter(fr.chunks["id"] == 1)["text"][0] == "A\nAlice met Bob."
    assert fr.grants["principal"].unique().to_list() == ["public"]


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
    q = hr.load_files("musique", qp, cp).questions.row(0, named=True)
    assert sorted(q["gold_chunk_ids"]) == [1, 2] and q["aliases"] == ["X", "Y"]


def test_subset_by_n_keeps_order(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    assert hr.load_files("hotpotqa", qp, cp, n=1).questions["id"].to_list() == ["q1"]


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
        ds = registry.load_fixture(name)
        assert ds.questions.height > 0 or ds.triples.height > 0, name
        for key, schema in base.SCHEMAS.items():
            assert dict(getattr(ds, key).schema) == schema, (name, key)
        chunk_ids = set(ds.chunks["id"].to_list())
        for gold, q_answerable in zip(
            ds.questions["gold_chunk_ids"].to_list(), ds.questions["answerable"].to_list()
        ):
            assert set(gold) <= chunk_ids, name
            assert gold or ds.chunks.height == 0 or not q_answerable, name
        assert len(ds.corpus_hash) == 64 and len(ds.questions_hash) == 64


def test_protocol_fixtures_have_twenty_questions():
    for name in ("hotpotqa", "musique", "twowiki"):
        ds = registry.load_fixture(name)
        assert ds.questions.height == 20 and ds.chunks.height > 20
        assert registry.load_fixture(name, n=3).questions.height == 3
    assert registry.load_fixture("twowiki").triples.height > 0


def test_fixture_round_trip_and_hashes(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    frames = hr.load_files("hotpotqa", qp, cp)
    path = base.write_fixture("rt", base.subset(frames, n=1, distractors=1), tmp_path / "rt.json")
    ds = base.read_fixture("rt", path=path)
    assert ds.questions.height == 1 and ds.chunks.height == 4  # gold + candidates + one filler
    assert ds.corpus_hash != ds.questions_hash


def test_identity_follows_parsed_content_not_source_bytes(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    frames = hr.load_files("hotpotqa", qp, cp)
    ds = base.dataset("x", frames)
    retitled = frames._replace(chunks=frames.chunks.with_columns(pl.col("text").str.to_uppercase()))
    assert base.dataset("x", retitled).corpus_hash != ds.corpus_hash
    assert base.dataset("x", retitled).questions_hash == ds.questions_hash
    fewer = frames._replace(questions=frames.questions.head(1))
    assert base.dataset("x", fewer).corpus_hash == ds.corpus_hash
    assert base.dataset("x", fewer).questions_hash != ds.questions_hash
    private = frames._replace(grants=frames.grants.with_columns(pl.lit("staff").alias("principal")))
    assert base.dataset("x", private).corpus_hash != ds.corpus_hash


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
        hr.load_files("hotpotqa", qp, cp)


def test_duplicate_corpus_key_raises(tmp_path):
    corpus = [{"idx": 0, "title": "A", "text": "x"}, {"idx": 1, "title": "A", "text": "y"}]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text("[]")
    cp.write_text(json.dumps(corpus))
    with pytest.raises(base.GoldMappingError):
        hr.load_files("hotpotqa", qp, cp)


def test_question_row_dedups_aliases_and_sorts_gold():
    row = base.question_row("q", "?", "a", ["b", "a", "b"], [3, 1, 3])
    assert row[3] == ["a", "b"] and row[4] == [1, 3] and row[6] is True
    assert pl.DataFrame([row], schema=base.QUESTION_SCHEMA, orient="row").height == 1
