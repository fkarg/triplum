"""Semantic value, storage and serialization boundaries for computation caching."""

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal, Protocol


class Fingerprintable(Protocol):
    """A semantic SHA-256 hex identity, including a value-kind/version tag.

    Select identity-bearing fields explicitly. Bookkeeping timestamps, cache resources
    and execution policies do not belong in this digest.
    """

    @abstractmethod
    def fingerprint(self) -> str: ...


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Full computation and input digests, separated by serialization format."""

    process: bytes
    input: bytes
    format: str

    def __post_init__(self) -> None:
        if len(self.process) != 32 or len(self.input) != 32:
            raise ValueError("cache key digests must contain exactly 32 bytes")
        if not self.format:
            raise ValueError("cache format must not be empty")


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Admission policy when accepted writes exhaust the pending-byte budget."""

    on_full: Literal["skip", "block"] = "skip"

    def __post_init__(self) -> None:
        if self.on_full not in ("skip", "block"):
            raise ValueError("on_full must be 'skip' or 'block'")


class Codec[T: Fingerprintable](Protocol):
    """Serialize a value without changing its semantic content or fingerprint."""

    @property
    @abstractmethod
    def format_id(self) -> str:
        """Stable namespace; change it for incompatible serialization semantics."""
        ...

    @abstractmethod
    def encode(self, value: T, /) -> bytes: ...

    @abstractmethod
    def decode(self, payload: bytes, /) -> T: ...


class CacheBackend(Protocol):
    """Storage supporting concurrent reads and one writer per Cache owner.

    A completed put_many makes all its values visible to subsequent reads. Individual
    values are atomic; an error may leave a partial batch. close follows all calls.
    """

    @abstractmethod
    def get(self, key: CacheKey, /) -> bytes | None: ...

    @abstractmethod
    def put_many(self, entries: Sequence[tuple[CacheKey, bytes]], /) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class _DefaultCache(Enum):
    SHARED = auto()
