import json

import pytest
from triplum.eval.datasets import hipporag as hr


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
    ds = hr.load_files("hotpotqa", qp, cp)
    assert ds.name == "hotpotqa" and ds.chunks.height == 4 and ds.documents.height == 4
    q = ds.questions.filter(ds.questions["id"] == "q1").row(0, named=True)
    assert q["answer"] == "Bob" and sorted(q["gold_chunk_ids"]) == [1, 2]
    assert q["aliases"] == ["Bob"]
    assert ds.chunks.filter(ds.chunks["id"] == 1)["text"][0] == "A\nAlice met Bob."
    assert ds.grants["principal"].unique().to_list() == ["public"]
    assert len(ds.corpus_hash) == 64 and len(ds.questions_hash) == 64


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
    ds = hr.load_files("musique", qp, cp)
    q = ds.questions.row(0, named=True)
    assert sorted(q["gold_chunk_ids"]) == [1, 2] and q["aliases"] == ["X", "Y"]


def test_subset_by_n_keeps_order(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    ds = hr.load_files("hotpotqa", qp, cp, n=1)
    assert ds.questions["id"].to_list() == ["q1"]


def test_verify_hash_mismatch_raises(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[]")
    with pytest.raises(hr.HashMismatch):
        hr.verify(p, "0" * 64)


def test_status_reports_missing_partial_verified_and_invalid_artifacts(tmp_path, monkeypatch):
    monkeypatch.setitem(hr.FILES, "status-test", ("questions.json", "corpus.json"))
    protocol_root = tmp_path / "hipporag"
    questions, corpus = protocol_root / "questions.json", protocol_root / "corpus.json"
    monkeypatch.setitem(
        hr.HASHES,
        "questions.json",
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    )
    monkeypatch.setitem(
        hr.HASHES, "corpus.json", "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    )

    assert hr.status("status-test", tmp_path).state == "not downloaded"
    protocol_root.mkdir()
    questions.write_text("[]")
    assert hr.status("status-test", tmp_path).state == "partial"
    corpus.write_text("[]")
    assert hr.status("status-test", tmp_path).state == "verified"
    corpus.write_text("bad")
    assert hr.status("status-test", tmp_path).state == "invalid"
    corpus.write_text("[]")
    questions.write_text("bad")
    assert hr.status("status-test", tmp_path).state == "invalid"


def test_fixture_files_load():
    for name in ("hotpotqa", "musique", "twowiki"):
        ds = hr.load_fixture(name)
        assert ds.questions.height == 20 and ds.chunks.height > 20
        assert all(len(g) > 0 for g in ds.questions["gold_chunk_ids"].to_list())


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
    with pytest.raises(hr.GoldMappingError):
        hr.load_files("hotpotqa", qp, cp)


def test_duplicate_corpus_key_raises(tmp_path):
    questions = []
    corpus = [{"idx": 0, "title": "A", "text": "x"}, {"idx": 1, "title": "A", "text": "y"}]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text(json.dumps(questions))
    cp.write_text(json.dumps(corpus))
    with pytest.raises(hr.GoldMappingError):
        hr.load_files("hotpotqa", qp, cp)
