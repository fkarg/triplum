from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from triplum.datatype import ids
from triplum.utils.cache import content_key


class Source(BaseModel):
    """Identified input text, as handed to chunking.

    A source is the output of upstream loading and preprocessing (file reading, OCR, HTML
    extraction, message history, ...) and the unit that chunks refer back to.
    It holds the full text in memory.

    Sources are immutable. Their `id` is derived from `collection_id`, `origin` and `text`, so an
    equal source in the same collection always gets the same id. To change a field, construct a
    new source; `model_copy(update=...)` skips validation and would keep a stale id.

    Examples:
        >>> Source(collection_id=collection.id, origin="notes/intro.md", text="# Intro\\n...")
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(
        default=ids.UNSET,
        description="Deterministic UUIDv8 of `collection_id`, `origin` and `text`; derived when omitted, checked when supplied.",
    )
    collection_id: UUID = Field(description="The collection this source belongs to.")
    origin: str = Field(
        description="External Source Identifier: where does the text came from? can be a file path, URL or other identifier.",
        examples=["notes/intro.md", "https://example.org/page"],
    )
    text: str = Field(
        description="The full source text. May be empty; chunking then produces no chunks. Used as basis for full-text-search and further processing such as chunking or knowledge graph construction.",
    )

    @model_validator(mode="after")
    def _derive_id(self) -> Self:
        derived = ids.source_id(self.collection_id, self.origin, self.text)
        ids.attach(self, derived)
        return self

    def fingerprint(self) -> str:
        """Content hash of `collection_id`, `origin` and `text`: the same inputs as `id`."""
        return content_key("source", [str(self.collection_id), self.origin, self.text])
