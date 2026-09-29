from pathlib import Path

from triplum.steps.indexing import index_folder


def test_index_folder_composes_steps(tmp_path: Path):
    (tmp_path / "b.md").write_text("xyz", encoding="utf-8")
    (tmp_path / "a.md").write_text("12345", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not markdown", encoding="utf-8")

    chunks = index_folder(tmp_path, chunk_size=3)
    assert [(c.origin, c.start, c.text) for c in chunks] == [
        (str(tmp_path / "a.md"), 0, "123"),
        (str(tmp_path / "a.md"), 3, "45"),
        (str(tmp_path / "b.md"), 0, "xyz"),
    ]
