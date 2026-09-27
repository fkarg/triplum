from pathlib import Path

from pydantic import BaseModel


class Chunk(BaseModel):
    """A source excerpt; start is a Python character offset into the source text."""

    origin: Path | str
    start: int
    text: str
