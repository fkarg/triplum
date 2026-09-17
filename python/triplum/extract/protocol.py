"""Identity and contracts of the extraction layer.

An extractor turns chunks into two frames. **Spans** are the things it recognised in a chunk:
entity mentions and literal values, by character offsets into the chunk text. **Claims** are the
candidate propositions it saw, every one of them, accepted or not: which span is the subject,
what the predicate is, which span is the object, and a status saying why a claim was or was not
materialised. `stages.extract` turns accepted claims into the canonical graph frames the same way
for every extractor, so the extractor never touches entity ids, facts or support groups.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Protocol

import polars as pl

from triplum.cache import content_key
from triplum.data import schema as canonical
from triplum.datasets.frames import FrameDataset

SPAN_SCHEMA = {
    "chunk_id": pl.Int64,
    "start": pl.Int64,
    "end": pl.Int64,
    "text": pl.Utf8,
    "label": pl.Utf8,  # NER type when the extractor gave one, else ""
    "kind": pl.Utf8,  # entity | literal
    "datatype": pl.Utf8,  # literals: date | number | money | percent | quantity | string
    "value": pl.Utf8,  # literals: the parsed, normalised value; the surface when unparsed
}
CLAIM_SCHEMA = {
    "chunk_id": pl.Int64,
    "sent_start": pl.Int64,
    "sent_end": pl.Int64,
    "subj_start": pl.Int64,
    "subj_end": pl.Int64,
    "predicate": pl.Utf8,
    "obj_start": pl.Int64,
    "obj_end": pl.Int64,
    "status": pl.Utf8,  # accepted | subordinate | negated | modal | ungrounded
    "reason": pl.Utf8,  # the rule that produced the claim, or why it was not materialised
}
STATUSES = ("accepted", "subordinate", "negated", "modal", "ungrounded")

ENTITY_SCHEMA = canonical.polars_schema(canonical.ENTITIES)
FACT_SCHEMA = canonical.polars_schema(canonical.FACTS)
SUPPORT_SCHEMA = canonical.polars_schema(canonical.FACT_SUPPORT)
MENTION_SCHEMA = canonical.polars_schema(canonical.MENTIONS)


@dataclass(frozen=True)
class ExtractorSpec:
    """What produced a set of claims: the extractor's name and rule-set version, the model it
    ran (with its revision) and its parameters. `hash()` is the `extractor` string on every
    support row and part of the graph identity."""

    name: str
    version: str
    model: str = ""
    revision: str = ""
    params: tuple[tuple[str, str], ...] = ()

    def hash(self) -> str:
        return content_key("extractor", asdict(self))[:16]


@dataclass(frozen=True)
class ResolverSpec:
    """Which entity resolver ran and with what threshold; part of the graph identity."""

    name: str  # none | exact | fuzzy
    threshold: float = 1.0

    def hash(self) -> str:
        return content_key("resolver", asdict(self))[:16]


class Extractor(Protocol):
    spec: ExtractorSpec
    seed_sensitive: bool

    def run(self, chunks: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Spans and claims (`SPAN_SCHEMA`, `CLAIM_SCHEMA`) for the given canonical chunks.
        Deterministic: same chunks, same frames, with no clock, randomness or network."""
        ...


@dataclass(frozen=True)
class Extraction:
    """The four D2 graph frames plus the audit trail of every claim the extractor considered."""

    entities: pl.DataFrame
    facts: pl.DataFrame
    fact_support: pl.DataFrame
    mentions: pl.DataFrame
    claims: pl.DataFrame

    def hash(self) -> str:
        return content_key(
            "extraction",
            [
                FrameDataset(frame).fingerprint()
                for frame in (
                    self.entities,
                    self.facts,
                    self.fact_support,
                    self.mentions,
                    self.claims,
                )
            ],
        )

    def counts(self) -> dict[str, int]:
        status = dict(self.claims.group_by("status").len().iter_rows())
        return {
            "entities": self.entities.height,
            "facts": self.facts.height,
            "mentions": self.mentions.height,
            **{f"claims_{s}": status.get(s, 0) for s in STATUSES},
        }


# ---- identities ----------------------------------------------------------------------------

_ARTICLE = re.compile(r"^(?:the|a|an) ")
_POSSESSIVE = re.compile(r"(?:'s|’s|')$")
_TRAILING = re.compile(r"[.,;:]+$")


def normalise(surface: str) -> str:
    """The surface form an entity id is built from: NFKC, casefolded, whitespace collapsed,
    leading article, trailing punctuation and trailing possessive stripped. `Bush's` and `the Bush` are one entity
    within a document; `bush` (the plant) is too, which is the price of no disambiguation."""
    s = unicodedata.normalize("NFKC", surface).casefold()
    s = re.sub(r"\s+", " ", s).strip()
    s = _TRAILING.sub("", _ARTICLE.sub("", s)).strip()
    return _POSSESSIVE.sub("", s).strip()


def entity_id(document_id: str, surface: str) -> str:
    """Document-scoped identity: the same name in one document is one entity, in two documents
    two entities until a resolver links them."""
    return content_key("entity", [document_id, normalise(surface)])[:20]


def proposition_id(
    subject: str, predicate: str, object_id: str | None, literal: str | None, datatype: str | None
) -> str:
    """One id per distinct assertion: an entity object and an equal literal never share it."""
    kind = "entity" if object_id is not None else "literal"
    return content_key("proposition", [subject, predicate, kind, object_id or literal, datatype])[
        :20
    ]


def fact_id(extractor: str, chunk_id: int, sent_start: int, sent_end: int, prop: str) -> int:
    """Positive 60-bit id from (extractor, chunk, sentence span, proposition)."""
    return int(content_key("fact", [extractor, chunk_id, sent_start, sent_end, prop])[:15], 16)
