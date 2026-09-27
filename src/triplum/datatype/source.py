from pathlib import Path

from pydantic import BaseModel


class Source(BaseModel):
    """Base object for a source of text; origin is a file path or other identifier (e.g. webpage URL)."""

    origin: Path | str
    text: str
