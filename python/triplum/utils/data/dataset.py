"""Small extension points for indexed and streaming sources, with author-defined records."""

from abc import ABC, abstractmethod
from collections.abc import Iterator


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
