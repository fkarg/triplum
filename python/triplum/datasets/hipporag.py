"""The HippoRAG / IRCoT 1000-question protocol for HotpotQA, MuSiQue and 2WikiMultiHopQA.

Source of truth: `reproduce/dataset/*.json` in github.com/OSU-NLP-Group/HippoRAG (MIT), content
under the upstream datasets' licences (HotpotQA CC BY-SA 4.0, MuSiQue CC BY 4.0, 2Wiki Apache-2.0).
"""

from __future__ import annotations

import json
from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import File, Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import ExtractionEvaluation, QAEvaluation

RAW_BASE = "https://raw.githubusercontent.com/OSU-NLP-Group/HippoRAG/main/reproduce/dataset/"

# sha256 of the files as fetched on 2026-09-16 (HippoRAG 2 generation; HotpotQA corpus = 9,811).
_FILES = {
    "hotpotqa": (
        ("hotpotqa.json", "3ad9c0bcbf93f41d7004ca6007049c904d2605046b314a2f7ecfb379c64cba6d"),
        (
            "hotpotqa_corpus.json",
            "9333647b922382776cd2cb02893b390d77984df85a91bfa8be411284978aca7d",
        ),
    ),
    "musique": (
        ("musique.json", "98ed4e21d3076532f6388d42320fb809599c63a0d8dffca8ece5e41922be6b46"),
        ("musique_corpus.json", "73157a03ce3f0b1a5673dd5dc12bb970c24976dbffc688af9eecdd758c97ffcb"),
    ),
    "twowiki": (
        (
            "2wikimultihopqa.json",
            "895cba294064df0c3302c76847b1fc08d99b5619f7663dfaa3b65cd780f1cac4",
        ),
        (
            "2wikimultihopqa_corpus.json",
            "9d6e352952aafb18dab22bf8195039461321a44a949df902ae83bce134ad238a",
        ),
    ),
}
_LICENCE = {
    "hotpotqa": "CC BY-SA 4.0 (HippoRAG files MIT)",
    "musique": "CC BY 4.0 (HippoRAG files MIT)",
    "twowiki": "Apache-2.0 (HippoRAG files MIT)",
}


def gold_key(name: str, title: str, text: str) -> tuple:
    """Titles are unique in the HotpotQA and 2Wiki corpora; MuSiQue needs (title, text)."""
    return (title,) if name in ("hotpotqa", "twowiki") else (title, text)


def parse(name: str, questions: list[dict], corpus: list[dict], n: int | None) -> Benchmark:
    if n is not None:
        questions = questions[:n]
    key_to_chunk: dict[tuple, int] = {}
    passages = []
    for i, rec in enumerate(corpus):
        key = gold_key(name, rec["title"], rec["text"])
        if key in key_to_chunk:
            raise base.GoldMappingError(f"{name}: duplicate corpus key {key[0]!r} at passage {i}")
        key_to_chunk[key] = i + 1
        passages.append((f"{name}:{i}", rec["title"], rec["text"], 0, None))
    documents, grants, chunks = base.corpus_frames(f"hipporag/{name}", passages)
    rows = []
    for q in questions:
        if name == "musique":
            qid, answer = q["id"], q["answer"]
            aliases = q.get("answer_aliases", [])
            gold = [
                (p["title"], p["paragraph_text"]) for p in q["paragraphs"] if p["is_supporting"]
            ]
            candidates = [(p["title"], p["paragraph_text"]) for p in q["paragraphs"]]
            qtype = q["id"].split("__")[0]
            meta = {"decomposition": q.get("question_decomposition", [])}
        else:
            qid, answer = q["_id"], q["answer"]
            aliases = []
            gold = sorted({(t,) for t, _ in q["supporting_facts"]})
            candidates = [(t,) for t, _ in q["context"]]
            qtype = q.get("type", "")
            meta = {"evidences": q["evidences"]} if name == "twowiki" else {}
        meta["candidate_chunk_ids"] = sorted(
            {key_to_chunk[c] for c in candidates if c in key_to_chunk}
        )
        gold_ids = base.resolve_gold(name, qid, gold, key_to_chunk)
        rows.append(
            base.question_row(qid, q["question"], answer, aliases, gold_ids, qtype, metadata=meta)
        )
    triples = base.empty(base.TRIPLE_SCHEMA)
    if name == "twowiki":
        triples = base.triples_frame(
            [(q["_id"], None, s, p, o) for q in questions for s, p, o in q["evidences"]]
        )
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(documents, grants, chunks)),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
        extraction=ExtractionEvaluation(FrameDataset(triples)) if not triples.is_empty() else None,
    )


def load_files(
    name: str, questions_path: Path, corpus_path: Path, n: int | None = None
) -> Benchmark:
    questions = json.loads(Path(questions_path).read_text())
    corpus = json.loads(Path(corpus_path).read_text())
    return parse(name, questions, corpus, n)


def _spec(name: str) -> Spec:
    (qfile, qhash), (cfile, chash) = _FILES[name]
    files = (
        File(RAW_BASE + qfile, f"hipporag/{qfile}", qhash),
        File(RAW_BASE + cfile, f"hipporag/{cfile}", chash),
    )
    return Spec(
        name=name,
        family="multihop",
        files=files,
        licence=_LICENCE[name],
        parse=lambda paths, n: load_files(name, paths[files[0].name], paths[files[1].name], n),
        default=True,
    )


SPECS = tuple(_spec(name) for name in _FILES)
