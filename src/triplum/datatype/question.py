from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class QuestionInput(BaseModel):
    """What a retriever or reader may see of a question. Gold never appears here."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(description="The question as posed.")


class SpanEvidence(BaseModel):
    """Characters `[start, end)` of one corpus document's text are needed to answer.

    Unknown fields are rejected: otherwise an invalid span would validate as `DocumentEvidence`
    inside the `Evidence` union and silently lose its offsets.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: str = Field(description="The benchmark's native key of the document.")
    start: int = Field(ge=0, description="Character offset of the first evidence character.")
    end: int = Field(description="Character offset after the last evidence character.")

    @model_validator(mode="after")
    def _nonempty(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"span [{self.start}, {self.end}) is empty")
        return self


class DocumentEvidence(BaseModel):
    """The document as a whole is the evidence (page-level provenance, e.g. FRAMES URLs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: str = Field(description="The benchmark's native key of the document.")


type Evidence = SpanEvidence | DocumentEvidence


class QAQuestion(BaseModel):
    """One benchmark question: the public `input` plus everything only evaluation may read.

    Answering steps receive `input` only. `evidence` lists alternative evidence sets; a set is
    satisfied when all its items are, and `[]` means the question has no gold evidence. Offsets
    index the document's `Source.text` as yielded by the same benchmark's corpus.

    Fields cannot be reassigned; nested lists and metadata are immutable by convention.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The benchmark's native question id; the sample key across runs.")
    input: QuestionInput
    answers: list[str] = Field(description="Accepted answers, canonical first.")
    evidence: list[list[Evidence]] = Field(
        description="Alternative evidence sets, each nonempty; `[]` without gold."
    )
    answerable: bool
    metadata: dict[str, JsonValue] = Field(
        default={}, description="Native extras; may contain gold, never shown to answering steps."
    )

    @model_validator(mode="after")
    def _nonempty_sets(self) -> Self:
        if any(not alternative for alternative in self.evidence):
            raise ValueError("an empty evidence set would be satisfied by retrieving nothing")
        return self
