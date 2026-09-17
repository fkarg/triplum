"""A folder of PDF, Word, Markdown and text files becomes a corpus with portable identity, and a
sidecar questions.jsonl becomes questions with document-level gold."""

import json
import shutil

import pytest
from triplum.bench.inputs import materialize
from triplum.datasets import registry
from triplum.eval.inputs import GoldMappingError
from triplum.ingest import files


def minimal_pdf(pages: list[str]) -> bytes:
    """A valid one-font PDF with one text line per page, written by hand."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font_no = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font_no} 0 R >> >> >>"
        )
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content.decode()}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def docx_bytes(paragraphs: list[str]) -> bytes:
    import io

    from docx import Document

    doc = Document()
    doc.core_properties.title = "A Word title"
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_chunk_packs_paragraphs_and_splits_long_ones():
    text = "aaa\n\nbbb\n\n" + "c" * 30 + "\n\nddd"
    spans = files.chunk(text, max_chars=12)
    assert [text[s:e] for s, e in spans] == ["aaa\n\nbbb", "c" * 12, "c" * 12, "c" * 6, "ddd"]
    assert files.chunk("\n\n  \n") == []


def test_folder_becomes_a_corpus_with_questions(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "paper.pdf").write_bytes(minimal_pdf(["Graphs help retrieval.", ""]))
    (tmp_path / "notes.md").write_text("# Notes\n\nSecond paragraph.\n", encoding="utf-8")
    (tmp_path / "memo.docx").write_bytes(docx_bytes(["Memo one.", "Memo two."]))
    (tmp_path / "ignored.png").write_bytes(b"\x89PNG")
    (tmp_path / "questions.jsonl").write_text(
        json.dumps({"question": "What helps?", "answer": "Graphs", "gold": ["sub/paper.pdf"]})
        + "\n",
        encoding="utf-8",
    )
    benchmark = registry.load(str(tmp_path))
    assert benchmark.corpus is not None and benchmark.qa is not None
    identity = benchmark.corpus.fingerprint()  # no parse: the PDF reader is never imported here
    ds = materialize(benchmark)
    assert ds.name == f"files:{tmp_path.name}" and ds.corpus_hash == identity
    assert ds.corpus.documents["id"].to_list() == ["memo.docx", "notes.md", "sub/paper.pdf"]
    meta = json.loads(
        ds.corpus.documents.filter(ds.corpus.documents["id"] == "sub/paper.pdf")["metadata"][0]
    )
    assert meta["pages"] == 2 and meta["empty_pages"] == 1 and len(meta["sha256"]) == 64
    assert json.loads(ds.corpus.documents["metadata"][0])["title"] == "A Word title"
    texts = dict(zip(ds.corpus.chunks["document_id"], ds.corpus.chunks["text"]))
    assert texts["sub/paper.pdf"].strip() == "Graphs help retrieval."
    assert texts["memo.docx"] == "Memo one.\n\nMemo two."
    assert ds.corpus.documents["uri"].null_count() == 3
    assert ds.corpus.documents["observed_at"].to_list() == [0, 0, 0]
    assert ds.qa is not None
    q = ds.qa.row(0, named=True)
    gold = ds.corpus.chunks.filter(ds.corpus.chunks["document_id"] == "sub/paper.pdf")[
        "id"
    ].to_list()
    assert q["gold_chunk_ids"] == gold and q["id"] == "0"
    # identity is portable: a copy of the folder under another name hashes the same
    copy = tmp_path.parent / (tmp_path.name + "-copy")
    shutil.copytree(tmp_path, copy)
    assert materialize(registry.load(str(copy))).corpus_hash == ds.corpus_hash


def test_missing_gold_file_fails_loudly(tmp_path):
    (tmp_path / "a.txt").write_text("text", encoding="utf-8")
    (tmp_path / "questions.jsonl").write_text(
        json.dumps({"question": "q", "answer": "a", "gold": ["b.txt"]}), encoding="utf-8"
    )
    with pytest.raises(GoldMappingError):
        materialize(registry.load(str(tmp_path)))


def test_folder_without_questions_is_extraction_only(tmp_path):
    (tmp_path / "a.txt").write_text("Only text.", encoding="utf-8")
    ds = materialize(registry.load(str(tmp_path)))
    assert ds.qa is None and ds.corpus.chunks.height == 1
    assert registry.get(str(tmp_path)).fixture is False
    assert registry.pinned(str(tmp_path)).status() == "not downloaded"  # nothing pinned


def test_question_identity_follows_the_files_it_parses(tmp_path):
    (tmp_path / "a.txt").write_text("one paragraph", encoding="utf-8")
    (tmp_path / "questions.jsonl").write_text(
        json.dumps({"question": "q", "answer": "a", "gold": ["a.txt"]}), encoding="utf-8"
    )
    before = files.FolderQuestions(tmp_path)
    one = before.fingerprint()
    assert len(before[0].gold) == 1
    (tmp_path / "a.txt").write_text("\n\n".join(["p" * 1000] * 4), encoding="utf-8")
    after = files.FolderQuestions(tmp_path)
    assert len(after[0].gold) == 4 and after.fingerprint() != one
