"""A folder of local files as a corpus. PDF (text layer only, no OCR), Word (`.docx`), Markdown
and plain text become one document each, chunked by packing paragraphs to about `MAX_CHARS`;
a `questions.jsonl` beside them, with `question`, `answer`, optional `aliases` and `qtype`, and
`gold` as a list of relative file paths, becomes the question frame with every chunk of a gold
file as gold. Identity is portable: document ids are relative paths, `observed_at` is 0 and the
file's sha256 sits in document metadata, so the same folder hashes the same on any machine. A
folder loads through the registry by its path (`triplum bench run --dataset ~/papers`), and an
object-store source only has to yield the same `(relative path, bytes)` pairs.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import polars as pl

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import QAEvaluation

SUFFIXES = {".pdf", ".docx", ".md", ".markdown", ".txt", ".text"}
MAX_CHARS = 1500
QUESTIONS_FILE = "questions.jsonl"
_BLANK = re.compile(r"\n\s*\n")


def read_pdf(data: bytes) -> tuple[list[str], str | None]:
    """Text per page from the PDF's text layer; a page without one is an empty string."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    title = reader.metadata.title if reader.metadata else None
    return [page.extract_text() or "" for page in reader.pages], title or None


def read_docx(data: bytes) -> tuple[list[str], str | None]:
    from docx import Document

    doc = Document(io.BytesIO(data))
    text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [text], doc.core_properties.title or None


def read(name: str, data: bytes) -> tuple[list[str], str | None]:
    """Pages (or one block) of text and the embedded title, if any, for a supported file."""
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return read_pdf(data)
    if suffix == ".docx":
        return read_docx(data)
    return [data.decode("utf-8", errors="replace")], None


def chunk(text: str, max_chars: int = MAX_CHARS) -> list[tuple[int, int]]:
    """Spans of `text` that pack whole paragraphs up to `max_chars`. A longer paragraph is split
    at whitespace into pieces that stand alone. Paragraphs are separated by blank lines."""
    spans: list[tuple[int, int]] = []
    pack: tuple[int, int] | None = None
    pos = 0
    for para in _BLANK.split(text):
        p_start = text.index(para, pos)
        p_end = pos = p_start + len(para)
        if not para.strip():
            continue
        if p_end - p_start > max_chars:
            if pack:
                spans.append(pack)
                pack = None
            while p_end - p_start > max_chars:
                cut = text.rfind(" ", p_start + 1, p_start + max_chars)
                cut = cut if cut > p_start else p_start + max_chars
                spans.append((p_start, cut))
                p_start = cut + 1 if text[cut] == " " else cut
            spans.append((p_start, p_end))
        elif pack and p_end - pack[0] <= max_chars:
            pack = (pack[0], p_end)
        else:
            if pack:
                spans.append(pack)
            pack = (p_start, p_end)
    if pack:
        spans.append(pack)
    return [(a, b) for a, b in spans if text[a:b].strip()]


SOURCE = "files"  # constant, so the corpus hash depends on content only, not the folder name


def frames(files: list[tuple[str, bytes]], n: int | None = None) -> Benchmark:
    """Canonical frames from `(relative path, bytes)` pairs; `questions.jsonl` is the questions."""
    doc_rows, grant_rows, chunk_rows = [], [], []
    chunks_of: dict[str, list[int]] = {}
    questions = None
    for name, data in sorted(files):
        if name == QUESTIONS_FILE:
            questions = data
            continue
        if Path(name).suffix.lower() not in SUFFIXES:
            continue
        pages, title = read(name, data)
        text = "\n\n".join(pages)
        meta = {
            "title": title or Path(name).stem,
            "pages": len(pages),
            "empty_pages": sum(1 for p in pages if not p.strip()),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        doc_rows.append((name, SOURCE, None, 0, json.dumps(meta)))
        grant_rows.append((name, "public", 0, None))
        chunks_of[name] = []
        for s, e in chunk(text):
            cid = len(chunk_rows) + 1
            chunk_rows.append((cid, name, None, 0, s, e, text[s:e]))
            chunks_of[name].append(cid)
    rows = []
    for i, line in enumerate(questions.decode("utf-8").splitlines() if questions else []):
        if not line.strip():
            continue
        q = json.loads(line)
        qid = str(q.get("id", i))
        missing = [g for g in q["gold"] if g not in chunks_of]
        if missing or not q["gold"]:
            raise base.GoldMappingError(f"{SOURCE}: question {qid} gold not in folder: {missing}")
        gold = [cid for g in q["gold"] for cid in chunks_of[g]]
        rows.append(
            base.question_row(
                qid,
                q["question"],
                q["answer"],
                q.get("aliases", []),
                gold,
                q.get("qtype", ""),
                metadata={"gold": q["gold"]},
            )
        )
    if n is not None:
        rows = rows[:n]
    return Benchmark(
        corpus=CorpusDataset(
            CorpusBatch(
                pl.DataFrame(doc_rows, schema=base.DOC_SCHEMA, orient="row"),
                pl.DataFrame(grant_rows, schema=base.GRANT_SCHEMA, orient="row"),
                pl.DataFrame(chunk_rows, schema=base.CHUNK_SCHEMA, orient="row"),
            )
        ),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows)))
        if questions is not None
        else None,
    )


def scan(root: Path) -> list[tuple[str, bytes]]:
    """Supported files under `root`, recursively, as `(relative posix path, bytes)`."""
    root = root.expanduser().resolve()
    return [
        (p.relative_to(root).as_posix(), p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and (p.suffix.lower() in SUFFIXES or p.name == QUESTIONS_FILE)
    ]


def spec(root: Path) -> Spec:
    """A registry entry for a folder: nothing to fetch, no fixture, parsed from disk."""
    root = root.expanduser().resolve()
    name = f"files:{root.name}"
    return Spec(
        name,
        "files",
        (),
        "local",
        lambda _paths, n: frames(scan(root), n),
        fixture=False,
    )
