"""Corpus records at the ingestion boundary, and the canonical batch they project onto.

A source yields `Document` records: the document's text, the segments the source ships as
units (passages, paragraphs, turns, pages), its grants and metadata. Identity is chosen by the
source and never by parse position (spec `2026-09-17-builtin-datasets.md`, per-source key
table). `CorpusBatch` is the canonical three-frame projection a collator makes from a list of
documents; it is what the store ingests.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import polars as pl
from pydantic import BaseModel, model_validator

from triplum.cache import content_key
from triplum.data import schema

DOC_SCHEMA = schema.polars_schema(schema.DOCUMENTS)
GRANT_SCHEMA = schema.polars_schema(schema.DOCUMENT_GRANTS)
CHUNK_SCHEMA = schema.polars_schema(schema.CHUNKS)

RECORD_VERSION = 1
"""Bumped when `content_id`, `chunk_id`, the record fields or the collators change what a
source's identity stands for; part of every source fingerprint."""


def content_id(*parts: str) -> str:
    """A 20-hex-character document id from the parts a source declares as its logical key."""
    return content_key("document", list(parts))[:20]


def chunk_id(document_id: str, ordinal: int) -> int:
    """Positive 60-bit chunk id from the document id and the segment's ordinal, so a question
    can name its gold without the corpus pass and ids never collide across sources."""
    return int(content_key("chunk", [document_id, ordinal])[:15], 16)


class Segment(BaseModel, frozen=True):
    """One unit of a document: a closed-open character span into `Document.text`."""

    ordinal: int
    start: int
    end: int
    parent: int | None = None  # ordinal of the enclosing segment
    level: int = 0


class Document(BaseModel, frozen=True):
    """A document with the segments its source ships. Ordinals are stable within a pinned
    layout and need not be contiguous, so a fixture keeps a subset with original ordinals."""

    id: str
    source: str
    text: str
    segments: tuple[Segment, ...] = ()
    uri: str | None = None
    observed_at: int = 0  # UTC microseconds (D2)
    grants: tuple[str, ...] = ("public",)
    metadata: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _default_segment(cls, data: Any) -> Any:
        if (
            isinstance(data, dict)
            and not data.get("segments")
            and isinstance(data.get("text"), str)
        ):
            data = {**data, "segments": (Segment(ordinal=0, start=0, end=len(data["text"])),)}
        return data

    @model_validator(mode="after")
    def _check(self) -> Document:
        ordinals = [s.ordinal for s in self.segments]
        if len(set(ordinals)) != len(ordinals) or min(ordinals) < 0:
            raise ValueError(f"{self.id}: segment ordinals must be unique and non-negative")
        level = {s.ordinal: s.level for s in self.segments}
        for s in self.segments:
            if not 0 <= s.start <= s.end <= len(self.text):
                raise ValueError(f"{self.id}: segment {s.ordinal} span outside the text")
            if s.parent is not None and level.get(s.parent, s.level) >= s.level:
                raise ValueError(
                    f"{self.id}: segment {s.ordinal} parent must exist at a lower level"
                )
        if not self.grants:
            raise ValueError(f"{self.id}: a document needs at least one grant")
        return self

    def chunk_ids(self) -> list[int]:
        return [chunk_id(self.id, s.ordinal) for s in self.segments]


class CorpusBatch(NamedTuple):
    """Documents, their grants and chunks in the canonical schemas.

    This is a batch value, not a dataset superclass. Sources may yield these directly,
    or a custom collator may construct them from source-specific records.
    """

    documents: pl.DataFrame
    grants: pl.DataFrame
    chunks: pl.DataFrame
