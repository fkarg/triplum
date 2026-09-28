from pathlib import Path

import pytest

from triplum.datasets.markdownfolder import MarkdownFolder


def test_top_level_markdown_files_in_name_order(tmp_path: Path):
    (tmp_path / "b.md").write_bytes("é\r\nx".encode())
    (tmp_path / "a.md").write_text("first", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not markdown", encoding="utf-8")
    (tmp_path / "nested.md").mkdir()
    (tmp_path / "nested.md" / "child.md").write_text("not top level", encoding="utf-8")

    dataset = MarkdownFolder(tmp_path)
    assert [(s.origin, s.text) for s in dataset] == [
        (tmp_path.resolve() / "a.md", "first"),
        (tmp_path.resolve() / "b.md", "é\r\nx"),
    ]


def test_fingerprint_follows_content(tmp_path: Path):
    (tmp_path / "a.md").write_text("one", encoding="utf-8")
    before = MarkdownFolder(tmp_path).fingerprint()
    assert MarkdownFolder(tmp_path).fingerprint() == before
    (tmp_path / "a.md").write_text("two", encoding="utf-8")
    assert MarkdownFolder(tmp_path).fingerprint() != before


def test_missing_folder(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        MarkdownFolder(tmp_path / "missing")
