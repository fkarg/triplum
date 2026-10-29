from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from triplum.datatype import ids
from triplum.utils.cache import content_key


class Chunk(BaseModel):
    """A contiguous excerpt of a source's text.

    `source_id` and `start` locate the excerpt in its source: `text` equals
    `source.text[start : start + len(text)]` for the source with that `id`. `ordinal` is the
    chunk's position in the list its chunker returned for that source.

    Chunks are immutable. Their `id` is derived from `collection_id`, `source_id`, `ordinal`,
    `start` and `text`; the chunker that produced them does not enter it. To change a field,
    construct a new chunk; `model_copy(update=...)` skips validation and would keep a stale id.

    Examples:
        >>> Chunk(
        ...     collection_id=source.collection_id,
        ...     source_id=source.id,
        ...     origin=source.origin,
        ...     ordinal=1,
        ...     start=1000,
        ...     text="...",
        ... )
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(
        default=ids.UNSET,
        description="Deterministic UUIDv8 of `collection_id`, `source_id`, `ordinal`, `start` and `text`; derived when omitted, checked when supplied.",
    )
    collection_id: UUID = Field(
        description="The collection of the source this chunk was taken from."
    )
    source_id: UUID = Field(description="The `id` of the source this chunk was taken from.")
    origin: str = Field(
        description="The `origin` of the source this chunk was taken from.",
        examples=["notes/intro.md", "https://example.org/page"],
    )
    ordinal: int = Field(
        ge=0,
        le=ids.MAX_ORDINAL,
        description="Position in the chunker's result for this source, counting from 0.",
    )
    start: int = Field(
        ge=0,
        description="Python character offset (code points, not bytes) of `text` in the source text.",
    )
    text: str = Field(description="The excerpt, verbatim from the source text.")

    @model_validator(mode="after")
    def _derive_id(self) -> Self:
        derived = ids.chunk_id(
            self.collection_id, self.source_id, self.ordinal, self.start, self.text
        )
        ids.attach(self, derived)
        return self

    def fingerprint(self) -> str:
        """Content hash of the same inputs as `id`: collection, source, ordinal, start and text."""
        return content_key(
            "chunk",
            [str(self.collection_id), str(self.source_id), self.ordinal, self.start, self.text],
        )
