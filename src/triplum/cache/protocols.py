"""Semantic value, storage and serialization boundaries for computation caching."""

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from types import BuiltinFunctionType, FunctionType, MethodType
from typing import Literal, Protocol


class Fingerprintable(Protocol):
    """A semantic SHA-256 hex identity that distinguishes the declared value kind.

    Select identity-bearing fields explicitly. Bookkeeping timestamps, cache resources
    and execution policies do not belong in this digest.
    """

    @abstractmethod
    def fingerprint(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ComputationMetadata:
    """Descriptive provenance, excluded from cache identity; location may be unavailable."""

    name: str
    source_path: str | None = None
    source_line: int | None = None

    @classmethod
    def from_callable(cls, compute: object) -> ComputationMetadata:
        """Describe a callable without reading source files or invoking user code."""
        target = compute.__func__ if isinstance(compute, MethodType) else compute
        if isinstance(target, (FunctionType, BuiltinFunctionType)):
            name = f"{target.__module__}.{target.__qualname__}"
        else:
            name = f"{type(target).__module__}.{type(target).__qualname__}"
        if isinstance(target, FunctionType) and not target.__code__.co_filename.startswith("<"):
            return cls(name, target.__code__.co_filename, target.__code__.co_firstlineno)
        return cls(name)


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Full computation namespace and input data identity."""

    process: bytes
    input: bytes
    metadata: ComputationMetadata | None = field(default=None, compare=False, hash=False)

    def __post_init__(self) -> None:
        if len(self.process) != 32 or len(self.input) != 32:
            raise ValueError("cache key digests must contain exactly 32 bytes")


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Admission policy when accepted writes exhaust the pending-byte budget."""

    on_full: Literal["skip", "block"] = "skip"

    def __post_init__(self) -> None:
        if self.on_full not in ("skip", "block"):
            raise ValueError("on_full must be 'skip' or 'block'")


class Codec[T: Fingerprintable](Protocol):
    """Serialize a value without changing its semantic content or fingerprint."""

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
