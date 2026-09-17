"""Task-owned evaluation records and schemas, independent of any corpus source."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import polars as pl
from pydantic import BaseModel, model_validator

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
TRIPLE_SCHEMA = {
    "question_id": pl.Utf8,
    "document_id": pl.Utf8,
    "subject": pl.Utf8,
    "predicate": pl.Utf8,
    "object": pl.Utf8,
}


class Question(BaseModel, frozen=True):
    """A question with its gold chunk ids. `aliases` always starts with `answer` and holds no
    duplicates; `gold` is sorted and unique. An answerable question must have gold when the
    benchmark ships a corpus; that cross-source rule is checked at materialization."""

    id: str
    question: str
    answer: str
    aliases: tuple[str, ...] = ()
    gold: tuple[int, ...] = ()
    qtype: str = ""
    answerable: bool = True
    as_of: int | None = None
    metadata: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            aliases = [data.get("answer", "")]
            for alias in data.get("aliases", ()):
                if alias not in aliases:
                    aliases.append(alias)
            data["aliases"] = tuple(aliases)
            data["gold"] = tuple(sorted(set(data.get("gold", ()))))
        return data


class Triple(BaseModel, frozen=True):
    """A gold triple, attributed to a question, a document, or neither."""

    subject: str
    predicate: str
    object: str
    question_id: str | None = None
    document_id: str | None = None


@dataclass
class QAEvaluation:
    """Question batches for QA scoring; independent of the corpus source."""

    questions: Iterable[pl.DataFrame]


@dataclass
class ExtractionEvaluation:
    """Gold triple batches for extraction scoring; never a requirement on corpus data."""

    triples: Iterable[pl.DataFrame]
