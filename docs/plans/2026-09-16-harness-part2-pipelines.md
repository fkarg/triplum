# Harness part 2: datasets, baselines, metrics, run store, CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (code is written in-session per repository policy; subagents review only). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `triplum bench run --pipeline dense --dataset musique --n 20` produces a run in the run store with EM, F1, Contain-Acc, Judge-Acc, R@2, R@5, tokens, cost and latency, for the five non-graph baselines, on the HippoRAG 1000-question protocol data, with the embedder as a swappable spec.

**Architecture:** Datasets are the HippoRAG `reproduce/dataset` files (the protocol's definition), fetched once, hash-verified, and parsed into the canonical frames from part 1 with one passage per document and per chunk. Retrieval stages are plain functions returning a `(question_id, chunk_id, rank, score)` frame; the reader is one prompt through the `LLM` protocol; metrics are pure functions; every call and stage writes a priced event to a SQLite run store; the runner composes them from a frozen config whose hash is the run identity.

**Tech Stack:** part 1 modules, polars, argparse, sqlite3, urllib for downloads.

Spec: `docs/specs/2026-09-16-harness-and-baselines.md`. Deviation from the spec, recorded here: the corpora are taken from the HippoRAG release files directly (MIT-licensed repo; content under the upstream datasets' licences) and their hashes are pinned. Rebuilding them from the upstream HotpotQA/MuSiQue/2Wiki releases is a verification task deferred to sub-project 2a.

---

## File structure

```
python/triplum/eval/__init__.py
python/triplum/eval/datasets/__init__.py
python/triplum/eval/datasets/hipporag.py   fetch, verify, parse the HippoRAG protocol files -> Dataset
python/triplum/eval/metrics.py             normalize_answer, em, f1, contain, recall_at_k
python/triplum/eval/judge.py               binary correctness judge through LLM
python/triplum/retrieve/__init__.py
python/triplum/retrieve/stages.py          dense, bm25, hybrid (RRF + rerank), oracle, none
python/triplum/generate/__init__.py
python/triplum/generate/reader.py          one prompt, one call, returns answer + usage
python/triplum/bench/__init__.py
python/triplum/bench/config.py             frozen dataclasses: EmbedderConfig, LLMConfig, PipelineConfig, RunConfig; hash()
python/triplum/bench/factories.py          config -> Embedder / LLM / Reranker (with cache wrappers)
python/triplum/bench/runstore.py           SQLite run store: runs, run_questions, events, prices, run_artifacts; Recorder
python/triplum/bench/index.py              ensure documents, chunks, embeddings are in the store (cached)
python/triplum/bench/runner.py             run_benchmark(RunConfig) -> run_id
python/triplum/bench/report.py             summary frames
python/triplum/bench/cli.py                triplum data fetch | bench run | bench report
scripts/make_fixture.py                    build tests/fixtures/<ds>.json from the fetched files
tests/fixtures/{hotpotqa,musique,twowiki}.json + ATTRIBUTION.md
tests/test_datasets.py, tests/test_metrics.py, tests/test_stages.py, tests/test_runstore.py,
tests/test_config.py, tests/integration/test_pipelines_fixture.py
notebooks/runs.py                          marimo notebook slicing the run store
```

---

### Task 1: Dataset loader for the HippoRAG protocol files

**Files:**
- Create: `python/triplum/eval/__init__.py`, `python/triplum/eval/datasets/__init__.py`, `python/triplum/eval/datasets/hipporag.py`, `scripts/make_fixture.py`, `tests/fixtures/ATTRIBUTION.md`
- Test: `tests/test_datasets.py`

- [ ] **Step 1: Write the failing test**

`tests/test_datasets.py`:
```python
import json

import pytest

from triplum.eval.datasets import hipporag as hr


def _mini_hotpot(tmp_path):
    questions = [
        {"_id": "q1", "question": "Who?", "answer": "Bob", "type": "bridge", "level": "hard",
         "supporting_facts": [["A", 0], ["B", 0]],
         "context": [["A", ["Alice met Bob."]], ["B", ["Bob is tall."]], ["C", ["Noise."]]]},
        {"_id": "q2", "question": "What?", "answer": "yes", "type": "comparison", "level": "hard",
         "supporting_facts": [["C", 0]],
         "context": [["C", ["Noise."]], ["D", ["Other."]]]},
    ]
    corpus = [{"idx": 0, "title": "A", "text": "Alice met Bob."}, {"idx": 1, "title": "B", "text": "Bob is tall."},
              {"idx": 2, "title": "C", "text": "Noise."}, {"idx": 3, "title": "D", "text": "Other."}]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text(json.dumps(questions))
    cp.write_text(json.dumps(corpus))
    return qp, cp


def test_parse_hotpot_style(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    ds = hr.load_files("hotpotqa", qp, cp)
    assert ds.name == "hotpotqa" and ds.chunks.height == 4 and ds.documents.height == 4
    q = ds.questions.filter(ds.questions["id"] == "q1").row(0, named=True)
    assert q["answer"] == "Bob" and sorted(q["gold_chunk_ids"]) == [1, 2] and q["aliases"] == ["Bob"]
    assert ds.chunks.filter(ds.chunks["id"] == 1)["text"][0] == "A\nAlice met Bob."
    assert ds.grants["principal"].unique().to_list() == ["public"]
    assert len(ds.corpus_hash) == 64 and len(ds.questions_hash) == 64


def test_parse_musique_style(tmp_path):
    questions = [{"id": "m1", "question": "Q", "answer": "X", "answer_aliases": ["Y"], "answerable": True,
                  "paragraphs": [{"idx": 0, "title": "T", "paragraph_text": "one", "is_supporting": True},
                                 {"idx": 1, "title": "T", "paragraph_text": "two", "is_supporting": True},
                                 {"idx": 2, "title": "U", "paragraph_text": "three", "is_supporting": False}],
                  "question_decomposition": []}]
    corpus = [{"title": "T", "text": "one"}, {"title": "T", "text": "two"}, {"title": "U", "text": "three"}]
    qp, cp = tmp_path / "q.json", tmp_path / "c.json"
    qp.write_text(json.dumps(questions))
    cp.write_text(json.dumps(corpus))
    ds = hr.load_files("musique", qp, cp)
    q = ds.questions.row(0, named=True)
    assert sorted(q["gold_chunk_ids"]) == [1, 2] and q["aliases"] == ["X", "Y"]


def test_subset_by_n_keeps_order(tmp_path):
    qp, cp = _mini_hotpot(tmp_path)
    ds = hr.load_files("hotpotqa", qp, cp, n=1)
    assert ds.questions["id"].to_list() == ["q1"]


def test_verify_hash_mismatch_raises(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[]")
    with pytest.raises(hr.HashMismatch):
        hr.verify(p, "0" * 64)


def test_fixture_files_load():
    for name in ("hotpotqa", "musique", "twowiki"):
        ds = hr.load_fixture(name)
        assert ds.questions.height == 20 and ds.chunks.height > 20
        assert all(len(g) > 0 for g in ds.questions["gold_chunk_ids"].to_list())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_datasets.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.eval`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/eval/__init__.py`, `python/triplum/eval/datasets/__init__.py`: empty.

`python/triplum/eval/datasets/hipporag.py`:
```python
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


class HashMismatch(RuntimeError):
    pass


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


def _gold_key(name: str, title: str, text: str) -> tuple:
    return (title,) if name in ("hotpotqa", "twowiki") else (title, text)


def _parse(name: str, questions: list[dict], corpus: list[dict], n: int | None) -> tuple[pl.DataFrame, ...]:
    if n is not None:
        questions = questions[:n]
    key_to_chunk: dict[tuple, int] = {}
    doc_rows, grant_rows, chunk_rows = [], [], []
    for i, rec in enumerate(corpus):
        cid = i + 1
        doc_id = f"{name}:{i}"
        key_to_chunk.setdefault(_gold_key(name, rec["title"], rec["text"]), cid)
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
        gold_ids = sorted({key_to_chunk[g] for g in gold if g in key_to_chunk})
        q_rows.append((qid, q["question"], answer, aliases, gold_ids, qtype))
    questions_df = pl.DataFrame(
        q_rows,
        schema={"id": pl.Utf8, "question": pl.Utf8, "answer": pl.Utf8, "aliases": pl.List(pl.Utf8),
                "gold_chunk_ids": pl.List(pl.Int64), "qtype": pl.Utf8},
        orient="row",
    )
    documents = pl.DataFrame(doc_rows, schema={"id": pl.Utf8, "source": pl.Utf8, "uri": pl.Utf8, "observed_at": pl.Int64, "metadata": pl.Utf8}, orient="row")
    grants = pl.DataFrame(grant_rows, schema={"document_id": pl.Utf8, "principal": pl.Utf8, "granted_at": pl.Int64, "revoked_at": pl.Int64}, orient="row")
    chunks = pl.DataFrame(chunk_rows, schema={"id": pl.Int64, "document_id": pl.Utf8, "parent_id": pl.Int64, "level": pl.Int64, "span_start": pl.Int64, "span_end": pl.Int64, "text": pl.Utf8}, orient="row")
    return questions_df, documents, grants, chunks


def load_files(name: str, questions_path: Path, corpus_path: Path, n: int | None = None) -> Dataset:
    questions = json.loads(Path(questions_path).read_text())
    corpus = json.loads(Path(corpus_path).read_text())
    q, d, g, c = _parse(name, questions, corpus, n)
    return Dataset(name, q, d, g, c, sha256_file(Path(corpus_path)), sha256_file(Path(questions_path)))


def load(name: str, n: int | None = None, root: Path | None = None) -> Dataset:
    qp, cp = fetch(name, root)
    return load_files(name, qp, cp, n)


def load_fixture(name: str, n: int | None = None) -> Dataset:
    return load_files(name, FIXTURE_DIR / f"{name}_questions.json", FIXTURE_DIR / f"{name}_corpus.json", n)
```

`scripts/make_fixture.py`:
```python
"""Build the 20-question smoke fixtures from the fetched HippoRAG files.

Keeps the first 20 questions and every corpus passage that appears in their candidate contexts,
so retrieval on the fixture has the same gold/distractor structure as the full corpus.
Run: uv run python scripts/make_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

from triplum.eval.datasets import hipporag as hr

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
N = 20


def candidate_keys(name: str, q: dict) -> set[tuple]:
    if name == "musique":
        return {(p["title"], p["paragraph_text"]) for p in q["paragraphs"]}
    return {(t,) for t, _ in q["context"]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in hr.FILES:
        qp, cp = hr.fetch(name)
        questions = json.loads(qp.read_text())[:N]
        corpus = json.loads(cp.read_text())
        keep = set().union(*(candidate_keys(name, q) for q in questions))
        sub = [r for r in corpus if hr._gold_key(name, r["title"], r["text"]) in keep]
        (OUT / f"{name}_questions.json").write_text(json.dumps(questions, ensure_ascii=False))
        (OUT / f"{name}_corpus.json").write_text(json.dumps(sub, ensure_ascii=False))
        print(name, len(questions), "questions", len(sub), "passages")


if __name__ == "__main__":
    main()
```

`tests/fixtures/ATTRIBUTION.md`:
```markdown
# Fixture attribution

The `*_questions.json` and `*_corpus.json` files are 20-question subsets of the evaluation
artefacts released in `reproduce/dataset/` of https://github.com/OSU-NLP-Group/HippoRAG (MIT),
which derive from:

- HotpotQA (Yang et al., 2018), CC BY-SA 4.0, https://hotpotqa.github.io/
- MuSiQue (Trivedi et al., 2022), CC BY 4.0, https://github.com/StonyBrookNLP/musique
- 2WikiMultiHopQA (Ho et al., 2020), Apache-2.0, https://github.com/Alab-NII/2wikimultihop

Generated by `scripts/make_fixture.py` from files with the sha256 values pinned in
`python/triplum/eval/datasets/hipporag.py`.
```

- [ ] **Step 4: Fetch data, build fixtures, run tests**

Run: `uv run python scripts/make_fixture.py`
Expected: three lines like `hotpotqa 20 questions 199 passages` (about 200 passages each; the exact count is deterministic).

Run: `uv run pytest tests/test_datasets.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/eval scripts/make_fixture.py tests/fixtures tests/test_datasets.py
git commit -m "Add HippoRAG protocol dataset loader with pinned hashes and 20-question fixtures"
```

---

### Task 2: Metrics

**Files:**
- Create: `python/triplum/eval/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

`tests/test_metrics.py`:
```python
from triplum.eval import metrics as m


def test_normalize_answer_matches_hotpot_rules():
    assert m.normalize_answer("The  Quick, brown fox!") == "quick brown fox"
    assert m.normalize_answer("an apple a day") == "apple day"


def test_em_and_f1_over_aliases():
    assert m.exact_match("Barack Obama", ["Obama", "Barack Obama"]) == 1.0
    assert m.exact_match("Barack", ["Obama"]) == 0.0
    assert m.f1("Barack Obama", ["Obama"]) == 2 * (0.5 * 1.0) / (0.5 + 1.0)
    assert m.f1("", ["x"]) == 0.0


def test_no_yes_no_zeroing():
    # HotpotQA's script zeroes F1 when one side is yes/no and the other is not; we do not.
    assert m.f1("yes indeed", ["yes"]) > 0.0


def test_contain():
    assert m.contain("The answer is Paris, France.", ["Paris"]) == 1.0
    assert m.contain("Rome", ["Paris"]) == 0.0


def test_recall_at_k():
    assert m.recall_at_k([1, 2], [5, 1, 3, 2], 2) == 0.5
    assert m.recall_at_k([1, 2], [5, 1, 3, 2], 5) == 1.0
    assert m.recall_at_k([], [1], 5) == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/eval/metrics.py`:
```python
"""QA and retrieval metrics. EM/F1 follow HotpotQA's normalisation, aggregated as max over gold
aliases (HippoRAG convention), without the yes/no zeroing rule. See benchmarks-multihop-qa.md §2."""

from __future__ import annotations

import re
import string
from collections import Counter


def normalize_answer(s: str) -> str:
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def _f1_single(pred: str, gold: str) -> float:
    p, g = normalize_answer(pred).split(), normalize_answer(gold).split()
    common = Counter(p) & Counter(g)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    precision, recall = num_same / len(p), num_same / len(g)
    return 2 * precision * recall / (precision + recall)


def exact_match(pred: str, golds: list[str]) -> float:
    n = normalize_answer(pred)
    return float(any(n == normalize_answer(g) for g in golds))


def f1(pred: str, golds: list[str]) -> float:
    return max((_f1_single(pred, g) for g in golds), default=0.0)


def contain(pred: str, golds: list[str]) -> float:
    n = normalize_answer(pred)
    return float(any(normalize_answer(g) in n for g in golds if normalize_answer(g)))


def recall_at_k(gold_ids: list[int], retrieved_ids: list[int], k: int) -> float:
    if not gold_ids:
        return 1.0
    top = set(retrieved_ids[:k])
    return sum(1 for g in gold_ids if g in top) / len(gold_ids)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/eval/metrics.py tests/test_metrics.py
git commit -m "Add QA and retrieval metrics (HotpotQA normalisation, max over aliases)"
```

---

### Task 3: Retrieval stages and reader

**Files:**
- Create: `python/triplum/retrieve/__init__.py`, `python/triplum/retrieve/stages.py`, `python/triplum/generate/__init__.py`, `python/triplum/generate/reader.py`, `python/triplum/eval/judge.py`
- Test: `tests/test_stages.py`

- [ ] **Step 1: Write the failing test**

`tests/test_stages.py`:
```python
import polars as pl

from triplum.data.viewer import Viewer
from triplum.embed.fake import FakeEmbedder
from triplum.eval.datasets import hipporag as hr
from triplum.eval.judge import judge_correct
from triplum.generate.reader import read
from triplum.llm.fake import FakeLLM
from triplum.rerank.fake import FakeReranker
from triplum.retrieve import stages
from triplum.store.sqlite.store import SqliteStore

PUBLIC = Viewer.of("public")


def _store(tmp_db, ds, embedder):
    s = SqliteStore(tmp_db)
    s.put_documents(ds.documents, ds.grants)
    s.put_chunks(ds.chunks)
    s.put_embeddings(embedder.spec, ds.chunks["id"].to_list(), embedder.embed_passages(ds.chunks["text"].to_list()))
    return s


def test_stages_return_ranked_frames(tmp_db):
    ds = hr.load_fixture("hotpotqa", n=3)
    e = FakeEmbedder(dims=64)
    s = _store(tmp_db, ds, e)
    for out in (
        stages.dense(ds.questions, s, e, k=5, viewer=PUBLIC),
        stages.bm25(ds.questions, s, k=5, viewer=PUBLIC),
        stages.hybrid(ds.questions, s, e, FakeReranker(), k=5, candidates=10, viewer=PUBLIC),
        stages.oracle(ds.questions, k=5),
    ):
        assert out.columns == ["question_id", "chunk_id", "rank", "score"]
        assert out.group_by("question_id").len()["len"].max() <= 5
        assert out.filter(pl.col("rank") == 1).height == 3
    assert stages.none(ds.questions).height == 0


def test_oracle_contains_all_gold(tmp_db):
    ds = hr.load_fixture("musique", n=5)
    out = stages.oracle(ds.questions, k=5)
    for q in ds.questions.iter_rows(named=True):
        got = out.filter(pl.col("question_id") == q["id"])["chunk_id"].to_list()
        assert set(q["gold_chunk_ids"]) <= set(got)


def test_reader_uses_visible_chunks_only(tmp_db):
    ds = hr.load_fixture("twowiki", n=2)
    e = FakeEmbedder(dims=64)
    s = _store(tmp_db, ds, e)
    seen = []

    def responder(msgs, schema):
        seen.append(msgs[-1].content)
        return '{"answer": "x"}'

    retrieved = stages.oracle(ds.questions, k=5)
    out = read(ds.questions, retrieved, s, FakeLLM(responder=responder), viewer=Viewer.of("nobody"))
    assert out.columns == ["question_id", "answer", "input_tokens", "output_tokens", "cached", "latency_s", "n_passages"]
    assert out["n_passages"].to_list() == [0, 0]
    assert all("Passage" not in p for p in seen)


def test_judge_parses_bool():
    llm = FakeLLM(responder=lambda m, s: '{"correct": true}')
    assert judge_correct(llm, "q", ["gold"], "pred") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stages.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.retrieve`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/retrieve/__init__.py`, `python/triplum/generate/__init__.py`: empty.

`python/triplum/retrieve/stages.py`:
```python
"""Retrieval stages. Each returns a frame (question_id, chunk_id, rank, score), rank starting at 1.
Visibility is the store's job: every call passes the Viewer through."""

from __future__ import annotations

import numpy as np
import polars as pl

from triplum.data.viewer import Viewer
from triplum.embed.protocol import Embedder
from triplum.rerank.protocol import Reranker
from triplum.store.protocol import Store

SCHEMA = {"question_id": pl.Utf8, "chunk_id": pl.Int64, "rank": pl.Int64, "score": pl.Float64}


def _frame(rows: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=SCHEMA, orient="row")


def _ranked(qid: str, ids: list[int], scores: list[float], k: int) -> list[tuple]:
    return [(qid, int(c), r + 1, float(s)) for r, (c, s) in enumerate(zip(ids[:k], scores[:k]))]


def none(questions: pl.DataFrame) -> pl.DataFrame:
    return _frame([])


def oracle(questions: pl.DataFrame, k: int) -> pl.DataFrame:
    rows = []
    for q in questions.iter_rows(named=True):
        ids = q["gold_chunk_ids"][:k]
        rows += _ranked(q["id"], ids, [1.0] * len(ids), k)
    return _frame(rows)


def dense(questions: pl.DataFrame, store: Store, embedder: Embedder, k: int, viewer: Viewer) -> pl.DataFrame:
    qvecs = embedder.embed_queries(questions["question"].to_list())
    rows = []
    for q, v in zip(questions.iter_rows(named=True), qvecs):
        hits = store.vector_search(embedder.spec, v, k, viewer)
        rows += _ranked(q["id"], hits["id"].to_list(), hits["score"].to_list(), k)
    return _frame(rows)


def bm25(questions: pl.DataFrame, store: Store, k: int, viewer: Viewer) -> pl.DataFrame:
    rows = []
    for q in questions.iter_rows(named=True):
        hits = store.bm25(q["question"], k, viewer)
        rows += _ranked(q["id"], hits["id"].to_list(), hits["score"].to_list(), k)
    return _frame(rows)


def rrf(rankings: list[list[int]], k_const: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion; returns (id, score) sorted by score desc."""
    acc: dict[int, float] = {}
    for ranking in rankings:
        for r, cid in enumerate(ranking):
            acc[cid] = acc.get(cid, 0.0) + 1.0 / (k_const + r + 1)
    return sorted(acc.items(), key=lambda t: -t[1])


def hybrid(
    questions: pl.DataFrame, store: Store, embedder: Embedder, reranker: Reranker,
    k: int, candidates: int, viewer: Viewer,
) -> pl.DataFrame:
    """Dense and BM25 candidates fused by RRF, top `candidates` reranked, top k returned."""
    qvecs = embedder.embed_queries(questions["question"].to_list())
    rows = []
    for q, v in zip(questions.iter_rows(named=True), qvecs):
        d = store.vector_search(embedder.spec, v, candidates, viewer)["id"].to_list()
        b = store.bm25(q["question"], candidates, viewer)["id"].to_list()
        fused = [cid for cid, _ in rrf([d, b])][:candidates]
        if not fused:
            continue
        chunks = store.get_chunks(fused, viewer)
        text_by_id = dict(zip(chunks["id"].to_list(), chunks["text"].to_list()))
        ids = [c for c in fused if c in text_by_id]
        scores = reranker.score(q["question"], [text_by_id[c] for c in ids])
        order = np.argsort(-scores)
        rows += _ranked(q["id"], [ids[i] for i in order], [float(scores[i]) for i in order], k)
    return _frame(rows)
```

`python/triplum/generate/reader.py`:
```python
"""One reader prompt for every pipeline. Passages come from the store through the Viewer, so a
retrieved id the viewer may not see is silently dropped before the prompt is built."""

from __future__ import annotations

import time

import polars as pl

from triplum.data.viewer import Viewer
from triplum.llm.protocol import DEFAULT_PARAMS, LLM, GenParams, Message
from triplum.store.protocol import Store

PROMPT_VERSION = "reader-v1"
SYSTEM = (
    "You answer questions using the given passages. Reply with the shortest possible answer: a "
    "name, date, number, or yes/no. Do not explain."
)
ANSWER_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

OUT_SCHEMA = {
    "question_id": pl.Utf8, "answer": pl.Utf8, "input_tokens": pl.Int64, "output_tokens": pl.Int64,
    "cached": pl.Boolean, "latency_s": pl.Float64, "n_passages": pl.Int64,
}


def build_messages(question: str, passages: list[str]) -> list[Message]:
    if passages:
        ctx = "\n\n".join(f"Passage {i + 1}:\n{p}" for i, p in enumerate(passages))
        user = f"{ctx}\n\nQuestion: {question}"
    else:
        user = f"Question: {question}"
    return [Message("system", SYSTEM), Message("user", user)]


def read(
    questions: pl.DataFrame, retrieved: pl.DataFrame, store: Store, llm: LLM,
    viewer: Viewer, params: GenParams = DEFAULT_PARAMS,
) -> pl.DataFrame:
    rows = []
    for q in questions.iter_rows(named=True):
        ids = retrieved.filter(pl.col("question_id") == q["id"]).sort("rank")["chunk_id"].to_list()
        passages: list[str] = []
        if ids:
            chunks = store.get_chunks(ids, viewer)
            by_id = dict(zip(chunks["id"].to_list(), chunks["text"].to_list()))
            passages = [by_id[c] for c in ids if c in by_id]
        t0 = time.perf_counter()
        c = llm.complete(build_messages(q["question"], passages), schema=ANSWER_SCHEMA, params=params)
        answer = c.parsed.get("answer", "") if isinstance(c.parsed, dict) else c.text
        rows.append((q["id"], str(answer), c.usage.input_tokens, c.usage.output_tokens, c.cached,
                     time.perf_counter() - t0, len(passages)))
    return pl.DataFrame(rows, schema=OUT_SCHEMA, orient="row")
```

`python/triplum/eval/judge.py`:
```python
"""Binary correctness judge. The judge model must come from a different family than the reader;
the runner records both ids."""

from __future__ import annotations

from triplum.llm.protocol import LLM, Message

PROMPT_VERSION = "judge-v1"
SCHEMA = {"type": "object", "properties": {"correct": {"type": "boolean"}}, "required": ["correct"]}


def judge_correct(llm: LLM, question: str, golds: list[str], answer: str) -> bool:
    msgs = [
        Message("system", "You grade short answers. Given the question, the gold answer(s) and a candidate, "
                          "say whether the candidate is correct (same meaning; extra words are fine)."),
        Message("user", f"Question: {question}\nGold: {' | '.join(golds)}\nCandidate: {answer}"),
    ]
    c = llm.complete(msgs, schema=SCHEMA)
    return bool(isinstance(c.parsed, dict) and c.parsed.get("correct") is True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stages.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/retrieve python/triplum/generate python/triplum/eval/judge.py tests/test_stages.py
git commit -m "Add retrieval stages (dense, bm25, hybrid RRF+rerank, oracle, none), reader and judge"
```

---

### Task 4: Config and factories

**Files:**
- Create: `python/triplum/bench/__init__.py`, `python/triplum/bench/config.py`, `python/triplum/bench/factories.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from triplum.bench import factories
from triplum.bench.config import EmbedderConfig, LLMConfig, PipelineConfig, RunConfig
from triplum.embed.fake import FakeEmbedder
from triplum.llm.cached import CachedLLM


def test_config_hash_is_stable_and_sensitive():
    a = PipelineConfig(name="dense", embedder=EmbedderConfig(kind="fake", dims=32), reader=LLMConfig(kind="fake"))
    b = PipelineConfig(name="dense", embedder=EmbedderConfig(kind="fake", dims=32), reader=LLMConfig(kind="fake"))
    c = PipelineConfig(name="dense", top_k=3, embedder=EmbedderConfig(kind="fake", dims=32), reader=LLMConfig(kind="fake"))
    assert a.hash() == b.hash() != c.hash()


def test_run_config_roundtrips_json():
    rc = RunConfig(dataset="musique", n=20, fixture=True,
                   pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake")))
    assert RunConfig.from_json(rc.to_json()) == rc


def test_factories_build_fakes(tmp_path):
    e = factories.make_embedder(EmbedderConfig(kind="fake", dims=16), cache_root=tmp_path)
    assert isinstance(e.inner if hasattr(e, "inner") else e, FakeEmbedder) and e.spec.dims == 16
    llm = factories.make_llm(LLMConfig(kind="fake"), cache_root=tmp_path)
    assert isinstance(llm, CachedLLM)
    assert factories.make_reranker(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.bench`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/bench/__init__.py`: empty.

`python/triplum/bench/config.py`:
```python
"""Frozen configs. `hash()` of a PipelineConfig is part of the run identity (design D8)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from triplum.cache import content_key


@dataclass(frozen=True)
class EmbedderConfig:
    kind: str  # fake | openai | st | fastembed
    model: str = "fake"
    dims: int = 64
    revision: str = ""
    query_prefix: str = ""
    passage_prefix: str = ""
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"


@dataclass(frozen=True)
class LLMConfig:
    kind: str  # fake | openai | cli
    model: str = "fake-1"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 256
    argv: tuple[str, ...] = ()
    json_field: str | None = None


@dataclass(frozen=True)
class RerankerConfig:
    kind: str  # fake | cross_encoder
    model: str = "fake"


@dataclass(frozen=True)
class PipelineConfig:
    name: str  # closed_book | bm25 | dense | hybrid | oracle
    reader: LLMConfig
    top_k: int = 5
    candidates: int = 20
    embedder: EmbedderConfig | None = None
    reranker: RerankerConfig | None = None
    prompt_version: str = "reader-v1"

    def hash(self) -> str:
        return content_key("pipeline", asdict(self))[:16]


@dataclass(frozen=True)
class RunConfig:
    dataset: str
    pipeline: PipelineConfig
    n: int | None = None
    fixture: bool = False
    judge: LLMConfig | None = None
    principals: tuple[str, ...] = ("public",)
    seed: int = 0
    force: bool = False
    store_path: str | None = None
    runstore_path: str | None = None
    cache_root: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "RunConfig":
        return _from_dict(cls, json.loads(s))


def _from_dict(cls, d):
    if d is None:
        return None
    kw = {}
    for f in fields(cls):
        v = d.get(f.name)
        if f.name == "pipeline":
            v = _from_dict(PipelineConfig, v)
        elif f.name in ("reader", "judge"):
            v = _from_dict(LLMConfig, v)
        elif f.name == "embedder":
            v = _from_dict(EmbedderConfig, v)
        elif f.name == "reranker":
            v = _from_dict(RerankerConfig, v)
        elif f.name in ("principals", "argv") and v is not None:
            v = tuple(v)
        if v is not None or f.name in d:
            kw[f.name] = v
    return cls(**kw)
```

`python/triplum/bench/factories.py`:
```python
"""Build model objects from configs, wrapped in the disk cache. API keys stay in the environment."""

from __future__ import annotations

from pathlib import Path

from triplum.bench.config import EmbedderConfig, LLMConfig, RerankerConfig
from triplum.cache import Cache
from triplum.embed.cached import CachedEmbedder
from triplum.embed.fake import FakeEmbedder
from triplum.embed.protocol import EmbeddingSpec
from triplum.llm.cached import CachedLLM
from triplum.llm.fake import FakeLLM
from triplum.llm.protocol import GenParams


def make_embedder(cfg: EmbedderConfig, cache_root: Path | str | None):
    cache = Cache(cache_root)
    if cfg.kind == "fake":
        return CachedEmbedder(FakeEmbedder(dims=cfg.dims), cache)
    if cfg.kind == "openai":
        from triplum.embed.openai_compat import OpenAICompatEmbedder

        spec = EmbeddingSpec(model=cfg.model, revision=cfg.revision or "api", dims=cfg.dims,
                             query_prefix=cfg.query_prefix, passage_prefix=cfg.passage_prefix, runtime="api")
        return CachedEmbedder(OpenAICompatEmbedder(spec, base_url=cfg.base_url, api_key_env=cfg.api_key_env), cache)
    if cfg.kind == "st":
        from triplum.embed.sentence_transformers import SentenceTransformersEmbedder

        return CachedEmbedder(SentenceTransformersEmbedder.from_model(
            cfg.model, query_prefix=cfg.query_prefix, passage_prefix=cfg.passage_prefix), cache)
    if cfg.kind == "fastembed":
        from triplum.embed.fastembed import FastEmbedEmbedder

        return CachedEmbedder(FastEmbedEmbedder.from_model(
            cfg.model, query_prefix=cfg.query_prefix, passage_prefix=cfg.passage_prefix), cache)
    raise ValueError(f"unknown embedder kind {cfg.kind}")


def make_llm(cfg: LLMConfig, cache_root: Path | str | None):
    cache = Cache(cache_root)
    if cfg.kind == "fake":
        return CachedLLM(FakeLLM(model=cfg.model), cache)
    if cfg.kind == "openai":
        from triplum.llm.openai_compat import OpenAICompatLLM

        return CachedLLM(OpenAICompatLLM(cfg.model, base_url=cfg.base_url, api_key_env=cfg.api_key_env), cache)
    if cfg.kind == "cli":
        from triplum.llm.cli import CliLLM

        return CachedLLM(CliLLM(cfg.model, list(cfg.argv), json_field=cfg.json_field), cache)
    raise ValueError(f"unknown llm kind {cfg.kind}")


def gen_params(cfg: LLMConfig) -> GenParams:
    return GenParams(temperature=cfg.temperature, max_tokens=cfg.max_tokens)


def make_reranker(cfg: RerankerConfig | None):
    if cfg is None:
        return None
    if cfg.kind == "fake":
        from triplum.rerank.fake import FakeReranker

        return FakeReranker()
    if cfg.kind == "cross_encoder":
        from triplum.rerank.cross_encoder import CrossEncoderReranker

        return CrossEncoderReranker.from_model(cfg.model)
    raise ValueError(f"unknown reranker kind {cfg.kind}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/bench tests/test_config.py
git commit -m "Add frozen run/pipeline configs with stable hashes and model factories"
```

---

### Task 5: Run store with events and prices

**Files:**
- Create: `python/triplum/bench/runstore.py`
- Test: `tests/test_runstore.py`

- [ ] **Step 1: Write the failing test**

`tests/test_runstore.py`:
```python
from triplum.bench.runstore import RunStore


def test_runstore_roundtrip(tmp_path):
    rs = RunStore(tmp_path / "runs.db")
    rs.set_price("m1", "openai", usd_in_per_m=1.0, usd_out_per_m=2.0, usd_cached_in_per_m=0.5, source="test")
    run_id = rs.start_run({"dataset": "musique", "pipeline": "dense", "config_hash": "abc", "config_json": "{}",
                           "code_version": "deadbeef", "dirty": 0, "corpus_hash": "c", "questions_hash": "q",
                           "n": 1, "embedding_spec": "e", "reranker_spec": None, "reader_model": "m1",
                           "judge_model": None, "seed": 0, "viewer_json": "{}", "host": "h"})
    rec = rs.recorder(run_id)
    with rec.stage("read", question_id="q1", provider="openai", model="m1") as ev:
        ev.usage(1_000_000, 500_000, cached_in=0)
    rs.add_question(run_id, {"question_id": "q1", "retrieved_json": "[]", "answer": "x", "em": 1.0, "f1": 1.0,
                             "contain": 1.0, "judge": None, "r2": 0.5, "r5": 1.0, "input_tokens": 1_000_000,
                             "output_tokens": 500_000, "usd": rec.cost("m1", 1_000_000, 500_000, 0),
                             "latency_s": 0.1, "n_passages": 5})
    rs.finish_run(run_id, status="ok", wall_s=1.0, cache_hits=0, cache_misses=1)
    runs = rs.runs()
    assert runs.height == 1 and runs["status"][0] == "ok"
    ev = rs.events(run_id)
    assert ev.height == 1 and ev["usd"][0] == 2.0 and ev["stage"][0] == "read"
    qs = rs.questions(run_id)
    assert qs["usd"][0] == 2.0


def test_find_existing_run(tmp_path):
    rs = RunStore(tmp_path / "runs.db")
    meta = {"dataset": "d", "pipeline": "p", "config_hash": "h", "config_json": "{}", "code_version": "v", "dirty": 0,
            "corpus_hash": "c", "questions_hash": "q", "n": 1, "embedding_spec": None, "reranker_spec": None,
            "reader_model": "m", "judge_model": None, "seed": 0, "viewer_json": "{}", "host": "h"}
    rid = rs.start_run(meta)
    rs.finish_run(rid, status="ok", wall_s=0, cache_hits=0, cache_misses=0)
    assert rs.find_run(identity_hash=rs.identity_hash(meta)) == rid
    assert rs.find_run(identity_hash="nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runstore.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/bench/runstore.py`:
```python
"""The run store is the metrics store: runs, per-question rows, timed and priced events, prices."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import polars as pl

from triplum.cache import content_key
from triplum.data.schema import now_us

DDL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, identity_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
  dataset TEXT NOT NULL, pipeline TEXT NOT NULL, config_hash TEXT NOT NULL, config_json TEXT NOT NULL,
  code_version TEXT NOT NULL, dirty INTEGER NOT NULL, corpus_hash TEXT NOT NULL, questions_hash TEXT NOT NULL,
  n INTEGER NOT NULL, embedding_spec TEXT, reranker_spec TEXT, reader_model TEXT NOT NULL, judge_model TEXT,
  seed INTEGER NOT NULL, viewer_json TEXT NOT NULL, host TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running', wall_s REAL, cache_hits INTEGER, cache_misses INTEGER
) STRICT;
CREATE INDEX IF NOT EXISTS runs_identity ON runs(identity_hash);
CREATE TABLE IF NOT EXISTS run_questions (
  run_id TEXT NOT NULL REFERENCES runs(run_id), question_id TEXT NOT NULL, retrieved_json TEXT NOT NULL,
  answer TEXT NOT NULL, em REAL NOT NULL, f1 REAL NOT NULL, contain REAL NOT NULL, judge REAL,
  r2 REAL NOT NULL, r5 REAL NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
  usd REAL, latency_s REAL NOT NULL, n_passages INTEGER NOT NULL,
  PRIMARY KEY (run_id, question_id)
) STRICT;
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL REFERENCES runs(run_id), stage TEXT NOT NULL, question_id TEXT, provider TEXT, model TEXT,
  started_at INTEGER NOT NULL, ended_at INTEGER NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0, cached_input_tokens INTEGER NOT NULL DEFAULT 0,
  cached INTEGER NOT NULL DEFAULT 0, usd REAL
) STRICT;
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, stage);
CREATE TABLE IF NOT EXISTS prices (
  model TEXT NOT NULL, provider TEXT NOT NULL, usd_in_per_m REAL NOT NULL, usd_out_per_m REAL NOT NULL,
  usd_cached_in_per_m REAL NOT NULL, valid_from INTEGER NOT NULL, source TEXT NOT NULL,
  PRIMARY KEY (model, provider, valid_from)
) STRICT;
CREATE TABLE IF NOT EXISTS run_artifacts (
  run_id TEXT NOT NULL REFERENCES runs(run_id), kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
  PRIMARY KEY (run_id, kind)
) STRICT;
"""

IDENTITY_FIELDS = ("dataset", "pipeline", "config_hash", "code_version", "corpus_hash", "questions_hash",
                   "n", "embedding_spec", "reranker_spec", "reader_model", "judge_model", "seed", "viewer_json")


class RunStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(DDL)

    # ---- prices -----------------------------------------------------------------------------

    def set_price(self, model: str, provider: str, *, usd_in_per_m: float, usd_out_per_m: float,
                  usd_cached_in_per_m: float, source: str, valid_from: int | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
            (model, provider, usd_in_per_m, usd_out_per_m, usd_cached_in_per_m, valid_from or now_us(), source),
        )

    def price(self, model: str) -> tuple[float, float, float] | None:
        row = self.conn.execute(
            "SELECT usd_in_per_m, usd_out_per_m, usd_cached_in_per_m FROM prices WHERE model = ?"
            " ORDER BY valid_from DESC LIMIT 1", (model,)
        ).fetchone()
        return None if row is None else (row[0], row[1], row[2])

    # ---- runs -------------------------------------------------------------------------------

    @staticmethod
    def identity_hash(meta: dict) -> str:
        return content_key("run", {k: meta.get(k) for k in IDENTITY_FIELDS})

    def find_run(self, identity_hash: str) -> str | None:
        row = self.conn.execute(
            "SELECT run_id FROM runs WHERE identity_hash = ? AND status = 'ok' ORDER BY created_at DESC LIMIT 1",
            (identity_hash,),
        ).fetchone()
        return None if row is None else row[0]

    def start_run(self, meta: dict) -> str:
        run_id = uuid.uuid4().hex[:12]
        cols = ["run_id", "identity_hash", "created_at", *meta.keys()]
        vals = [run_id, self.identity_hash(meta), now_us(), *meta.values()]
        self.conn.execute(f"INSERT INTO runs({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        return run_id

    def finish_run(self, run_id: str, *, status: str, wall_s: float, cache_hits: int, cache_misses: int) -> None:
        self.conn.execute(
            "UPDATE runs SET status = ?, wall_s = ?, cache_hits = ?, cache_misses = ? WHERE run_id = ?",
            (status, wall_s, cache_hits, cache_misses, run_id),
        )

    def add_question(self, run_id: str, row: dict) -> None:
        cols = ["run_id", *row.keys()]
        self.conn.execute(
            f"INSERT OR REPLACE INTO run_questions({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [run_id, *row.values()],
        )

    def add_artifact(self, run_id: str, kind: str, path: str, sha256: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO run_artifacts VALUES (?,?,?,?)", (run_id, kind, path, sha256))

    def recorder(self, run_id: str) -> "Recorder":
        return Recorder(self, run_id)

    # ---- reads ------------------------------------------------------------------------------

    def _frame(self, sql: str, params: tuple = ()) -> pl.DataFrame:
        cur = self.conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pl.DataFrame(cur.fetchall(), schema=cols, orient="row")

    def runs(self) -> pl.DataFrame:
        return self._frame("SELECT * FROM runs ORDER BY created_at")

    def questions(self, run_id: str) -> pl.DataFrame:
        return self._frame("SELECT * FROM run_questions WHERE run_id = ?", (run_id,))

    def events(self, run_id: str) -> pl.DataFrame:
        return self._frame("SELECT * FROM events WHERE run_id = ? ORDER BY started_at", (run_id,))


class _Event:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_in = 0
        self.cached = False

    def usage(self, input_tokens: int, output_tokens: int, cached_in: int = 0, cached: bool = False) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_in += cached_in
        self.cached = self.cached or cached


class Recorder:
    def __init__(self, store: RunStore, run_id: str) -> None:
        self.store = store
        self.run_id = run_id
        self.cache_hits = 0
        self.cache_misses = 0

    def cost(self, model: str | None, input_tokens: int, output_tokens: int, cached_in: int) -> float | None:
        p = self.store.price(model) if model else None
        if p is None:
            return None
        usd_in, usd_out, usd_cached = p
        return ((input_tokens - cached_in) * usd_in + cached_in * usd_cached + output_tokens * usd_out) / 1e6

    @contextmanager
    def stage(self, stage: str, *, question_id: str | None = None, provider: str | None = None, model: str | None = None):
        ev = _Event()
        t0 = time.time_ns() // 1000
        try:
            yield ev
        finally:
            t1 = time.time_ns() // 1000
            if ev.cached:
                self.cache_hits += 1
            elif ev.input_tokens or ev.output_tokens:
                self.cache_misses += 1
            usd = None if ev.cached else self.cost(model, ev.input_tokens, ev.output_tokens, ev.cached_in)
            self.store.conn.execute(
                "INSERT INTO events(run_id, stage, question_id, provider, model, started_at, ended_at,"
                " input_tokens, output_tokens, cached_input_tokens, cached, usd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.run_id, stage, question_id, provider, model, t0, t1, ev.input_tokens, ev.output_tokens,
                 ev.cached_in, int(ev.cached), usd),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runstore.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/bench/runstore.py tests/test_runstore.py
git commit -m "Add run store: runs, per-question rows, priced timed events, prices, artifacts"
```

---

### Task 6: Indexing, runner, report

**Files:**
- Create: `python/triplum/bench/index.py`, `python/triplum/bench/runner.py`, `python/triplum/bench/report.py`
- Test: `tests/integration/__init__.py` (empty), `tests/integration/test_pipelines_fixture.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_pipelines_fixture.py`:
```python
import pytest

from triplum.bench.config import EmbedderConfig, LLMConfig, PipelineConfig, RerankerConfig, RunConfig
from triplum.bench.report import summary
from triplum.bench.runner import run_benchmark
from triplum.bench.runstore import RunStore

FAKE_READER = LLMConfig(kind="fake")
FAKE_EMB = EmbedderConfig(kind="fake", dims=64)


def _cfg(tmp_path, name, dataset="musique", **kw):
    return RunConfig(
        dataset=dataset, n=20, fixture=True,
        pipeline=PipelineConfig(name=name, reader=FAKE_READER, embedder=FAKE_EMB,
                                reranker=RerankerConfig(kind="fake") if name == "hybrid" else None, **kw),
        judge=LLMConfig(kind="fake", model="judge-fake"),
        store_path=str(tmp_path / f"{dataset}.sqlite"), runstore_path=str(tmp_path / "runs.db"),
        cache_root=str(tmp_path / "cache"),
    )


@pytest.mark.parametrize("dataset", ["hotpotqa", "musique", "twowiki"])
def test_all_baselines_run_on_fixture(tmp_path, dataset):
    ids = {name: run_benchmark(_cfg(tmp_path, name, dataset)) for name in ("closed_book", "bm25", "dense", "hybrid", "oracle")}
    rs = RunStore(tmp_path / "runs.db")
    s = summary(rs).sort("pipeline")
    assert s.height == 5 and set(s["pipeline"]) == set(ids)
    by = {r["pipeline"]: r for r in s.iter_rows(named=True)}
    assert by["oracle"]["r5"] == 1.0
    assert by["closed_book"]["r5"] == 0.0 and by["closed_book"]["n_passages"] == 0.0
    assert by["oracle"]["r5"] >= by["dense"]["r5"] >= by["closed_book"]["r5"]
    for r in by.values():
        assert r["n"] == 20 and r["indexing_s"] >= 0 and r["latency_s"] >= 0
    assert rs.questions(ids["dense"]).height == 20


def test_identical_run_is_a_lookup(tmp_path):
    a = run_benchmark(_cfg(tmp_path, "bm25"))
    b = run_benchmark(_cfg(tmp_path, "bm25"))
    assert a == b
    c = run_benchmark(_cfg(tmp_path, "bm25", top_k=3))
    assert c != a
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/bench/index.py`:
```python
"""Make sure the dataset is in the store: documents, chunks, and embeddings for a spec.
Everything is idempotent and skips what exists (design D6a)."""

from __future__ import annotations

from triplum.bench.runstore import Recorder
from triplum.embed.protocol import Embedder
from triplum.eval.datasets.hipporag import Dataset
from triplum.store.sqlite.store import SqliteStore


def ensure_documents(store: SqliteStore, ds: Dataset, rec: Recorder) -> None:
    n = store.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    if n == ds.chunks.height:
        return
    with rec.stage("index.documents"):
        store.put_documents(ds.documents, ds.grants)
        store.put_chunks(ds.chunks)


def ensure_embeddings(store: SqliteStore, ds: Dataset, embedder: Embedder, rec: Recorder, batch: int = 256) -> None:
    ids = ds.chunks["id"].to_list()
    texts = ds.chunks["text"].to_list()
    have = store.has_embeddings(embedder.spec, ids)
    todo = [i for i, h in enumerate(have) if not h]
    if not todo:
        return
    with rec.stage("index.embed", model=embedder.spec.model, provider=embedder.spec.runtime) as ev:
        for start in range(0, len(todo), batch):
            idx = todo[start : start + batch]
            vecs = embedder.embed_passages([texts[i] for i in idx])
            store.put_embeddings(embedder.spec, [ids[i] for i in idx], vecs)
            ev.usage(sum(len(texts[i].split()) for i in idx), 0)
```

`python/triplum/bench/runner.py`:
```python
"""Compose stages from a RunConfig, record everything, return the run id."""

from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path

import polars as pl

from triplum.bench import factories
from triplum.bench.config import RunConfig
from triplum.bench.index import ensure_documents, ensure_embeddings
from triplum.bench.runstore import RunStore
from triplum.cache import default_root
from triplum.data.viewer import Viewer
from triplum.eval import metrics
from triplum.eval.datasets import hipporag as hr
from triplum.eval.judge import judge_correct
from triplum.generate.reader import read
from triplum.retrieve import stages
from triplum.store.sqlite.store import SqliteStore


def code_version() -> tuple[str, int]:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.strip() != ""
        return sha, int(dirty)
    except Exception:
        return "unknown", 1


def _retrieve(cfg: RunConfig, ds, store, embedder, reranker, viewer):
    p = cfg.pipeline
    if p.name == "closed_book":
        return stages.none(ds.questions)
    if p.name == "oracle":
        return stages.oracle(ds.questions, p.top_k)
    if p.name == "bm25":
        return stages.bm25(ds.questions, store, p.top_k, viewer)
    if p.name == "dense":
        return stages.dense(ds.questions, store, embedder, p.top_k, viewer)
    if p.name == "hybrid":
        return stages.hybrid(ds.questions, store, embedder, reranker, p.top_k, p.candidates, viewer)
    raise ValueError(f"unknown pipeline {p.name}")


def run_benchmark(cfg: RunConfig) -> str:
    t_start = time.perf_counter()
    root = Path(cfg.cache_root) if cfg.cache_root else default_root()
    ds = hr.load_fixture(cfg.dataset, cfg.n) if cfg.fixture else hr.load(cfg.dataset, cfg.n)
    p = cfg.pipeline
    needs_embed = p.name in ("dense", "hybrid")
    embedder = factories.make_embedder(p.embedder, root) if needs_embed and p.embedder else None
    reranker = factories.make_reranker(p.reranker) if p.name == "hybrid" else None
    reader = factories.make_llm(p.reader, root)
    judge = factories.make_llm(cfg.judge, root) if cfg.judge else None
    viewer = Viewer(principals=frozenset(cfg.principals))
    sha, dirty = code_version()
    rs = RunStore(cfg.runstore_path or root / "runs.db")
    meta = {
        "dataset": ds.name, "pipeline": p.name, "config_hash": p.hash(), "config_json": cfg.to_json(),
        "code_version": sha, "dirty": dirty, "corpus_hash": ds.corpus_hash, "questions_hash": ds.questions_hash,
        "n": ds.questions.height, "embedding_spec": embedder.spec.hash() if embedder else None,
        "reranker_spec": reranker.spec.hash() if reranker else None, "reader_model": p.reader.model,
        "judge_model": cfg.judge.model if cfg.judge else None, "seed": cfg.seed,
        "viewer_json": json.dumps(sorted(viewer.principals)), "host": platform.node(),
    }
    if not cfg.force:
        existing = rs.find_run(rs.identity_hash(meta))
        if existing:
            return existing
    run_id = rs.start_run(meta)
    rec = rs.recorder(run_id)
    store_path = Path(cfg.store_path) if cfg.store_path else root / "stores" / f"{ds.name}-{ds.corpus_hash[:8]}.sqlite"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(store_path)
    status = "failed"
    try:
        ensure_documents(store, ds, rec)
        if embedder is not None:
            ensure_embeddings(store, ds, embedder, rec)
        with rec.stage("retrieve"):
            retrieved = _retrieve(cfg, ds, store, embedder, reranker, viewer)
        answers = read(ds.questions, retrieved, store, reader, viewer, factories.gen_params(p.reader))
        for q, a in zip(ds.questions.iter_rows(named=True), answers.iter_rows(named=True)):
            with rec.stage("read", question_id=q["id"], provider=p.reader.kind, model=p.reader.model) as ev:
                ev.usage(a["input_tokens"], a["output_tokens"], cached=a["cached"])
            ids = retrieved.filter(pl.col("question_id") == q["id"]).sort("rank")["chunk_id"].to_list()
            jud = None
            if judge is not None:
                with rec.stage("judge", question_id=q["id"], provider=cfg.judge.kind, model=cfg.judge.model) as ev:
                    jc = judge_correct(judge, q["question"], q["aliases"], a["answer"])
                    jud = float(jc)
            rs.add_question(run_id, {
                "question_id": q["id"], "retrieved_json": json.dumps(ids), "answer": a["answer"],
                "em": metrics.exact_match(a["answer"], q["aliases"]), "f1": metrics.f1(a["answer"], q["aliases"]),
                "contain": metrics.contain(a["answer"], q["aliases"]), "judge": jud,
                "r2": metrics.recall_at_k(q["gold_chunk_ids"], ids, 2), "r5": metrics.recall_at_k(q["gold_chunk_ids"], ids, 5),
                "input_tokens": a["input_tokens"], "output_tokens": a["output_tokens"],
                "usd": None if a["cached"] else rec.cost(p.reader.model, a["input_tokens"], a["output_tokens"], 0),
                "latency_s": a["latency_s"], "n_passages": a["n_passages"],
            })
        rs.add_artifact(run_id, "store", str(store_path), hr.sha256_file(store_path))
        status = "ok"
    finally:
        store.close()
        rs.finish_run(run_id, status=status, wall_s=time.perf_counter() - t_start,
                      cache_hits=rec.cache_hits, cache_misses=rec.cache_misses)
    return run_id
```

`python/triplum/bench/report.py`:
```python
"""Summary frames over the run store."""

from __future__ import annotations

import polars as pl

from triplum.bench.runstore import RunStore


def summary(rs: RunStore, run_ids: list[str] | None = None) -> pl.DataFrame:
    runs = rs.runs()
    if run_ids:
        runs = runs.filter(pl.col("run_id").is_in(run_ids))
    rows = []
    for r in runs.iter_rows(named=True):
        q = rs.questions(r["run_id"])
        ev = rs.events(r["run_id"])
        idx = ev.filter(pl.col("stage").str.starts_with("index."))
        rows.append({
            "run_id": r["run_id"], "dataset": r["dataset"], "pipeline": r["pipeline"], "n": q.height,
            "reader_model": r["reader_model"], "embedding_spec": r["embedding_spec"],
            "em": q["em"].mean(), "f1": q["f1"].mean(), "contain": q["contain"].mean(),
            "judge": q["judge"].mean(), "r2": q["r2"].mean(), "r5": q["r5"].mean(),
            "n_passages": q["n_passages"].mean(), "latency_s": q["latency_s"].mean(),
            "usd_per_q": q["usd"].mean(), "usd_total": q["usd"].sum(),
            "indexing_s": float(((idx["ended_at"] - idx["started_at"]).sum() or 0) / 1e6),
            "cache_hits": r["cache_hits"], "cache_misses": r["cache_misses"], "wall_s": r["wall_s"],
        })
    return pl.DataFrame(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/bench tests/integration
git commit -m "Add indexing, benchmark runner with full run identity, and summary report"
```

---

### Task 7: CLI, notebook, sweep

**Files:**
- Create: `python/triplum/bench/cli.py`, `notebooks/runs.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Test: append to `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:
```python
from triplum.bench.cli import build_run_config, parse_args


def test_cli_builds_run_config(tmp_path):
    ns = parse_args(["bench", "run", "--pipeline", "dense", "--dataset", "musique", "--n", "20", "--fixture",
                     "--reader", "fake", "--embedder", "fake", "--judge", "fake",
                     "--cache-root", str(tmp_path)])
    rc = build_run_config(ns)
    assert rc.pipeline.name == "dense" and rc.n == 20 and rc.fixture and rc.pipeline.embedder.kind == "fake"
    assert rc.judge is not None and rc.cache_root == str(tmp_path)


def test_cli_sweep_reads_embedder_specs(tmp_path):
    specs = tmp_path / "emb.json"
    specs.write_text('[{"kind": "fake", "dims": 8}, {"kind": "fake", "dims": 16}]')
    ns = parse_args(["bench", "sweep", "--dataset", "musique", "--fixture", "--reader", "fake",
                     "--embedders", str(specs), "--cache-root", str(tmp_path)])
    cfgs = [build_run_config(ns, embedder=e) for e in __import__("json").loads(specs.read_text())]
    assert [c.pipeline.embedder.dims for c in cfgs] == [8, 16] and all(c.pipeline.name == "dense" for c in cfgs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: the two new tests FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/bench/cli.py`:
```python
"""triplum CLI: data fetch | bench run | bench sweep | bench report."""

from __future__ import annotations

import argparse
import json
import sys

from triplum.bench.config import EmbedderConfig, LLMConfig, PipelineConfig, RerankerConfig, RunConfig


def _llm(kind: str, model: str | None, base_url: str | None) -> LLMConfig:
    if kind == "fake":
        return LLMConfig(kind="fake")
    if kind == "openai":
        return LLMConfig(kind="openai", model=model or "gpt-5.6-luna", base_url=base_url)
    if kind == "claude-cli":
        return LLMConfig(kind="cli", model=model or "claude-cli", argv=("claude", "-p", "--output-format", "json"), json_field="result")
    raise SystemExit(f"unknown reader kind {kind}")


def _embedder(spec: dict | str) -> EmbedderConfig:
    if isinstance(spec, str):
        if spec == "fake":
            return EmbedderConfig(kind="fake", dims=64)
        if spec.startswith("st:"):
            return EmbedderConfig(kind="st", model=spec[3:])
        if spec.startswith("openai:"):
            model = spec[7:]
            dims = 3072 if "large" in model else 1536
            return EmbedderConfig(kind="openai", model=model, dims=dims)
        raise SystemExit(f"unknown embedder {spec}")
    return EmbedderConfig(**spec)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="triplum")
    sub = p.add_subparsers(dest="cmd", required=True)
    data = sub.add_parser("data").add_subparsers(dest="data_cmd", required=True)
    data.add_parser("fetch").add_argument("--dataset", choices=["hotpotqa", "musique", "twowiki", "all"], default="all")
    bench = sub.add_parser("bench").add_subparsers(dest="bench_cmd", required=True)
    for name in ("run", "sweep"):
        b = bench.add_parser(name)
        if name == "run":
            b.add_argument("--pipeline", required=True, choices=["closed_book", "bm25", "dense", "hybrid", "oracle"])
            b.add_argument("--embedder", default="fake")
        else:
            b.add_argument("--embedders", required=True, help="JSON file: list of EmbedderConfig dicts")
        b.add_argument("--dataset", required=True, choices=["hotpotqa", "musique", "twowiki"])
        b.add_argument("--n", type=int, default=None)
        b.add_argument("--fixture", action="store_true")
        b.add_argument("--reader", default="fake", help="fake | openai | claude-cli")
        b.add_argument("--reader-model", default=None)
        b.add_argument("--base-url", default=None)
        b.add_argument("--judge", default=None, help="fake | openai")
        b.add_argument("--judge-model", default=None)
        b.add_argument("--reranker", default="fake", help="fake | cross_encoder:<model>")
        b.add_argument("--top-k", type=int, default=5)
        b.add_argument("--candidates", type=int, default=20)
        b.add_argument("--force", action="store_true")
        b.add_argument("--cache-root", default=None)
        b.add_argument("--runstore", default=None)
    rep = bench.add_parser("report")
    rep.add_argument("--runstore", default=None)
    return p.parse_args(argv)


def build_run_config(ns: argparse.Namespace, embedder: dict | str | None = None) -> RunConfig:
    reader = _llm(ns.reader, ns.reader_model, ns.base_url)
    judge = _llm(ns.judge, ns.judge_model, ns.base_url) if ns.judge else None
    rr = ns.reranker
    reranker = RerankerConfig(kind="fake") if rr == "fake" else RerankerConfig(kind="cross_encoder", model=rr.split(":", 1)[1])
    pipeline_name = getattr(ns, "pipeline", "dense")
    emb = _embedder(embedder if embedder is not None else getattr(ns, "embedder", "fake"))
    pipeline = PipelineConfig(name=pipeline_name, reader=reader, top_k=ns.top_k, candidates=ns.candidates,
                              embedder=emb, reranker=reranker if pipeline_name == "hybrid" else None)
    return RunConfig(dataset=ns.dataset, pipeline=pipeline, n=ns.n, fixture=ns.fixture, judge=judge,
                     force=ns.force, cache_root=ns.cache_root, runstore_path=ns.runstore)


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(sys.argv[1:] if argv is None else argv)
    if ns.cmd == "data":
        from triplum.eval.datasets import hipporag as hr

        for name in (hr.FILES if ns.dataset == "all" else [ns.dataset]):
            qp, cp = hr.fetch(name)
            print(f"{name}: {qp} {cp} (verified)")
        return 0
    from triplum.bench.report import summary
    from triplum.bench.runner import run_benchmark
    from triplum.bench.runstore import RunStore
    from triplum.cache import default_root

    if ns.bench_cmd == "report":
        rs = RunStore(ns.runstore or default_root() / "runs.db")
        with __import__("polars").Config(tbl_cols=-1, tbl_width_chars=200):
            print(summary(rs))
        return 0
    cfgs = [build_run_config(ns)] if ns.bench_cmd == "run" else [
        build_run_config(ns, embedder=e) for e in json.loads(open(ns.embedders).read())
    ]
    ids = [run_benchmark(c) for c in cfgs]
    rs = RunStore(cfgs[0].runstore_path or default_root() / "runs.db")
    with __import__("polars").Config(tbl_cols=-1, tbl_width_chars=200):
        print(summary(rs, ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `pyproject.toml` under `[project]`:
```toml
[project.scripts]
triplum = "triplum.bench.cli:main"
```

`notebooks/runs.py` (marimo):
```python
import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import polars as pl

    from triplum.bench.report import summary
    from triplum.bench.runstore import RunStore
    from triplum.cache import default_root

    return RunStore, default_root, mo, pl, summary


@app.cell
def _(RunStore, default_root, mo):
    path = mo.ui.text(value=str(default_root() / "runs.db"), label="run store")
    path
    return (path,)


@app.cell
def _(RunStore, path, summary):
    rs = RunStore(path.value)
    table = summary(rs)
    table
    return rs, table


@app.cell
def _(mo, rs, table):
    pick = mo.ui.dropdown(options=table["run_id"].to_list() if table.height else [], label="run")
    pick
    return (pick,)


@app.cell
def _(pick, rs):
    rs.questions(pick.value) if pick.value else None
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests, then the CLI end to end on a fixture**

Run: `uv sync --all-extras --group dev && uv run pytest tests/test_config.py -v`
Expected: 5 passed

Run: `uv run triplum bench run --pipeline hybrid --dataset musique --n 20 --fixture --reader fake --judge fake --cache-root /tmp/triplum-smoke`
Expected: a one-row summary table with `pipeline = hybrid`, `n = 20`, `r5` between 0 and 1.

- [ ] **Step 5: Full suite, lint, commit**

Run: `uv run pytest -q && uv run ruff check python tests scripts`
Expected: all green.

```bash
git add python/triplum/bench/cli.py notebooks pyproject.toml uv.lock tests/test_config.py
git commit -m "Add triplum CLI (data fetch, bench run/sweep/report) and marimo run browser"
```

---

## Self-review

**Spec coverage (scope items 7 to 12):** datasets and protocol with pinned hashes and fixtures (Task 1); pipelines closed-book, BM25, dense, hybrid, oracle with one shared reader prompt (Task 3, composed in Task 6); metrics EM, F1, Contain-Acc, Judge-Acc, R@2, R@5, tokens, cost, latency, indexing cost (Tasks 2, 5, 6); run store with runs, run_questions, run_artifacts, events, prices and the D8 identity (Task 5, 6); reports as Polars frames and the marimo notebook (Tasks 6, 7); embedding sweep as `bench sweep` over a list of embedder configs (Task 7); CLI (Task 7). Cache levels: call cache from part 1, artifact cache via `has_embeddings` and the chunk-count check in Task 6, run lookup by identity in Task 6.

Deferred with a note: hierarchical chunking (spec item 3's "implemented but unused") moves to the 2a plan where it is first used; the upstream-rebuild verification of the corpora moves to 2a as well; the `--cache-only` replay flag is not in this plan (a run with all reader calls cached shows `cache_misses = 0`, which is the same evidence).

**Placeholders:** none.

**Type consistency:** `stages.*` return the `SCHEMA` frame consumed by `read()` and the runner; `Dataset.questions` columns (`id`, `question`, `answer`, `aliases`, `gold_chunk_ids`, `qtype`) are used identically in Tasks 1, 3 and 6; `Recorder.stage/usage/cost` (Task 5) as used in Task 6; `RunStore.find_run/identity_hash` (Task 5) as used in Task 6; `factories.make_*` and `gen_params` (Task 4) as used in Task 6; `build_run_config(ns, embedder=...)` (Task 7) matches both test call shapes.
