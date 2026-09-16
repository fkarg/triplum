"""One reader prompt for every pipeline. Passages come from the store through the Viewer, so a
retrieved id the viewer may not see is silently dropped before the prompt is built."""

from __future__ import annotations

import time

import polars as pl

from triplum.cache import content_key
from triplum.data.viewer import Viewer
from triplum.llm.protocol import DEFAULT_PARAMS, LLM, GenParams, Message
from triplum.store.protocol import Store

SYSTEM = (
    "You answer questions using the given passages. Reply with the shortest possible answer: a "
    "name, date, number, or yes/no. Do not explain."
)
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}

PROMPT_HASH = content_key("reader_prompt", {"system": SYSTEM, "schema": ANSWER_SCHEMA})[:16]

OUT_SCHEMA = {
    "question_id": pl.Utf8,
    "answer": pl.Utf8,
    "input_tokens": pl.Int64,
    "output_tokens": pl.Int64,
    "cached": pl.Boolean,
    "latency_s": pl.Float64,
    "n_passages": pl.Int64,
}


def build_messages(question: str, passages: list[str]) -> list[Message]:
    if passages:
        ctx = "\n\n".join(f"Passage {i + 1}:\n{p}" for i, p in enumerate(passages))
        user = f"{ctx}\n\nQuestion: {question}"
    else:
        user = f"Question: {question}"
    return [Message("system", SYSTEM), Message("user", user)]


def read(
    questions: pl.DataFrame,
    retrieved: pl.DataFrame,
    store: Store,
    llm: LLM,
    viewer: Viewer,
    params: GenParams = DEFAULT_PARAMS,
) -> pl.DataFrame:
    rows = []
    for q in questions.iter_rows(named=True):
        ids = (
            retrieved.filter(pl.col("question_id") == q["id"]).sort("rank")["chunk_id"].to_list()
        )
        passages: list[str] = []
        if ids:
            chunks = store.get_chunks(ids, viewer)
            by_id = dict(zip(chunks["id"].to_list(), chunks["text"].to_list()))
            passages = [by_id[c] for c in ids if c in by_id]
        t0 = time.perf_counter()
        c = llm.complete(
            build_messages(q["question"], passages), schema=ANSWER_SCHEMA, params=params
        )
        answer = c.parsed.get("answer", "") if isinstance(c.parsed, dict) else c.text
        rows.append(
            (
                q["id"],
                str(answer),
                c.usage.input_tokens,
                c.usage.output_tokens,
                c.cached,
                time.perf_counter() - t0,
                len(passages),
            )
        )
    return pl.DataFrame(rows, schema=OUT_SCHEMA, orient="row")
