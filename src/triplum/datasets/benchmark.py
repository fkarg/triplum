"""The question-answering benchmark interface: a corpus and the questions over it."""

from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from triplum.datatype import Source
from triplum.datatype.question import QAQuestion
from triplum.utils.data import Dataset


class QABenchmark(Protocol):
    """A corpus and the questions over it, from one source, kept in step.

    Question evidence refers to corpus documents by the benchmark's native document key.
    A question-only benchmark has an empty corpus.
    """

    @abstractmethod
    def corpus(self, collection_id: UUID, /) -> Dataset[Source]:
        """The benchmark's documents as Sources of the collection `collection_id`."""
        ...

    @abstractmethod
    def questions(self) -> Dataset[QAQuestion]:
        """The benchmark's questions, in native order."""
        ...
