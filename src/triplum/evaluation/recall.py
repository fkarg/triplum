"""Retrieval recall: how much of a question's gold evidence the top `k` hits contain."""

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from triplum.datatype import QAQuestion, RetrievalHit, SpanEvidence


class ResolvedSpan(BaseModel):
    """Characters `[start, end)` of the source `source_id` are gold evidence.

    Unknown fields are rejected, so a span cannot validate as `ResolvedDocument`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: UUID = Field(description="The `id` of the source holding the span.")
    start: int = Field(ge=0, description="Character offset of the first evidence character.")
    end: int = Field(description="Character offset after the last evidence character.")

    @model_validator(mode="after")
    def _nonempty(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"span [{self.start}, {self.end}) is empty")
        return self


class ResolvedDocument(BaseModel):
    """The source `source_id` as a whole is gold evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: UUID = Field(description="The `id` of the evidence source.")


type ResolvedEvidence = ResolvedSpan | ResolvedDocument


def resolve_evidence(
    question: QAQuestion, sources: Mapping[str, UUID], /
) -> list[list[ResolvedEvidence]]:
    """The question's evidence sets with each native document key replaced by its Source id.

    `sources` maps the benchmark's document keys to Source ids within one collection, usually
    `{s.external_id: s.id for s in corpus if s.external_id is not None}`. Resolve every question
    before retrieving: a key missing from `sources` raises `KeyError` naming question and key.
    """

    def resolve(document: str) -> UUID:
        if document not in sources:
            raise KeyError(f"question {question.id!r}: unknown document key {document!r}")
        return sources[document]

    return [
        [
            ResolvedSpan(source_id=resolve(e.document), start=e.start, end=e.end)
            if isinstance(e, SpanEvidence)
            else ResolvedDocument(source_id=resolve(e.document))
            for e in alternative
        ]
        for alternative in question.evidence
    ]


class RecallAtK(BaseModel):
    """Recall of one question's top `k` hits."""

    model_config = ConfigDict(frozen=True)

    recall: float | None = Field(
        description="Best alternative set's fraction of fully covered items; None without gold."
    )
    all_gold: bool | None = Field(
        description="Whether some alternative set is covered completely; None without gold."
    )
    retrieved_characters: int = Field(
        description="Distinct source characters in the top `k` hits; overlaps count once."
    )


def _merged(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _covered(item: ResolvedEvidence, intervals: dict[UUID, list[tuple[int, int]]]) -> bool:
    merged = intervals.get(item.source_id, [])
    if isinstance(item, ResolvedDocument):
        return bool(merged)
    return any(s <= item.start and item.end <= e for s, e in merged)


def score_recall(
    hits: Sequence[RetrievalHit],
    evidence: Sequence[Sequence[ResolvedEvidence]],
    /,
    *,
    ks: Sequence[int] = (2, 5),
) -> dict[int, RecallAtK]:
    """Recall of the first `k` hits for each `k` in `ks`; fewer hits are scored as they are.

    A span is covered when the union of the top-`k` chunks of its source contains all of it; a
    document when any top-`k` chunk comes from it. Each alternative set scores the fraction of
    its items covered; the question takes the best set. Items of different sets never combine.
    """
    if any(k < 1 for k in ks):
        raise ValueError("every k must be at least 1")
    result: dict[int, RecallAtK] = {}
    for k in ks:
        by_source: dict[UUID, list[tuple[int, int]]] = {}
        for hit in hits[:k]:
            chunk = hit.chunk
            by_source.setdefault(chunk.source_id, []).append(
                (chunk.start, chunk.start + len(chunk.text))
            )
        covered_by = {source: _merged(spans) for source, spans in by_source.items()}

        fractions = [
            sum(_covered(item, covered_by) for item in items) / len(items) for items in evidence
        ]
        result[k] = RecallAtK(
            recall=max(fractions) if fractions else None,
            all_gold=any(f == 1 for f in fractions) if fractions else None,
            retrieved_characters=sum(e - s for spans in covered_by.values() for s, e in spans),
        )
    return result


class RecallSummary(BaseModel):
    """Recall at one `k` across questions."""

    model_config = ConfigDict(frozen=True)

    recall: float | None = Field(description="Mean recall over `denominator` questions.")
    all_gold: float | None = Field(
        description="Fraction of the `denominator` questions with some set fully covered."
    )
    retrieved_characters: float | None = Field(
        description="Mean distinct retrieved characters over all `questions`."
    )
    questions: int = Field(description="Questions scored.")
    no_gold: int = Field(description="Questions without gold evidence.")
    denominator: int = Field(description="Questions in the recall means.")


def summarize_recall(
    scores: Iterable[RecallAtK], /, *, no_gold: Literal["exclude", "zero"] = "exclude"
) -> RecallSummary:
    """Means over questions at one `k`.

    Questions without gold are left out of the recall means, or counted as 0 with
    `no_gold="zero"`; either way they are counted in `no_gold`.
    """
    scores = list(scores)
    missing = sum(s.recall is None for s in scores)
    recalls = [s.recall for s in scores if s.recall is not None]
    all_gold = [float(s.all_gold) for s in scores if s.all_gold is not None]
    if no_gold == "zero":
        recalls += [0.0] * missing
        all_gold += [0.0] * missing

    def mean(values: Sequence[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return RecallSummary(
        recall=mean(recalls),
        all_gold=mean(all_gold),
        retrieved_characters=mean([s.retrieved_characters for s in scores]),
        questions=len(scores),
        no_gold=missing,
        denominator=len(recalls),
    )
