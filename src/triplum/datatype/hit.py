from pydantic import BaseModel, ConfigDict, Field

from triplum.datatype.chunk import Chunk


class RetrievalHit(BaseModel):
    """One retrieved chunk. A list of hits is ranked: earlier hits rank higher.

    Scores are comparable only within one result list. Which step produced a hit is recorded by
    the run, not by the hit.
    """

    model_config = ConfigDict(frozen=True)

    chunk: Chunk = Field(description="The retrieved chunk.")
    score: float | None = Field(
        description="The producer's score, higher is better; None where it has none (an oracle)."
    )
