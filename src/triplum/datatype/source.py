from pathlib import Path

from pydantic import BaseModel, Field


class Source(BaseModel):
    """Identified input text, as handed to chunking.

    A source is the output of upstream loading and preprocessing (file reading, OCR, HTML
    extraction, ...) and the unit that chunks refer back to. It holds the full text in memory.

    Examples:
        >>> Source(origin=Path("notes/intro.md"), text="# Intro\\n...")
    """

    origin: Path | str = Field(
        description="Identifies where the text came from: a file path, or another identifier such as a URL.",
        examples=[Path("notes/intro.md"), "https://example.org/page"],
    )
    text: str = Field(
        description="The full source text. May be empty; chunking then produces no chunks.",
    )
