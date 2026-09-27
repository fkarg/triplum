from pathlib import Path

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A contiguous excerpt of a source's text.

    `origin` and `start` locate the excerpt in its source: `text` equals
    `source.text[start : start + len(text)]` for the source with the same origin.

    Examples:
        >>> Chunk(origin=Path("notes/intro.md"), start=1000, text="...")
    """

    origin: Path | str = Field(
        description="The `origin` of the source this chunk was taken from.",
        examples=[Path("notes/intro.md"), "https://example.org/page"],
    )
    start: int = Field(
        ge=0,
        description="Python character offset (code points, not bytes) of `text` in the source text.",
    )
    text: str = Field(description="The excerpt, verbatim from the source text.")
