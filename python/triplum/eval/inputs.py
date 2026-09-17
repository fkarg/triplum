"""Task-owned evaluation records and schemas, independent of any corpus source."""

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


class GoldMappingError(ValueError):
    """A gold reference cannot be resolved, or a gold chunk is missing from the corpus. Silently
    dropping it would score an empty gold list as perfect recall, so loading fails instead."""


class Question(BaseModel, frozen=True):
    """A question with its gold chunk ids. `aliases` always starts with `answer` and holds no
    duplicates; `gold` is sorted and unique. Sources that promise gold for answerable questions
    raise `GoldMappingError` at parse time; that every gold id exists in the corpus is checked
    at materialization."""

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
            if isinstance(data.get("answer"), (int, float)):  # numeric answers occur upstream
                data["answer"] = str(data["answer"])
            aliases = [data.get("answer", "")]
            for alias in data.get("aliases", ()):
                alias = str(alias) if isinstance(alias, (int, float)) else alias
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

    @model_validator(mode="before")
    @classmethod
    def _text(cls, data: Any) -> Any:
        if isinstance(data, dict):  # numeric slots occur upstream (years, counts)
            data = {
                k: str(v)
                if k in ("subject", "predicate", "object") and isinstance(v, (int, float))
                else v
                for k, v in data.items()
            }
        return data
