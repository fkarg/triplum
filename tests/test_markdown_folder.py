from pathlib import Path
from uuid import UUID

import pytest

from triplum.datasets.markdownfolder import MarkdownFolder

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")


def test_top_level_markdown_files_in_name_order(tmp_path: Path):
    (tmp_path / "b.md").write_bytes("é\r\nx".encode())
    (tmp_path / "a.md").write_text("first", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not markdown", encoding="utf-8")
    (tmp_path / "nested.md").mkdir()
    (tmp_path / "nested.md" / "child.md").write_text("not top level", encoding="utf-8")

    dataset = MarkdownFolder(tmp_path, collection_id=COLLECTION)
    assert {s.collection_id for s in dataset} == {COLLECTION}
    assert [(s.origin, s.text) for s in dataset] == [
        (str(tmp_path.resolve() / "a.md"), "first"),
        (str(tmp_path.resolve() / "b.md"), "é\r\nx"),
    ]


def test_fingerprint_follows_content(tmp_path: Path):
    (tmp_path / "a.md").write_text("one", encoding="utf-8")
    before = MarkdownFolder(tmp_path, collection_id=COLLECTION).fingerprint()
    assert MarkdownFolder(tmp_path, collection_id=COLLECTION).fingerprint() == before
    (tmp_path / "a.md").write_text("two", encoding="utf-8")
    assert MarkdownFolder(tmp_path, collection_id=COLLECTION).fingerprint() != before


def test_fingerprint_covers_location(tmp_path: Path):
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "n.md").write_text("same", encoding="utf-8")

    a = MarkdownFolder(tmp_path / "a", collection_id=COLLECTION).fingerprint()
    assert MarkdownFolder(tmp_path / "b", collection_id=COLLECTION).fingerprint() != a


def test_missing_folder(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        MarkdownFolder(tmp_path / "missing", collection_id=COLLECTION)


def test_fingerprint_covers_collection(tmp_path: Path):
    (tmp_path / "a.md").write_text("same", encoding="utf-8")
    other = UUID("01900000-0000-7000-8000-000000000002")
    assert (
        MarkdownFolder(tmp_path, collection_id=COLLECTION).fingerprint()
        != MarkdownFolder(tmp_path, collection_id=other).fingerprint()
    )
