"""QA and retrieval metrics. EM/F1 follow HotpotQA's normalisation, aggregated as max over gold
aliases (HippoRAG convention), without the yes/no zeroing rule."""

from __future__ import annotations

import re
import string
from collections import Counter

_PUNCT = set(string.punctuation)


def normalize_answer(s: str) -> str:
    s = s.lower()
    s = "".join(ch for ch in s if ch not in _PUNCT)
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
        raise ValueError("recall_at_k needs at least one gold id")
    top = set(retrieved_ids[:k])
    return sum(1 for g in gold_ids if g in top) / len(gold_ids)
