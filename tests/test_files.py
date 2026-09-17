"""Pinned files fetch on first use, verify once, and identify themselves without reading."""

import pytest
from triplum.datasets import files
from triplum.datasets.files import File, Files
from triplum.settings import Settings

EMPTY = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"  # sha256 of "[]"


def _files():
    return (
        File(url="http://x/q", name="t/questions.json", sha256=EMPTY),
        File(url="http://x/c", name="t/corpus.json", sha256=EMPTY, bytes=2),
    )


def test_settings_read_the_environment_and_expand_home(monkeypatch, tmp_path):
    monkeypatch.setenv("TRIPLUM_DATA", str(tmp_path / "d"))
    monkeypatch.setenv("TRIPLUM_MIRRORS", '{"http://x/": "http://mirror/x/"}')
    s = Settings()
    assert s.data == tmp_path / "d" and s.cache == Settings().cache
    assert s.mirrored("http://x/q") == "http://mirror/x/q" and s.mirrored("http://y") == "http://y"
    assert Settings(data="~/z").data == (tmp_path.home() / "z")


def test_status_reports_missing_partial_verified_and_invalid(tmp_path):
    fs = Files(_files(), Settings(data=tmp_path))
    questions, corpus = tmp_path / "t" / "questions.json", tmp_path / "t" / "corpus.json"
    assert fs.status() == "not downloaded"
    questions.parent.mkdir()
    questions.write_text("[]")
    assert fs.status() == "partial"
    corpus.write_text("[]")
    assert fs.status() == "verified"
    corpus.write_text("bad")
    assert fs.status() == "invalid"
    with pytest.raises(files.HashMismatch):
        fs.fetch()
    assert fs.bytes == 2 and not fs.large
    assert Files((File(url="u", name="a", sha256="0" * 64, bytes=files.LARGE_BYTES + 1),)).large


def test_fetch_downloads_missing_files_through_a_mirror_and_verifies_once(monkeypatch, tmp_path):
    fetched = []

    def fake_retrieve(url, tmp):
        fetched.append(url)
        tmp.write_text("[]")

    monkeypatch.setattr(files.urllib.request, "urlretrieve", fake_retrieve)
    hashed = []
    real = files.sha256_file
    monkeypatch.setattr(files, "sha256_file", lambda p: hashed.append(p) or real(p))
    fs = Files(_files(), Settings(data=tmp_path, mirrors={"http://x/": "http://m/"}))
    local = fs.fetch()
    assert fetched == ["http://m/q", "http://m/c"] and len(hashed) == 2
    assert local["t/corpus.json"].read_text() == "[]"
    assert not (tmp_path / "t" / "corpus.json.part").exists()
    assert fs.fetch() is local and len(hashed) == 2  # verified once per instance


def test_fingerprint_needs_no_files(tmp_path):
    fs = Files(_files(), Settings(data=tmp_path / "missing"))
    assert fs.fingerprint() == Files(_files(), Settings(data=tmp_path / "elsewhere")).fingerprint()
    other = (File(url="http://x/q", name="t/questions.json", sha256="1" * 64),)
    assert fs.fingerprint() != Files(other).fingerprint()


def test_manifest_files_are_pinned():
    pinned = files.manifest_files("popqa")
    assert pinned and all(len(f.sha256) == 64 and f.name.startswith("popqa/") for f in pinned)
