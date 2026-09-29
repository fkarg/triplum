from uuid import UUID, uuid7

from pydantic import BaseModel, Field, computed_field

from triplum.utils.cache import content_key


class Source(BaseModel):
    """Identified input text, as handed to chunking.

    A source is the output of upstream loading and preprocessing (file reading, OCR, HTML
    extraction, message history, ...) and the unit that chunks refer back to.
    It holds the full text in memory.

    Examples:
        >>> Source(origin="notes/intro.md", text="# Intro\\n...")
    """

    id: UUID = Field(
        default_factory=uuid7,
        description="Storage identity of this record: a time-ordered UUIDv7, not derived from content.",
    )
    origin: str = Field(
        description="External Source Identifier: where does the text came from? can be a file path, URL or other identifier.",
        examples=["notes/intro.md", "https://example.org/page"],
    )
    text: str = Field(
        description="The full source text. May be empty; chunking then produces no chunks. Used as basis for full-text-search and further processing such as chunking or knowledge graph construction.",
    )

    @computed_field
    @property
    def fingerprint(self) -> str:
        """Content hash of `origin` and `text`; equal for records with equal content, whatever their `id`."""
        return content_key("source", [str(self.origin), self.text])
