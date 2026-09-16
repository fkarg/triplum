"""The HippoRAG / IRCoT 1000-question protocol for HotpotQA, MuSiQue and 2WikiMultiHopQA.

Source of truth: `reproduce/dataset/*.json` in github.com/OSU-NLP-Group/HippoRAG (MIT), content
under the upstream datasets' licences (HotpotQA CC BY-SA 4.0, MuSiQue CC BY 4.0, 2Wiki Apache-2.0).
Files are fetched once into the data root and verified by sha256 before use.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import polars as pl

RAW_BASE = "https://raw.githubusercontent.com/OSU-NLP-Group/HippoRAG/main/reproduce/dataset/"

FILES = {
    "hotpotqa": ("hotpotqa.json", "hotpotqa_corpus.json"),
    "musique": ("musique.json", "musique_corpus.json"),
    "twowiki": ("2wikimultihopqa.json", "2wikimultihopqa_corpus.json"),
}

# sha256 of the files as fetched on 2026-09-16 (HippoRAG 2 generation; HotpotQA corpus = 9,811).
HASHES = {
    "hotpotqa.json": "3ad9c0bcbf93f41d7004ca6007049c904d2605046b314a2f7ecfb379c64cba6d",
    "hotpotqa_corpus.json": "9333647b922382776cd2cb02893b390d77984df85a91bfa8be411284978aca7d",
    "musique.json": "98ed4e21d3076532f6388d42320fb809599c63a0d8dffca8ece5e41922be6b46",
    "musique_corpus.json": "73157a03ce3f0b1a5673dd5dc12bb970c24976dbffc688af9eecdd758c97ffcb",
    "2wikimultihopqa.json": "895cba294064df0c3302c76847b1fc08d99b5619f7663dfaa3b65cd780f1cac4",
    "2wikimultihopqa_corpus.json": "9d6e352952aafb18dab22bf8195039461321a44a949df902ae83bce134ad238a",
}

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures"

QUESTION_SCHEMA = {
    "id": pl.Utf8,
    "question": pl.Utf8,
    "answer": pl.Utf8,
    "aliases": pl.List(pl.Utf8),
    "gold_chunk_ids": pl.List(pl.Int64),
    "qtype": pl.Utf8,
}
DOC_SCHEMA = {
    "id": pl.Utf8,
    "source": pl.Utf8,
    "uri": pl.Utf8,
    "observed_at": pl.Int64,
    "metadata": pl.Utf8,
}
GRANT_SCHEMA = {
    "document_id": pl.Utf8,
    "principal": pl.Utf8,
    "granted_at": pl.Int64,
    "revoked_at": pl.Int64,
}
CHUNK_SCHEMA = {
    "id": pl.Int64,
    "document_id": pl.Utf8,
    "parent_id": pl.Int64,
    "level": pl.Int64,
    "span_start": pl.Int64,
    "span_end": pl.Int64,
    "text": pl.Utf8,
}


class HashMismatch(RuntimeError):
    pass


class GoldMappingError(ValueError):
    """A gold passage is missing from the corpus or a corpus key is ambiguous. Silently dropping
    it would score an empty gold list as perfect recall, so the load fails instead."""


@dataclass(frozen=True)
class Dataset:
    name: str
    questions: pl.DataFrame  # id, question, answer, aliases, gold_chunk_ids, qtype
    documents: pl.DataFrame
    grants: pl.DataFrame
    chunks: pl.DataFrame
    corpus_hash: str
    questions_hash: str


def data_root() -> Path:
    return Path(os.environ.get("TRIPLUM_DATA", Path.home() / ".cache" / "triplum" / "data"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(p: Path, expected: str) -> str:
    got = sha256_file(p)
    if got != expected:
        raise HashMismatch(f"{p}: expected sha256 {expected}, got {got}")
    return got


def fetch(name: str, root: Path | None = None) -> tuple[Path, Path]:
    root = (root or data_root()) / "hipporag"
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for fname in FILES[name]:
        p = root / fname
        if not p.exists():
            tmp = p.with_suffix(".part")
            urllib.request.urlretrieve(RAW_BASE + fname, tmp)
            os.replace(tmp, p)
        verify(p, HASHES[fname])
        out.append(p)
    return out[0], out[1]


def gold_key(name: str, title: str, text: str) -> tuple:
    """Titles are unique in the HotpotQA and 2Wiki corpora; MuSiQue needs (title, text)."""
    return (title,) if name in ("hotpotqa", "twowiki") else (title, text)


def _parse(name: str, questions: list[dict], corpus: list[dict], n: int | None):
    if n is not None:
        questions = questions[:n]
    key_to_chunk: dict[tuple, int] = {}
    doc_rows, grant_rows, chunk_rows = [], [], []
    for i, rec in enumerate(corpus):
        cid = i + 1
        doc_id = f"{name}:{i}"
        key = gold_key(name, rec["title"], rec["text"])
        if key in key_to_chunk:
            raise GoldMappingError(f"{name}: duplicate corpus key {key[0]!r} at passage {i}")
        key_to_chunk[key] = cid
        text = f"{rec['title']}\n{rec['text']}"
        doc_rows.append((doc_id, f"hipporag/{name}", None, 0, json.dumps({"title": rec["title"]})))
        grant_rows.append((doc_id, "public", 0, None))
        chunk_rows.append((cid, doc_id, None, 0, 0, len(text), text))
    q_rows = []
    for q in questions:
        if name == "musique":
            qid, answer = q["id"], q["answer"]
            aliases = [answer, *[a for a in q.get("answer_aliases", []) if a != answer]]
            gold = [(p["title"], p["paragraph_text"]) for p in q["paragraphs"] if p["is_supporting"]]
            qtype = q["id"].split("__")[0]
        else:
            qid, answer = q["_id"], q["answer"]
            aliases = [answer]
            gold = sorted({(t,) for t, _ in q["supporting_facts"]})
            qtype = q.get("type", "")
        missing = [g for g in gold if g not in key_to_chunk]
        if missing or not gold:
            raise GoldMappingError(f"{name}: question {qid} gold not in corpus: {missing or 'none'}")
        gold_ids = sorted({key_to_chunk[g] for g in gold})
        q_rows.append((qid, q["question"], answer, aliases, gold_ids, qtype))
    return (
        pl.DataFrame(q_rows, schema=QUESTION_SCHEMA, orient="row"),
        pl.DataFrame(doc_rows, schema=DOC_SCHEMA, orient="row"),
        pl.DataFrame(grant_rows, schema=GRANT_SCHEMA, orient="row"),
        pl.DataFrame(chunk_rows, schema=CHUNK_SCHEMA, orient="row"),
    )


def load_files(name: str, questions_path: Path, corpus_path: Path, n: int | None = None) -> Dataset:
    questions = json.loads(Path(questions_path).read_text())
    corpus = json.loads(Path(corpus_path).read_text())
    q, d, g, c = _parse(name, questions, corpus, n)
    return Dataset(
        name, q, d, g, c, sha256_file(Path(corpus_path)), sha256_file(Path(questions_path))
    )


def load(name: str, n: int | None = None, root: Path | None = None) -> Dataset:
    qp, cp = fetch(name, root)
    return load_files(name, qp, cp, n)


def load_fixture(name: str, n: int | None = None) -> Dataset:
    return load_files(
        name, FIXTURE_DIR / f"{name}_questions.json", FIXTURE_DIR / f"{name}_corpus.json", n
    )
