"""Decorator and compute-hook mixin sharing one optional cache path."""

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import get_type_hints, overload

from triplum.cache.codecs import PydanticCodec
from triplum.cache.defaults import default_cache
from triplum.cache.identity import function_fingerprint
from triplum.cache.protocols import CacheKey, CachePolicy, Codec, Fingerprintable, _DefaultCache
from triplum.cache.runtime import Cache
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import _FRAMEWORK_BASES, FingerprintedComputationMixin


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
    key = CacheKey(process, _digest(item.fingerprint()))
    payload = cache.get(key)
    if payload is not None:
        return codec.decode(payload)
    result = compute(item)
    cache.put(key, codec.encode(result), policy=policy)
    return result


def _codec[O: Fingerprintable](
    compute: object, output_type: type[O] | None, codec: Codec[O] | None
) -> Codec[O]:
    if codec is not None:
        return codec
    if output_type is not None:
        return PydanticCodec(output_type)
    try:
        model = get_type_hints(compute).get("return")
    except (NameError, TypeError) as error:
        raise TypeError("cannot resolve output annotation; supply output_type or codec") from error
    if not isinstance(model, type):
        raise TypeError("annotate a concrete output model or supply output_type/codec")
    return PydanticCodec[O](model)


@overload
def cached[I: Fingerprintable, O: Fingerprintable](
    compute: Callable[[I], O],
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
) -> Callable[[I], O]: ...


@overload
def cached[I: Fingerprintable, O: Fingerprintable](
    compute: None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
) -> Callable[[Callable[[I], O]], Callable[[I], O]]: ...


def cached[I: Fingerprintable, O: Fingerprintable](
    compute: Callable[[I], O] | None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
) -> Callable[[I], O] | Callable[[Callable[[I], O]], Callable[[I], O]]:
    """Use @cached or @cached(overrides...) for a one-input callable.

    By default the shared cache opens on first use, the return annotation selects a
    Pydantic model. Loaded code, settings and application helpers identify computation
    on first use. Keep definitions and settings fixed afterwards. External libraries,
    files, environment and resource state are outside automatic discovery; project their
    content identities as settings or supply an explicit process_id.
    cache=None bypasses identity, serialization and lookup entirely.
    """
    process = _digest(process_id) if cache is not None and process_id is not None else None

    def decorate(function: Callable[[I], O]) -> Callable[[I], O]:
        if cache is None:
            return function
        identity = process
        selected: Codec[O] | None = None
        lock = Lock()

        @wraps(function)
        def call(item: I, /) -> O:
            nonlocal selected, identity
            if selected is None or identity is None:
                with lock:
                    if identity is None:
                        identity = _digest(function_fingerprint(function))
                    if selected is None:
                        selected = _codec(function, output_type, codec)
            owner = default_cache() if cache is _DefaultCache.SHARED else cache
            return _call(owner, identity, item, function, selected, policy)

        vars(call)["_triplum_compute"] = function
        vars(call)["_triplum_process_id"] = process_id
        return call

    return decorate if compute is None else decorate(compute)


class CachedStep[I: Fingerprintable, O: Fingerprintable](FingerprintedComputationMixin, ABC):
    """Opt-in cache mixin: implement compute and fingerprint_config ({} if stateless).

    Defaults use automatic loaded-definition identity, the shared lazy cache and compute's
    return model annotation. Override fingerprint for full identity control. Override cache,
    output_type, codec or policy independently. Put this before domain Protocol bases.
    Cache/codec/policy resources are excluded. The step borrows its cache, never closes it.
    """

    def __init__(
        self,
        *,
        cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
        output_type: type[O] | None = None,
        codec: Codec[O] | None = None,
        policy: CachePolicy | None = None,
    ) -> None:
        self._cache = cache
        self._codec = codec
        self._output_type = output_type
        self._codec_lock = Lock()
        self._policy = policy

    def __call__(self, item: I, /) -> O:
        if self._cache is None:
            return self.compute(item)
        if self._codec is None:
            with self._codec_lock:
                if self._codec is None:
                    self._codec = _codec(self.compute, self._output_type, None)
        owner = default_cache() if self._cache is _DefaultCache.SHARED else self._cache
        return _call(
            owner, _digest(self.fingerprint()), item, self.compute, self._codec, self._policy
        )

    def fingerprint(self) -> str:
        """Identify definitions/configuration and an explicitly selected output type."""
        model = self._output_type
        return content_key(
            "cached-step",
            {
                "computation": super().fingerprint(),
                "output_type": f"{model.__module__}.{model.__qualname__}" if model else None,
            },
        )

    @abstractmethod
    def compute(self, item: I, /) -> O:
        """Execute on a miss or when caching is disabled; do not mutate item."""
        ...


_FRAMEWORK_BASES.add(CachedStep)
