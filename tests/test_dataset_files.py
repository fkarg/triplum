import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from triplum.datasets import hotpotqa, multihoprag
from triplum.datasets.files import datasets_home, fetch
from triplum.datatype import SpanEvidence

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_datasets_live_beside_the_computation_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert datasets_home() == tmp_path / "triplum" / "datasets"
    monkeypatch.setenv("XDG_CACHE_HOME", "relative")
    assert datasets_home() == Path.home() / ".cache" / "triplum" / "datasets"


def test_fetch_downloads_once_and_keeps_only_verified_files(tmp_path: Path):
    remote = tmp_path / "remote.json"
    remote.write_bytes(b"[1]")
    target = tmp_path / "cache" / "data.json"
    assert fetch(remote.as_uri(), target, _sha(b"[1]")) == target
    assert target.read_bytes() == b"[1]"

    remote.write_bytes(b"[2]")  # upstream changed: the verified copy is kept, no download
    assert fetch(remote.as_uri(), target, _sha(b"[1]")).read_bytes() == b"[1]"

    with pytest.raises(ValueError, match="does not match the pinned sha256"):
        fetch(remote.as_uri(), tmp_path / "cache" / "other.json", _sha(b"[1]"))
    with pytest.raises(OSError):  # a failed transfer leaves nothing behind either
        fetch((tmp_path / "missing").as_uri(), tmp_path / "cache" / "gone.json", _sha(b"[1]"))
    assert sorted(p.name for p in (tmp_path / "cache").iterdir()) == ["data.json"]


SENTENCES = {"A": ["Alpha one.", " Alpha two."], "B": ["Beta."], "C": ["Gamma."]}


def _files(tmp_path: Path, monkeypatch, supporting_facts, sentences=SENTENCES) -> Path:
    corpus = [
        {"idx": i, "title": t, "text": "".join(s)} for i, (t, s) in enumerate(SENTENCES.items())
    ]
    question = {
        "_id": "q1",
        "question": "Which?",
        "answer": "Alpha",
        "supporting_facts": supporting_facts,
        "context": [[t, s] for t, s in sentences.items()],
        "type": "bridge",
        "level": "easy",
    }
    remote = tmp_path / "remote"
    remote.mkdir()
    files = {"hotpotqa.json": [question], "hotpotqa_corpus.json": corpus}
    for name, content in files.items():
        (remote / name).write_text(json.dumps(content))
    monkeypatch.setattr(hotpotqa, "BASE", remote.as_uri() + "/")
    monkeypatch.setattr(hotpotqa, "FILES", {n: _sha((remote / n).read_bytes()) for n in files})
    return tmp_path / "root"


def _span(document: str, start: int, end: int) -> SpanEvidence:
    return SpanEvidence(document=document, start=start, end=end)


@pytest.mark.parametrize(
    ("gold", "expected"),
    [
        # "A\nAlpha one. Alpha two.": "Alpha one." is [2, 12), " Alpha two." [12, 23).
        ("sentence", [_span("A", 12, 23), _span("B", 2, 7), _span("A", 2, 12)]),
        ("passage", [_span("A", 0, 23), _span("B", 0, 7)]),
    ],
)
def test_hotpotqa_gold_spans_select_the_supporting_text(tmp_path, monkeypatch, gold, expected):
    root = _files(tmp_path, monkeypatch, [["A", 1], ["B", 0], ["A", 0], ["A", 1]])
    benchmark = hotpotqa.HotpotQA(root, gold=gold)
    [question] = benchmark.questions()
    assert question.evidence == [expected]
    texts = {s.external_id: s.text for s in benchmark.corpus(COLLECTION)}
    assert texts["A"][12:23] == " Alpha two."
    assert (question.id, question.input.text, question.answers) == ("q1", "Which?", ["Alpha"])
    assert question.metadata == {"type": "bridge", "level": "easy"}


def test_hotpotqa_corpus_is_title_newline_text_keyed_by_title(tmp_path, monkeypatch):
    benchmark = hotpotqa.HotpotQA(_files(tmp_path, monkeypatch, [["B", 0]]))
    assert [(s.origin, s.external_id, s.text) for s in benchmark.corpus(COLLECTION)] == [
        ("A", "A", "A\nAlpha one. Alpha two."),
        ("B", "B", "B\nBeta."),
        ("C", "C", "C\nGamma."),
    ]


@pytest.mark.parametrize(
    ("facts", "sentences"),
    [
        ([["Z", 0]], SENTENCES),  # unknown passage
        ([["A", 2]], SENTENCES),  # no such sentence
        ([["A", -1]], SENTENCES),  # negative indices would count from the end
        ([["A", 0]], {**SENTENCES, "A": ["Alpha one.", "Alpha two."]}),  # differs from corpus
    ],
    ids=["unknown-title", "sentence-index", "negative-index", "sentences-differ"],
)
def test_hotpotqa_unresolvable_supporting_facts_raise(tmp_path, monkeypatch, facts, sentences):
    with pytest.raises(ValueError, match="question q1"):
        hotpotqa.HotpotQA(_files(tmp_path, monkeypatch, facts, sentences))


def test_multihoprag_downloads_into_root_on_first_use(tmp_path: Path, monkeypatch):
    articles = [{"url": "https://example.org/a", "title": "T", "body": "Body."}]
    remote = tmp_path / "corpus.json"
    remote.write_text(json.dumps(articles))
    monkeypatch.setattr(multihoprag, "URL", remote.as_uri())
    monkeypatch.setattr(multihoprag, "SHA256", _sha(remote.read_bytes()))
    corpus = multihoprag.MultiHopRAGCorpus(collection_id=COLLECTION, root=tmp_path / "root")
    assert (tmp_path / "root" / "multihoprag" / "corpus.json").is_file()
    assert [(s.origin, s.text) for s in corpus] == [("https://example.org/a", "T\n\nBody.")]


def test_concurrent_fetches_do_not_share_a_partial_file(tmp_path: Path, monkeypatch):
    # Regression: both calls once wrote `<name>.part`; a second download failing mid-transfer
    # truncated the first one's verified file before it was renamed into place.
    from triplum.datasets import files

    target = tmp_path / "data.json"

    def interleaved(url: str, filename: Path):
        if url == "first":
            Path(filename).write_bytes(b"[1]")
            with pytest.raises(OSError):
                fetch("second", target, _sha(b"[1]"))
            return filename, None
        Path(filename).write_bytes(b"[")  # partial transfer, then the connection drops
        raise OSError("connection reset")

    monkeypatch.setattr(files.urllib.request, "urlretrieve", interleaved)
    assert fetch("first", target, _sha(b"[1]")).read_bytes() == b"[1]"
    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]
