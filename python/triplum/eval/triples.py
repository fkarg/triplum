"""Intrinsic extraction metrics: predicted triples against gold triples, one-to-one.

Two matchers. `exact` needs all three normalised strings equal. `partial` is CaRB-style: token
F1 per slot with tokens equal up to inflection, subject and object at least 0.5, predicate
above 0.5 with auxiliaries and articles removed, so `work for` and `work against` do not match. Assignment is
greedy by descending mean slot score, one gold per prediction and one prediction per gold;
duplicate predictions count once. Scores are micro-averaged over groups (documents, or
questions where the gold is per question). See docs/research/benchmarks.md.
"""

from __future__ import annotations

import json
import re

import polars as pl

from triplum.extract.protocol import Extraction, normalise

PRED_STOP = frozenset({"is", "was", "were", "are", "be", "been", "being", "a", "an", "the", "to"})
Triple = tuple[str, str, str]


def _tokens(s: str, stop: frozenset[str] = frozenset()) -> list[str]:
    return [t for t in re.findall(r"\w+", s.lower().replace("_", " ")) if t not in stop]


def _same(a: str, b: str) -> bool:
    """Token equality up to inflection: equal, or one is a prefix of the other with at least
    four shared characters and at most three extra (`found`/`founded`, `hire`/`hired`)."""
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and len(long) - len(short) <= 3 and long.startswith(short)


def normalise_triple(s: str, p: str, o: str) -> Triple:
    return (normalise(s), normalise(p.replace("_", " ")), normalise(o))


def _token_f1(a: list[str], b: list[str]) -> float:
    unused = list(b)
    common = 0
    for t in a:
        hit = next((u for u in unused if _same(t, u)), None)
        if hit is not None:
            unused.remove(hit)
            common += 1
    if not common:
        return 0.0
    pr, rc = common / len(a), common / len(b)
    return 2 * pr * rc / (pr + rc)


def partial_score(pred: Triple, gold: Triple) -> float:
    """Mean slot F1 when every slot clears its threshold, else 0."""
    s = _token_f1(_tokens(pred[0]), _tokens(gold[0]))
    o = _token_f1(_tokens(pred[2]), _tokens(gold[2]))
    p = _token_f1(_tokens(pred[1], PRED_STOP), _tokens(gold[1], PRED_STOP))
    if s < 0.5 or o < 0.5 or p <= 0.5:
        return 0.0
    return (s + p + o) / 3


def match(pred: list[Triple], gold: list[Triple], mode: str) -> int:
    """Number of one-to-one matches between distinct predictions and gold triples."""
    pred = list(dict.fromkeys(pred))
    if mode == "exact":
        return len(set(pred) & set(gold))
    scored = sorted(
        (
            (sc, i, j)
            for i, p in enumerate(pred)
            for j, g in enumerate(gold)
            if (sc := partial_score(p, g)) > 0
        ),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    used_p: set[int] = set()
    used_g: set[int] = set()
    for _, i, j in scored:
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
    return len(used_p)


def prf(tp: int, n_pred: int, n_gold: int) -> tuple[float, float, float]:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def predicted(extraction: Extraction, chunks: pl.DataFrame) -> pl.DataFrame:
    """Surface triples (document_id, subject, predicate, object) from the claim facts: the
    entity labels asserted in the fact's support chunk, longest first; literals verbatim."""
    doc_of = dict(zip(chunks["id"].to_list(), chunks["document_id"].to_list()))
    chunk_of = dict(extraction.fact_support.select("fact_id", "chunk_id").iter_rows())
    labels: dict[tuple[str, int], str] = {}
    for f in extraction.facts.filter(pl.col("predicate") == "label").iter_rows(named=True):
        key = (f["subject_id"], chunk_of[f["id"]])
        if len(f["object_literal"]) > len(labels.get(key, "")):
            labels[key] = f["object_literal"]
    rows = []
    for f in extraction.facts.filter(
        ~pl.col("predicate").is_in(["label", "type", "same_as"])
    ).iter_rows(named=True):
        cid = chunk_of[f["id"]]
        subject = labels.get((f["subject_id"], cid))
        obj = f["object_literal"] if f["object_id"] is None else labels.get((f["object_id"], cid))
        if subject is None or obj is None:
            continue
        rows.append((doc_of[cid], subject, f["predicate"], obj))
    return pl.DataFrame(
        rows,
        schema={
            "document_id": pl.Utf8,
            "subject": pl.Utf8,
            "predicate": pl.Utf8,
            "object": pl.Utf8,
        },
        orient="row",
    )


def score(
    pred: pl.DataFrame, gold: pl.DataFrame, chunks: pl.DataFrame, questions: pl.DataFrame
) -> dict[str, float | int | None]:
    """Micro-averaged exact and partial precision, recall and F1. Gold rows with a document_id
    group by document; rows with only a question_id group by question, over the documents of
    that question's gold chunks (2Wiki evidences), and score recall only, since those gold
    lists are not exhaustive."""
    doc_of = dict(zip(chunks["id"].to_list(), chunks["document_id"].to_list()))
    pred_by_doc: dict[str, list[Triple]] = {}
    for r in pred.iter_rows(named=True):
        pred_by_doc.setdefault(r["document_id"], []).append(
            normalise_triple(r["subject"], r["predicate"], r["object"])
        )
    groups: dict[str, tuple[list[Triple], list[Triple]]] = {}
    per_question = gold.height > 0 and gold["document_id"].null_count() == gold.height
    if per_question:
        docs_of_q = {
            q["id"]: sorted({doc_of[c] for c in q["gold_chunk_ids"]})
            for q in questions.iter_rows(named=True)
        }
        for r in gold.iter_rows(named=True):
            key = r["question_id"]
            if key not in groups:
                groups[key] = (
                    [t for d in docs_of_q.get(key, []) for t in pred_by_doc.get(d, [])],
                    [],
                )
            groups[key][1].append(normalise_triple(r["subject"], r["predicate"], r["object"]))
    else:
        for r in gold.iter_rows(named=True):
            key = r["document_id"]
            if key not in groups:
                groups[key] = (pred_by_doc.get(key, []), [])
            groups[key][1].append(normalise_triple(r["subject"], r["predicate"], r["object"]))
    out: dict[str, float | int | None] = {"n_pred": pred.height, "n_gold": gold.height}
    out["duplicate_rate"] = (
        1 - sum(len(set(p)) for p, _ in groups.values()) / sum(len(p) for p, _ in groups.values())
        if any(p for p, _ in groups.values())
        else 0.0
    )
    n_pred = sum(len(set(p)) for p, _ in groups.values())
    n_gold = sum(len(g) for _, g in groups.values())
    for mode in ("exact", "partial"):
        tp = sum(match(p, g, mode) for p, g in groups.values())
        p, r, f = prf(tp, n_pred, n_gold)
        out[f"{mode}_recall"] = r
        out[f"{mode}_precision"] = None if per_question else p
        out[f"{mode}_f1"] = None if per_question else f
    return out


def gold_spans(documents: pl.DataFrame) -> set[tuple[str, str]]:
    """(document_id, normalised surface) of every entity a typed dataset lists in its document
    metadata (CoNLL04, SciERC); empty where there is none."""
    out = set()
    for d in documents.iter_rows(named=True):
        meta = json.loads(d["metadata"]) if d["metadata"] else {}
        for e in meta.get("entities", []):
            out.add((d["id"], normalise(e if isinstance(e, str) else e["text"])))
    return out


def predicted_spans(extraction: Extraction, chunks: pl.DataFrame) -> set[tuple[str, str]]:
    doc_of = dict(zip(chunks["id"].to_list(), chunks["document_id"].to_list()))
    chunk_of = dict(extraction.fact_support.select("fact_id", "chunk_id").iter_rows())
    return {
        (doc_of[chunk_of[f["id"]]], normalise(f["object_literal"]))
        for f in extraction.facts.filter(pl.col("predicate") == "label").iter_rows(named=True)
    }


def span_score(
    pred: set[tuple[str, str]], gold: set[tuple[str, str]]
) -> tuple[float, float, float]:
    return prf(len(pred & gold), len(pred), len(gold))
