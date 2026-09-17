"""A folder of local files as a corpus. PDF (text layer only, no OCR), Word (`.docx`), Markdown
and plain text become one document each, segmented by packing paragraphs to about `MAX_CHARS`;
a `questions.jsonl` beside them, with `question`, `answer`, optional `aliases` and `qtype`, and
`gold` as a list of relative file paths, becomes the questions with every segment of a gold
file as gold. Identity is portable: document ids are relative paths, `observed_at` is 0 and the
file's sha256 sits in document metadata, so the same folder hashes the same on any machine. The
corpus fingerprint is the file hashes plus the parser version, computed without parsing a PDF;
the corpus streams one file at a time, and the question source parses the files it names when
iterated. A folder loads through the registry by its path (`triplum bench run --dataset
~/papers`), and an object-store source only has to yield the same `(relative path, bytes)`.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterator
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.cache import content_key
from triplum.data.corpus import RECORD_VERSION, Document, Segment
from triplum.datasets.base import Entry
from triplum.datasets.files import sha256_file
from triplum.eval.inputs import GoldMappingError, Question
from triplum.settings import Settings
from triplum.utils.data import Dataset, IterableDataset

SUFFIXES = {".pdf", ".docx", ".md", ".markdown", ".txt", ".text"}
MAX_CHARS = 1500
QUESTIONS_FILE = "questions.jsonl"
SOURCE = "files"  # constant, so the corpus identity depends on content only, not the folder name
VERSION = 1  # bump when reading, segmentation or the record built here changes
_BLANK = re.compile(r"\n\s*\n")


def read_pdf(data: bytes) -> tuple[list[str], str | None]:
    """Text per page from the PDF's text layer; a page without one is an empty string."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    title = reader.metadata.title if reader.metadata else None
    return [page.extract_text() or "" for page in reader.pages], title or None


def read_docx(data: bytes) -> tuple[list[str], str | None]:
    from docx import Document as Docx

    doc = Docx(io.BytesIO(data))
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


def document(name: str, data: bytes) -> Document:
    """The document for one file: its text, its packed-paragraph segments, its metadata."""
    pages, title = read(name, data)
    text = "\n\n".join(pages)
    meta = {
        "title": title or Path(name).stem,
        "pages": len(pages),
        "empty_pages": sum(1 for p in pages if not p.strip()),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    segments = tuple(
        Segment(ordinal=i, start=s, end=e) for i, (s, e) in enumerate(chunk(text))
    ) or (Segment(ordinal=0, start=0, end=0),)
    return Document(id=name, source=SOURCE, text=text, segments=segments, metadata=meta)


def scan(root: Path) -> list[tuple[str, Path]]:
    """Supported files under `root`, recursively, as `(relative posix path, path)`."""
    root = root.expanduser().resolve()
    return [
        (p.relative_to(root).as_posix(), p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and (p.suffix.lower() in SUFFIXES or p.name == QUESTIONS_FILE)
    ]


class FolderCorpus(IterableDataset[Document]):
    """The supported files under a folder, one document each, read on iteration."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def files(self) -> list[tuple[str, Path]]:
        return [(name, p) for name, p in scan(self.root) if name != QUESTIONS_FILE]

    def __iter__(self) -> Iterator[Document]:
        for name, path in self.files():
            yield document(name, path.read_bytes())

    def fingerprint(self) -> str:
        return content_key(
            "folder",
            {
                "version": VERSION,
                "contract": RECORD_VERSION,
                "files": [(name, sha256_file(p)) for name, p in self.files()],
            },
        )


class FolderQuestions(Dataset[Question]):
    """`questions.jsonl` beside the files; a gold file expands to every segment of that file,
    so iterating parses the files a question names. The fingerprint needs no parse."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self._rows: list[dict] | None = None

    def rows(self) -> list[dict]:
        if self._rows is None:
            path = self.root / QUESTIONS_FILE
            lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            self._rows = [json.loads(line) for line in lines if line.strip()]
        return self._rows

    def __len__(self) -> int:
        return len(self.rows())

    def __getitem__(self, index: int) -> Question:
        q = self.rows()[index]
        qid = str(q.get("id", index))
        gold: list[int] = []
        for name in q["gold"]:
            path = self.root / name
            if not path.is_file() or Path(name).suffix.lower() not in SUFFIXES:
                raise GoldMappingError(f"{SOURCE}: question {qid} gold not in folder: {name}")
            gold += document(name, path.read_bytes()).chunk_ids()
        if not gold:
            raise GoldMappingError(f"{SOURCE}: question {qid} names no gold file")
        return Question(
            id=qid,
            question=q["question"],
            answer=q["answer"],
            aliases=tuple(q.get("aliases", [])),
            gold=tuple(gold),
            qtype=q.get("qtype", ""),
            metadata={"gold": q["gold"]},
        )

    def fingerprint(self) -> str:
        path = self.root / QUESTIONS_FILE
        return content_key(
            "folder-questions",
            {
                "version": VERSION,
                "contract": RECORD_VERSION,
                "sha256": sha256_file(path) if path.exists() else None,
            },
        )


def benchmark(root: Path, settings: Settings | None = None) -> Benchmark:
    root = root.expanduser().resolve()
    has_questions = (root / QUESTIONS_FILE).is_file()
    return Benchmark(
        name=f"{SOURCE}:{root.name}",
        corpus=FolderCorpus(root),
        qa=FolderQuestions(root) if has_questions else None,
    )


def entry(root: Path) -> Entry:
    """A catalog entry for a folder: nothing pinned, no fixture, read from disk."""
    root = root.expanduser().resolve()
    return Entry(
        name=f"{SOURCE}:{root.name}",
        family=SOURCE,
        licence="local",
        fixture=False,
        build=lambda s: benchmark(root, s),
    )
