from pathlib import Path
from uuid import UUID, uuid7

from pydantic import BaseModel, Field, computed_field

from triplum.utils.cache import content_key


class Chunk(BaseModel):
    """A contiguous excerpt of a source's text.

    `source_id` and `start` locate the excerpt in its source: `text` equals
    `source.text[start : start + len(text)]` for the source with that `id`.

    Examples:
        >>> Chunk(source_id=source.id, origin=source.origin, start=1000, text="...")
    """

    id: UUID = Field(
        default_factory=uuid7,
        description="Storage identity of this record: a time-ordered UUIDv7, not derived from content.",
    )
    source_id: UUID = Field(description="The `id` of the source this chunk was taken from.")
    origin: Path | str = Field(
        description="The `origin` of the source this chunk was taken from.",
        examples=[Path("notes/intro.md"), "https://example.org/page"],
    )
    start: int = Field(
        ge=0,
        description="Python character offset (code points, not bytes) of `text` in the source text.",
    )
    text: str = Field(description="The excerpt, verbatim from the source text.")

    @computed_field
    @property
    def fingerprint(self) -> str:
        """Content hash of `origin`, `start` and `text`; independent of `id` and `source_id`."""
        return content_key("chunk", [str(self.origin), self.start, self.text])
