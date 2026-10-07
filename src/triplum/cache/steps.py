"""Decorator and compute-hook mixin sharing one optional cache path."""

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import wraps

from triplum.cache.codecs import PydanticCodec
from triplum.cache.protocols import CacheKey, CachePolicy, Codec, Fingerprintable
from triplum.cache.runtime import Cache


def _digest(value: str) -> bytes:
    if re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("fingerprint must be a 64-character SHA-256 hex digest")
    return bytes.fromhex(value)


def _call[I: Fingerprintable, O: Fingerprintable](
    cache: Cache,
    process: bytes,
    item: I,
    compute: Callable[[I], O],
    codec: Codec[O],
    policy: CachePolicy | None,
) -> O:
    key = CacheKey(process, _digest(item.fingerprint()), codec.format_id)
    payload = cache.get(key)
    if payload is not None:
        return codec.decode(payload)
    result = compute(item)
    cache.put(key, codec.encode(result), policy=policy)
    return result


def cached[I: Fingerprintable, O: Fingerprintable](
    *,
    cache: Cache | None,
    process_id: str,
    output_type: type[O],
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
) -> Callable[[Callable[[I], O]], Callable[[I], O]]:
    """Cache a one-input function/bound callable with Pydantic serialization by default.

    process_id must identify computation kind/revision and all effective configuration,
    including relevant model/helper revisions. Equivalent instances share entries;
    pipeline positions, instance IDs and policy must not enter it. Keep computation
    configuration fixed while bound. A custom codec supports other fingerprintable
    output types. cache=None bypasses fingerprints, serialization and lookup entirely.
    """
    process = _digest(process_id) if cache is not None else b""
    selected = (
        (PydanticCodec(output_type) if codec is None else codec) if cache is not None else None
    )

    def decorate(compute: Callable[[I], O]) -> Callable[[I], O]:
        if cache is None or selected is None:
            return compute

        @wraps(compute)
        def call(item: I, /) -> O:
            return _call(cache, process, item, compute, selected, policy)

        return call

    return decorate


class CachedStep[I: Fingerprintable, O: Fingerprintable](ABC):
    """Opt-in cache mixin: implement compute and a semantic computation fingerprint.

    Put this before domain Protocol bases. fingerprint must include a computation kind
    and revision plus effective configuration; exclude cache/codec/policy resources.
    The method is read on each enabled call, so immutable configs can precompute it.
    This step borrows the cache and never closes it. Ordinary uncached steps need not
    inherit anything here.
    """

    def __init__(
        self,
        *,
        cache: Cache | None,
        output_type: type[O],
        codec: Codec[O] | None = None,
        policy: CachePolicy | None = None,
    ) -> None:
        self._cache = cache
        self._codec = (
            (PydanticCodec(output_type) if codec is None else codec) if cache is not None else None
        )
        self._policy = policy

    def __call__(self, item: I, /) -> O:
        if self._cache is None or self._codec is None:
            return self.compute(item)
        return _call(
            self._cache, _digest(self.fingerprint()), item, self.compute, self._codec, self._policy
        )

    @abstractmethod
    def fingerprint(self) -> str:
        """Identify this computation and configuration, independently of its cache."""
        ...

    @abstractmethod
    def compute(self, item: I, /) -> O:
        """Execute on a miss or when caching is disabled; do not mutate item."""
        ...
