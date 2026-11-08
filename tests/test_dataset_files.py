import hashlib
import http.client
import io
import json
from pathlib import Path
from uuid import UUID

import pytest

from triplum.datasets import files, hotpotqa, multihoprag
from triplum.datasets.files import DatasetEntry, PinnedFile, datasets_home, download, fetch
from triplum.datatype import SpanEvidence

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(name: str, remote: Path, *names: str) -> DatasetEntry:
    """An entry whose files are served from `remote` over file:// URLs."""
    pinned = [
        PinnedFile(
            name=n,
            url=(remote / n).as_uri(),
            sha256=_sha((remote / n).read_bytes()),
            bytes=len((remote / n).read_bytes()),
        )
        for n in names
    ]
    return DatasetEntry(name=name, files=pinned, licence="L", commercial_reuse="C")


def test_datasets_live_beside_the_computation_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert datasets_home() == tmp_path / "triplum" / "datasets"
    monkeypatch.setenv("XDG_CACHE_HOME", "relative")
    assert datasets_home() == Path.home() / ".cache" / "triplum" / "datasets"


def test_fetch_downloads_once_then_keeps_the_verified_file(tmp_path: Path):
    remote = tmp_path / "remote.json"
    remote.write_bytes(b"[1]")
    target = tmp_path / "cache" / "data.json"
    assert fetch(remote.as_uri(), target, _sha(b"[1]")).read_bytes() == b"[1]"
    remote.write_bytes(b"[2]")  # upstream changed: the verified copy is used, nothing fetched
    assert fetch(remote.as_uri(), target, _sha(b"[1]")).read_bytes() == b"[1]"


def test_an_existing_corrupt_file_raises_and_is_kept(tmp_path: Path):
    remote = tmp_path / "remote.json"
    remote.write_bytes(b"[1]")
    target = tmp_path / "data.json"
    target.write_bytes(b"[9]")
    with pytest.raises(ValueError, match=f"has sha256 {_sha(b'[9]')}, expected {_sha(b'[1]')}"):
        fetch(remote.as_uri(), target, _sha(b"[1]"))
    assert target.read_bytes() == b"[9]"


@pytest.mark.parametrize("name", ["../keep.txt", "sub/a.json", "..", "", "a\\b"])
def test_file_and_dataset_names_must_stay_inside_their_folder(name: str):
    with pytest.raises(ValueError, match="plain name"):
        PinnedFile(name=name, url="file:///x", sha256="0" * 64, bytes=0)
    with pytest.raises(ValueError, match="plain name"):
        DatasetEntry(name=name, files=[], licence="L", commercial_reuse="C")


@pytest.mark.parametrize("field", ["licence", "commercial_reuse"])
def test_licence_terms_must_be_recorded_explicitly(field: str):
    terms = {"licence": "L", "commercial_reuse": "C", field: ""}
    with pytest.raises(ValueError, match="at least 1 character"):
        DatasetEntry(name="demo", files=[], **terms)


def test_protocol_failures_name_the_url_and_destination(tmp_path: Path, monkeypatch):
    def malformed(url, timeout):
        raise http.client.BadStatusLine("not an HTTP status")

    monkeypatch.setattr(files.urllib.request, "urlopen", malformed)
    target = tmp_path / "demo" / "a.json"
    with pytest.raises(OSError, match=f"downloading file:///x to {target} failed: not an HTTP"):
        fetch("file:///x", target, _sha(b""))


def test_a_directory_at_the_file_path_raises(tmp_path: Path):
    (tmp_path / "data.json").mkdir()
    with pytest.raises(ValueError, match="is not a file"):
        fetch("file:///unused", tmp_path / "data.json", _sha(b""))


def test_failed_or_unexpected_downloads_leave_nothing(tmp_path: Path):
    remote = tmp_path / "remote.json"
    remote.write_bytes(b"[2]")
    cache = tmp_path / "cache"
    with pytest.raises(ValueError, match=f"to {cache / 'other.json'} failed: sha256"):
        fetch(remote.as_uri(), cache / "other.json", _sha(b"[1]"))
    with pytest.raises(OSError):
        fetch((tmp_path / "missing").as_uri(), cache / "gone.json", _sha(b"[1]"))
    assert list(cache.iterdir()) == []


def test_concurrent_fetches_do_not_share_a_partial_file(tmp_path: Path, monkeypatch):
    # Regression: both calls once wrote `<name>.part`; a second download failing mid-transfer
    # truncated (and then deleted) the first one's file before it was renamed into place.
    target = tmp_path / "data.json"

    class First(io.BytesIO):
        def read(self, size=-1):
            if self.tell() == 0:  # the second download runs while the first is writing
                with pytest.raises(OSError):
                    fetch("second", target, _sha(b"[1]"))
            return super().read(size)

    class Dropped(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("connection reset")
            return super().read(1)

    def urlopen(url, timeout):
        return First(b"[1]") if url == "first" else Dropped(b"[1]")

    monkeypatch.setattr(files.urllib.request, "urlopen", urlopen)
    assert fetch("first", target, _sha(b"[1]")).read_bytes() == b"[1]"
    assert [p.name for p in tmp_path.iterdir()] == ["data.json"]


def test_download_fetches_entry_files_in_order_and_keeps_them_on_failure(tmp_path: Path):
    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / "a.json").write_bytes(b"[1]")
    (remote / "b.json").write_bytes(b"[2]")
    entry = _entry("demo", remote, "a.json", "b.json")
    (remote / "b.json").write_bytes(b"[3]")  # b no longer matches its pin
    with pytest.raises(ValueError, match="expected the pinned"):
        download(entry, tmp_path / "root")
    assert [p.name for p in (tmp_path / "root" / "demo").iterdir()] == ["a.json"]


# Title lengths give offsets 2 and 3, so offset arithmetic is not hidden by bit coincidences.
SENTENCES = {"A": ["Alpha one.", " Alpha two."], "Bb": ["Beta."], "C": ["Gamma."]}


def _hotpotqa(tmp_path: Path, monkeypatch, supporting_facts, sentences=SENTENCES) -> Path:
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
    (remote / "hotpotqa.json").write_text(json.dumps([question]))
    (remote / "hotpotqa_corpus.json").write_text(json.dumps(corpus))
    entry = _entry("hotpotqa", remote, "hotpotqa.json", "hotpotqa_corpus.json")
    monkeypatch.setattr(hotpotqa, "ENTRY", entry)
    return tmp_path / "root"


def _span(document: str, start: int, end: int) -> SpanEvidence:
    return SpanEvidence(document=document, start=start, end=end)


@pytest.mark.parametrize(
    ("gold", "expected"),
    [
        # "A\nAlpha one. Alpha two.": "Alpha one." is [2, 12), " Alpha two." [12, 23).
        ("sentence", [_span("A", 12, 23), _span("Bb", 3, 8), _span("A", 2, 12)]),
        ("passage", [_span("A", 0, 23), _span("Bb", 0, 8)]),
    ],
)
def test_hotpotqa_gold_spans_select_the_supporting_text(tmp_path, monkeypatch, gold, expected):
    root = _hotpotqa(tmp_path, monkeypatch, [["A", 1], ["Bb", 0], ["A", 0], ["A", 1]])
    benchmark = hotpotqa.HotpotQA(root, gold=gold)
    [question] = benchmark.questions()
    assert question.evidence == [expected]
    texts = {s.external_id: s.text for s in benchmark.corpus(COLLECTION)}
    selected = [texts[span.document][span.start : span.end] for span in expected]
    if gold == "sentence":
        assert selected == [" Alpha two.", "Beta.", "Alpha one."]
    else:
        assert selected == [texts["A"], texts["Bb"]]
    assert (question.id, question.input.text, question.answers) == ("q1", "Which?", ["Alpha"])
    assert question.metadata == {"type": "bridge", "level": "easy"}
    assert (root / "hotpotqa" / "hotpotqa.json").is_file()


def test_hotpotqa_corpus_is_title_newline_text_keyed_by_title(tmp_path, monkeypatch):
    benchmark = hotpotqa.HotpotQA(_hotpotqa(tmp_path, monkeypatch, [["Bb", 0]]))
    assert [(s.origin, s.external_id, s.text) for s in benchmark.corpus(COLLECTION)] == [
        ("A", "A", "A\nAlpha one. Alpha two."),
        ("Bb", "Bb", "Bb\nBeta."),
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
        hotpotqa.HotpotQA(_hotpotqa(tmp_path, monkeypatch, facts, sentences))


def test_multihoprag_downloads_into_root_on_first_use(tmp_path: Path, monkeypatch):
    remote = tmp_path / "remote"
    remote.mkdir()
    articles = [{"url": "https://example.org/a", "title": "T", "body": "Body."}]
    (remote / "corpus.json").write_text(json.dumps(articles))
    monkeypatch.setattr(multihoprag, "ENTRY", _entry("multihoprag", remote, "corpus.json"))
    corpus = multihoprag.MultiHopRAGCorpus(collection_id=COLLECTION, root=tmp_path / "root")
    assert (tmp_path / "root" / "multihoprag" / "corpus.json").is_file()
    assert [(s.origin, s.text) for s in corpus] == [("https://example.org/a", "T\n\nBody.")]
