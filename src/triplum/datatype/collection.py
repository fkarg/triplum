from uuid import UUID, uuid7

from pydantic import BaseModel, Field


class Collection(BaseModel):
    """A named corpus scope for sources and their derived records.

    The name is a human-readable label, not a unique identifier.
    """

    id: UUID = Field(default_factory=uuid7, description="Identity of this collection.")
    name: str = Field(description="Human-readable name of this collection.")
