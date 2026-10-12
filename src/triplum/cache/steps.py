"""Decorator and compute-hook mixin sharing one optional cache path."""

import re
from abc import ABC, abstractmethod
from annotationlib import Format
from collections.abc import Callable
from functools import wraps
from inspect import Parameter, Signature, signature
from threading import Lock
from typing import Literal, get_type_hints, overload

from triplum.cache.codecs import PydanticCodec
from triplum.cache.defaults import default_cache
from triplum.cache.identity import function_fingerprint
from triplum.cache.protocols import (
    CacheKey,
    CachePolicy,
    Codec,
    ComputationMetadata,
    Fingerprintable,
    _DefaultCache,
)
from triplum.cache.runtime import Cache
from triplum.datatype.fingerprint import _value
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import _FRAMEWORK_BASES, FingerprintedComputationMixin


def _digest(value: str) -> bytes:
    if re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("fingerprint must be a 64-character SHA-256 hex digest")
    return bytes.fromhex(value)


def _call[O: Fingerprintable](
    cache: Cache,
    process: bytes,
    data_id: bytes,
    compute: Callable[[], O],
    codec: Codec[O],
    policy: CachePolicy | None,
    metadata: ComputationMetadata | None = None,
) -> O:
    from triplum.cache.tracing import suspend_tracing, untraced_hit

    with suspend_tracing():
        key = CacheKey(process, data_id, metadata=metadata)
        payload = cache.get(key)
        if payload is not None:
            untraced_hit()
            return codec.decode(payload)
    result = compute()
    with suspend_tracing():
        cache.put(key, codec.encode(result), policy=policy)
    return result


def _arguments(
    call_signature: Signature, arguments: dict[str, object]
) -> tuple[bytes, dict[str, object]]:
    """Encode bound defaults and direct receiver roles while preserving the legacy key."""
    receivers: dict[str, object] = {}

    def encode(role: str, value: object) -> object:
        fingerprint = getattr(value, "fingerprint", None) if not isinstance(value, type) else None
        if callable(fingerprint):
            digest = _digest(fingerprint())
            receivers[role] = value
            return {"fingerprint": digest.hex()}
        return _value(value)

    parameters = call_signature.parameters
    if len(parameters) == 1:
        name, parameter = next(iter(parameters.items()))
        value = arguments[name]
        if parameter.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            fingerprint = (
                getattr(value, "fingerprint", None) if not isinstance(value, type) else None
            )
            if callable(fingerprint):
                return _digest(fingerprint()), {"input": value}
    encoded_values = {}
    for name, value in arguments.items():
        kind = parameters[name].kind
        if kind is Parameter.VAR_POSITIONAL:
            assert isinstance(value, tuple)
            encoded_values[name] = [
                encode(f"argument:{name}:{index}", item) for index, item in enumerate(value)
            ]
        elif kind is Parameter.VAR_KEYWORD:
            assert isinstance(value, dict)
            encoded_values[name] = [
                [key, encode(f"argument:{name}:{key}", item)] for key, item in value.items()
            ]
        else:
            encoded_values[name] = encode(f"argument:{name}", value)
    return bytes.fromhex(content_key("cached-arguments", encoded_values)), receivers


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
def cached[**P, O: Fingerprintable](
    compute: Callable[P, O],
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
    dependency_mode: Literal["static", "traced"] = "static",
) -> Callable[P, O]: ...


@overload
def cached[**P, O: Fingerprintable](
    compute: None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: None = None,
    codec: None = None,
    policy: CachePolicy | None = None,
    dependency_mode: Literal["static", "traced"] = "static",
) -> Callable[[Callable[P, O]], Callable[P, O]]: ...


@overload
def cached[**P, O: Fingerprintable](
    compute: None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
    dependency_mode: Literal["static", "traced"] = "static",
) -> Callable[[Callable[P, O]], Callable[P, O]]: ...


def cached[**P, O: Fingerprintable](
    compute: Callable[P, O] | None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
    dependency_mode: Literal["static", "traced"] = "static",
) -> Callable[P, O] | Callable[[Callable[P, O]], Callable[P, O]]:
    """Use @cached or @cached(overrides...) for a callable.

    By default the shared cache opens on first use, the return annotation selects a
    Pydantic model. Loaded code, settings and application helpers identify computation
    on first use. Keep definitions and settings fixed afterwards. External libraries,
    files, environment and resource state are outside automatic discovery; project their
    content identities as settings or supply an explicit process_id.
    cache=None bypasses identity, serialization and lookup entirely.
    """
    if dependency_mode not in {"static", "traced"}:
        raise ValueError("dependency_mode must be static or traced")
    process = _digest(process_id) if cache is not None and process_id is not None else None

    def decorate(function: Callable[P, O]) -> Callable[P, O]:
        if cache is None:
            return function
        identity = process
        metadata = ComputationMetadata.from_callable(function)
        selected: Codec[O] | None = None
        lock = Lock()

        @wraps(function)
        def call(*args: P.args, **kwargs: P.kwargs) -> O:
            nonlocal selected, identity
            from triplum.cache.tracing import suspend_tracing, traced_call

            with suspend_tracing():
                effective_signature = signature(function, annotation_format=Format.FORWARDREF)
                bound = effective_signature.bind(*args, **kwargs)
                bound.apply_defaults()
                data_id, receivers = _arguments(effective_signature, bound.arguments)
            if selected is None or (identity is None and dependency_mode == "static"):
                with lock, suspend_tracing():
                    if identity is None and dependency_mode == "static":
                        identity = _digest(function_fingerprint(function))
                    if selected is None:
                        selected = _codec(function, output_type, codec)
            owner = default_cache() if cache is _DefaultCache.SHARED else cache
            if dependency_mode == "traced":
                return traced_call(
                    owner,
                    data_id,
                    function,
                    args,
                    kwargs,
                    receivers,
                    selected,
                    policy,
                    process_id=process_id,
                    metadata=metadata,
                )
            assert identity is not None
            return _call(
                owner,
                identity,
                data_id,
                lambda: function(*args, **kwargs),
                selected,
                policy,
                metadata,
            )

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
        dependency_mode: Literal["static", "traced"] = "static",
    ) -> None:
        if dependency_mode not in {"static", "traced"}:
            raise ValueError("dependency_mode must be static or traced")
        self._dependency_mode = dependency_mode
        self._cache = cache
        self._codec = codec
        self._output_type = output_type
        self._codec_lock = Lock()
        self._policy = policy
        self._computation_metadata = ComputationMetadata.from_callable(self.compute)

    def __call__(self, item: I, /) -> O:
        from triplum.cache.tracing import suspend_tracing, traced_call

        if self._cache is None:
            return self.compute(item)
        if self._codec is None:
            with self._codec_lock, suspend_tracing():
                if self._codec is None:
                    self._codec = _codec(self.compute, self._output_type, None)
        with suspend_tracing():
            data_id = _digest(item.fingerprint())
        owner = default_cache() if self._cache is _DefaultCache.SHARED else self._cache
        if self._dependency_mode == "traced":
            configuration = None
            process_id = None
            if type(self).fingerprint is CachedStep.fingerprint:
                config = self.fingerprint_config()
                if type(config) is not dict:
                    raise TypeError("fingerprint_config() must return a string-keyed dictionary")
                model = self._output_type
                configuration = {
                    "settings": config,
                    "output_type": f"{model.__module__}.{model.__qualname__}" if model else None,
                }
            else:
                process_id = _digest(self.fingerprint()).hex()
            return traced_call(
                owner,
                data_id,
                self.compute,
                (item,),
                {},
                {"input": item},
                self._codec,
                self._policy,
                owner=self,
                configuration=configuration,
                metadata=self._computation_metadata,
                process_id=process_id,
            )
        return _call(
            owner,
            _digest(self.fingerprint()),
            data_id,
            lambda: self.compute(item),
            self._codec,
            self._policy,
            self._computation_metadata,
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
