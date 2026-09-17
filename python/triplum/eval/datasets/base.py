"""Shared machinery for every dataset: canonical frames, pinned-file fetching, fixtures.

A dataset is a `Spec`: its files (exact URL, path under the data root, sha256) and a parser that
turns the fetched files into the canonical frames. Fetch, verify, status and fixture handling are
generic; only the parser knows the source format.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import polars as pl

from triplum.data import schema as canonical

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures"
FIXTURE_N = 20
LARGE_BYTES = 300 << 20  # a dataset above this total download size only fetches when named

QUESTION_SCHEMA = {
    "id": pl.Utf8,
    "question": pl.Utf8,
    "answer": pl.Utf8,
    "aliases": pl.List(pl.Utf8),
    "gold_chunk_ids": pl.List(pl.Int64),
    "qtype": pl.Utf8,
    "answerable": pl.Boolean,
    "as_of": pl.Int64,
    "metadata": pl.Utf8,
}
# Documents, grants and chunks are the D2 tables owned by the Rust core; questions and triples
# are evaluation-only frames defined here.
DOC_SCHEMA = canonical.polars_schema(canonical.DOCUMENTS)
GRANT_SCHEMA = canonical.polars_schema(canonical.DOCUMENT_GRANTS)
CHUNK_SCHEMA = canonical.polars_schema(canonical.CHUNKS)
TRIPLE_SCHEMA = {
    "question_id": pl.Utf8,
    "document_id": pl.Utf8,
    "subject": pl.Utf8,
    "predicate": pl.Utf8,
    "object": pl.Utf8,
}
SCHEMAS = {
    "questions": QUESTION_SCHEMA,
    "documents": DOC_SCHEMA,
    "grants": GRANT_SCHEMA,
    "chunks": CHUNK_SCHEMA,
    "triples": TRIPLE_SCHEMA,
}


class HashMismatch(RuntimeError):
    pass


class GoldMappingError(ValueError):
    """A gold chunk is missing from the corpus or a corpus key is ambiguous. Silently dropping
    it would score an empty gold list as perfect recall, so the load fails instead."""


class Frames(NamedTuple):
    questions: pl.DataFrame
    documents: pl.DataFrame
    grants: pl.DataFrame
    chunks: pl.DataFrame
    triples: pl.DataFrame


@dataclass(frozen=True)
class File:
    url: str
    name: str  # path under the data root
    sha256: str
    bytes: int | None = None


@dataclass(frozen=True)
class Spec:
    name: str
    family: str
    files: tuple[File, ...]
    licence: str
    parse: Callable[[dict[str, Path], int | None], Frames]
    default: bool = False
    fixture: bool = True
    needs: str | None = None  # a runner capability this dataset needs and the runner lacks

    @property
    def bytes(self) -> int:
        return sum(f.bytes or 0 for f in self.files)

    @property
    def large(self) -> bool:
        return self.bytes > LARGE_BYTES


@dataclass(frozen=True)
class Dataset:
    name: str
    questions: pl.DataFrame
    documents: pl.DataFrame
    grants: pl.DataFrame
    chunks: pl.DataFrame
    triples: pl.DataFrame
    corpus_hash: str
    questions_hash: str


@dataclass(frozen=True)
class DatasetStatus:
    name: str
    state: str  # not downloaded | partial | verified | invalid
    paths: tuple[Path, ...]


MANIFEST = Path(__file__).with_name("manifest.json")


def manifest_files(dataset: str) -> tuple[File, ...]:
    """Pinned files for a dataset from `manifest.json` (url, sha256 and bytes as verified on
    2026-09-17), stored under `<dataset>/<upstream path>` in the data root."""
    entries = json.loads(MANIFEST.read_text())[dataset]
    return tuple(File(e["url"], f"{dataset}/{e['name']}", e["sha256"], e["bytes"]) for e in entries)


def data_root() -> Path:
    return Path(os.environ.get("TRIPLUM_DATA", Path.home() / ".cache" / "triplum" / "data"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def frames_hash(*frames: pl.DataFrame) -> str:
    """Identity of parsed content, so a parser change invalidates stores and runs even when the
    source bytes did not change. Row order is part of the identity."""
    h = hashlib.sha256()
    for frame in frames:
        h.update(json.dumps(frame.to_dicts(), sort_keys=True, ensure_ascii=False).encode())
        h.update(b"\0")
    return h.hexdigest()


def verify(p: Path, expected: str) -> str:
    got = sha256_file(p)
    if got != expected:
        raise HashMismatch(f"{p}: expected sha256 {expected}, got {got}")
    return got


def paths(spec: Spec, root: Path | None = None) -> dict[str, Path]:
    base = root or data_root()
    return {f.name: base / f.name for f in spec.files}


def status(spec: Spec, root: Path | None = None) -> DatasetStatus:
    """Inspect local files without downloading or creating directories."""
    local = paths(spec, root)
    present = [p.exists() for p in local.values()]
    if not any(present):
        state = "not downloaded"
    elif not all(present):
        state = "partial"
    else:
        state = (
            "verified"
            if all(sha256_file(local[f.name]) == f.sha256 for f in spec.files)
            else "invalid"
        )
    return DatasetStatus(spec.name, state, tuple(local.values()))


def fetch(spec: Spec, root: Path | None = None) -> dict[str, Path]:
    """Download missing files, then verify every file against its pinned hash."""
    local = paths(spec, root)
    for f in spec.files:
        p = local[f.name]
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".part")
            urllib.request.urlretrieve(f.url, tmp)
            os.replace(tmp, p)
        verify(p, f.sha256)
    return local


def dataset(name: str, frames: Frames) -> Dataset:
    return Dataset(
        name,
        *frames,
        corpus_hash=frames_hash(frames.documents, frames.grants, frames.chunks),
        questions_hash=frames_hash(frames.questions),
    )


def load_files(spec: Spec, local: dict[str, Path], n: int | None = None) -> Dataset:
    return dataset(spec.name, spec.parse(local, n))


def load(spec: Spec, n: int | None = None, root: Path | None = None) -> Dataset:
    return load_files(spec, fetch(spec, root), n)


# ---- helpers for parsers -------------------------------------------------------------------


def corpus_frames(
    source: str,
    passages: Iterable[tuple[str, str, str, int, dict | None]],
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Documents, public grants and one chunk per passage from `(doc_id, title, text, observed_at,
    metadata)` rows. Chunk text is `title\\ntext`; chunk ids are 1-based in passage order."""
    doc_rows, grant_rows, chunk_rows = [], [], []
    for cid, (doc_id, title, text, observed_at, meta) in enumerate(passages, start=1):
        body = f"{title}\n{text}" if title else text
        doc_rows.append((doc_id, source, None, observed_at, json.dumps(meta or {"title": title})))
        grant_rows.append((doc_id, "public", 0, None))
        chunk_rows.append((cid, doc_id, None, 0, 0, len(body), body))
    return (
        pl.DataFrame(doc_rows, schema=DOC_SCHEMA, orient="row"),
        pl.DataFrame(grant_rows, schema=GRANT_SCHEMA, orient="row"),
        pl.DataFrame(chunk_rows, schema=CHUNK_SCHEMA, orient="row"),
    )


def document_frames(
    source: str,
    documents: Iterable[tuple[str, list[str], int, dict | None]],
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Documents with several chunks each, from `(doc_id, chunk_texts, observed_at, metadata)`
    rows. Chunk ids are 1-based across all documents in order; spans are offsets into the chunk
    texts joined by a blank line."""
    doc_rows, grant_rows, chunk_rows = [], [], []
    for doc_id, texts, observed_at, meta in documents:
        doc_rows.append((doc_id, source, None, observed_at, json.dumps(meta or {})))
        grant_rows.append((doc_id, "public", 0, None))
        offset = 0
        for text in texts:
            cid = len(chunk_rows) + 1
            chunk_rows.append((cid, doc_id, None, 0, offset, offset + len(text), text))
            offset += len(text) + 2
    return (
        pl.DataFrame(doc_rows, schema=DOC_SCHEMA, orient="row"),
        pl.DataFrame(grant_rows, schema=GRANT_SCHEMA, orient="row"),
        pl.DataFrame(chunk_rows, schema=CHUNK_SCHEMA, orient="row"),
    )


class Corpus:
    """Accumulates distinct (title, text) passages in first-seen order and hands out chunk ids, for
    datasets whose corpus is the union of per-question inline paragraphs."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.key_to_chunk: dict[tuple[str, str], int] = {}
        self.passages: list[tuple[str, str, str, int, dict | None]] = []

    def add(self, title: str, text: str, observed_at: int = 0, meta: dict | None = None) -> int:
        key = (title, text)
        if key not in self.key_to_chunk:
            self.key_to_chunk[key] = len(self.passages) + 1
            self.passages.append(
                (f"{self.source}:{len(self.passages)}", title, text, observed_at, meta)
            )
        return self.key_to_chunk[key]

    def frames(self) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        return corpus_frames(self.source, self.passages)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def utc_us(text: str, fmt: str | None = None) -> int:
    """Microseconds since the epoch for an ISO-8601 string with offset, or a naive string in `fmt`
    read as UTC."""
    from datetime import UTC, datetime

    if fmt:
        dt = datetime.strptime(text, fmt).replace(tzinfo=UTC)
    else:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)


def question_row(
    qid: str,
    question: str,
    answer: str,
    aliases: list[str],
    gold_chunk_ids: list[int],
    qtype: str = "",
    *,
    answerable: bool = True,
    as_of: int | None = None,
    metadata: dict | None = None,
) -> tuple:
    uniq = [answer]
    for alias in aliases:
        if alias not in uniq:
            uniq.append(alias)
    return (
        qid,
        question,
        answer,
        uniq,
        sorted(set(gold_chunk_ids)),
        qtype,
        answerable,
        as_of,
        json.dumps(metadata or {}),
    )


def questions_frame(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=QUESTION_SCHEMA, orient="row")


def triples_frame(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=TRIPLE_SCHEMA, orient="row")


def empty(schema: dict) -> pl.DataFrame:
    return pl.DataFrame(schema=schema)


def resolve_gold(name: str, qid: str, keys: list, key_to_chunk: dict) -> list[int]:
    missing = [k for k in keys if k not in key_to_chunk]
    if missing or not keys:
        raise GoldMappingError(f"{name}: question {qid} gold not in corpus: {missing or 'none'}")
    return sorted({key_to_chunk[k] for k in keys})


# ---- fixtures ------------------------------------------------------------------------------


def fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def write_fixture(name: str, frames: Frames, path: Path | None = None) -> Path:
    path = path or fixture_path(name)
    payload = {key: getattr(frames, key).to_dicts() for key in SCHEMAS}
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def read_fixture(name: str, n: int | None = None, path: Path | None = None) -> Dataset:
    path = path or fixture_path(name)
    payload = json.loads(path.read_text())
    frames = Frames(
        **{key: pl.DataFrame(payload[key], schema=schema) for key, schema in SCHEMAS.items()}
    )
    if n is not None:
        frames = frames._replace(questions=frames.questions.head(n))
    return dataset(name, frames)


def subset(frames: Frames, n: int = FIXTURE_N, distractors: int = 40, seed: int = 0) -> Frames:
    """The first `n` questions, every chunk they need (gold, and candidate ids from `metadata`),
    and up to `distractors` further chunks chosen with a fixed seed; without questions, the first
    `distractors` chunks. Triples of the kept documents and questions come along."""
    import random

    questions = frames.questions.head(n)
    keep: set[int] = set()
    for q in questions.iter_rows(named=True):
        keep.update(q["gold_chunk_ids"])
        keep.update(json.loads(q["metadata"]).get("candidate_chunk_ids", []))
    rest = [c for c in frames.chunks["id"].to_list() if c not in keep]
    if questions.height == 0:
        keep.update(rest[:distractors])
    else:
        keep.update(random.Random(seed).sample(rest, min(distractors, len(rest))))
    chunks = frames.chunks.filter(pl.col("id").is_in(sorted(keep)))
    doc_ids = chunks["document_id"].unique()
    documents = frames.documents.filter(pl.col("id").is_in(doc_ids))
    grants = frames.grants.filter(pl.col("document_id").is_in(doc_ids))
    qids = questions["id"]
    triples = frames.triples.filter(
        pl.col("document_id").is_in(doc_ids) | pl.col("question_id").is_in(qids)
    )
    return Frames(questions, documents, grants, chunks, triples)
