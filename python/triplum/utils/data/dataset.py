"""Small extension points for indexed and streaming sources, with author-defined records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from itertools import islice

from pydantic import BaseModel

from triplum.cache import content_key


class Dataset[T](ABC):
    """An indexed source. Implement length and item access; bulk access is overridable.

    Constructing a dataset need not load its records. No schema, registry, download,
    storage format is required by this class. Identity is supplied by the concrete source.
    """

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __getitem__(self, index: int) -> T: ...

    @abstractmethod
    def fingerprint(self) -> str:
        """Stable identity of logical output, including source revision and transformations.

        Equal identities promise equal ordered records. Names and mutable URLs are insufficient.
        Computing identity must not consume iteration state. Physical batch size is not content.
        """
        ...

    def __getitems__(self, indices: list[int]) -> list[T]:
        """Fetch records in index order; override for efficient bulk reads."""
        return [self[index] for index in indices]

    def __iter__(self) -> Iterator[T]:
        for index in range(len(self)):
            yield self[index]


class IterableDataset[T](ABC):
    """A streaming source. Implement iteration without promising length or random access.

    Replay, ordering and resource ownership are properties of the concrete source.
    A stream may be finite, infinite, replayable or consumable only once.
    """

    @abstractmethod
    def __iter__(self) -> Iterator[T]: ...

    @abstractmethod
    def fingerprint(self) -> str:
        """Identify the logical stream without consuming it; equal identities promise replay.

        Live sources must pin a revision or captured segment before claiming such an identity.
        Deterministically generated infinite sequences may identify their generating parameters.
        Replay means equal logical data, not that a one-shot iterator can be rewound.
        """
        ...


type Source[T] = Dataset[T] | IterableDataset[T]
"""Either base class: what a benchmark part or a selection accepts. The two are not subtypes."""


class Take[T](IterableDataset[T]):
    """The first ``n`` records of a source; the one selection primitive.

    ``n`` is a non-negative integer. ``n == 0`` yields nothing without touching the source;
    otherwise exactly ``n`` records are pulled and never the next one. The length is
    ``min(n, len(source))`` when the source has one. A one-shot source stays one-shot.
    """

    def __init__(self, source: Source[T], n: int) -> None:
        if isinstance(n, bool) or n < 0:
            raise ValueError("n must be a non-negative integer")
        self.source = source
        self.n = n

    def __iter__(self) -> Iterator[T]:
        if self.n == 0:
            return
        yield from islice(self.source, self.n)

    def __len__(self) -> int:
        if self.n == 0:
            return 0
        if not isinstance(self.source, Dataset):
            raise TypeError(f"{type(self.source).__name__} has no length")
        return min(self.n, len(self.source))

    def fingerprint(self) -> str:
        return content_key("take", [self.source.fingerprint(), self.n])


class RecordDataset[T: BaseModel](Dataset[T]):
    """An in-memory sequence of pydantic records, the record analogue of `FrameDataset`.

    Identity is the ordered content, recomputed on every call so an edit to a record's nested
    metadata cannot reuse a stale digest. Records are treated as immutable by convention.
    """

    def __init__(self, records: Sequence[T]) -> None:
        self.records = list(records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> T:
        return self.records[index]

    def __getitems__(self, indices: list[int]) -> list[T]:
        return [self.records[i] for i in indices]

    def fingerprint(self) -> str:
        return content_key("records", [r.model_dump(mode="json") for r in self.records])
