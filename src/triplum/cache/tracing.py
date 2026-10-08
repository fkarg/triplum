"""Bounded runtime dependency discovery and content-addressed traced cache entries."""

import inspect
import sys
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock, get_ident
from types import CodeType, FunctionType, GetSetDescriptorType, MethodType, ModuleType

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from triplum.cache.protocols import (
    CacheKey,
    CachePolicy,
    Codec,
    ComputationMetadata,
    Fingerprintable,
)
from triplum.cache.runtime import Cache
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import (
    UnsupportedFingerprint,
    _captures,
    _Definitions,
    _instructions,
    _snapshot,
    _state,
)


class _Locator(BaseModel):
    model_config = ConfigDict(frozen=True)
    module: str
    qualname: str
    receiver: str | None = None


_INDEX = TypeAdapter(list[list[_Locator]])
_TOOL_ID = 4
_LOCK = Lock()
_ACTIVE: dict[int, list[_Scope]] = {}
_SUSPENDED: dict[int, int] = {}


def _receiver_namespace(receiver: object) -> dict[str, object] | None:
    classes = type(receiver).__mro__
    getter = next(
        (vars(base)["__getattribute__"] for base in classes if "__getattribute__" in vars(base)),
        None,
    )
    if getter is not object.__getattribute__:
        return None
    dictionary = inspect.getattr_static(receiver, "__dict__", None)
    if dictionary is None:
        return {}
    if not isinstance(dictionary, GetSetDescriptorType):
        return None
    values = dictionary.__get__(receiver, type(receiver))
    if not isinstance(values, dict) or any(callable(value) for value in values.values()):
        return None
    return values


def _resolve(
    locator: _Locator, namespace: dict[str, object], receivers: dict[str, object] | None = None
) -> FunctionType | None:
    if locator.receiver is not None:
        receiver = (receivers or {}).get(locator.receiver)
        if receiver is None:
            return None
        slot = locator.qualname.rsplit(".", 1)[-1]
        classes = type(receiver).__mro__
        dictionary = _receiver_namespace(receiver)
        if dictionary is None or slot in dictionary:
            return None
        for base in classes:
            member = vars(base).get(slot)
            if member is not None:
                if not isinstance(member, FunctionType):
                    return None
                owner_name = member.__qualname__.rpartition(".")[0]
                if not any(
                    base.__qualname__ == owner_name and base.__module__ == member.__module__
                    for base in classes
                ):
                    return None
                aliases = {
                    name
                    for base in classes
                    for name, value in vars(base).items()
                    if value is member
                }
                return member if aliases == {slot} else None
        return None
    if "<locals>" in locator.qualname:
        return None
    module = sys.modules.get(locator.module)
    current: object = (
        module
        if module is not None
        else namespace
        if namespace.get("__name__") == locator.module
        else None
    )
    for name in locator.qualname.split("."):
        if isinstance(current, dict):
            current = current.get(name)
        elif isinstance(current, (type, ModuleType)):
            current = vars(current).get(name)
        else:
            return None
        if isinstance(current, (staticmethod, classmethod)):
            current = current.__func__
    return current if isinstance(current, FunctionType) else None


@dataclass(eq=False)
class _Scope:
    context: _Definitions
    namespace: dict[str, object]
    receivers: dict[str, object]
    records: dict[
        tuple[int, int, tuple[tuple[str, int], ...]],
        tuple[CodeType, str, dict[str, object], dict[int, object]],
    ] = field(default_factory=dict)
    extra: set[_Locator] = field(default_factory=set)
    tainted: bool = False
    installed: bool = False

    def __enter__(self):
        with _LOCK:
            if not _ACTIVE:
                try:
                    sys.monitoring.use_tool_id(_TOOL_ID, "triplum-cache")
                except ValueError:
                    return self
                sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_START, _observe)
                sys.monitoring.set_events(_TOOL_ID, sys.monitoring.events.PY_START)
            _ACTIVE.setdefault(get_ident(), []).append(self)
            self.installed = True
        return self

    def __exit__(self, *_exc: object) -> None:
        if not self.installed:
            return
        with _LOCK:
            scopes = _ACTIVE[get_ident()]
            scopes.remove(self)
            if not scopes:
                del _ACTIVE[get_ident()]
            if not _ACTIVE:
                sys.monitoring.set_events(_TOOL_ID, 0)
                sys.monitoring.register_callback(_TOOL_ID, sys.monitoring.events.PY_START, None)
                sys.monitoring.free_tool_id(_TOOL_ID)

    def manifest(self) -> list[_Locator] | None:
        if not self.installed or self.tainted:
            return None
        result = set(self.extra)
        for key, (code, module, namespace, receivers) in self.records.items():
            kind = None
            if receivers:
                if len(receivers) != 1:
                    return None
                receiver = next(iter(receivers.values()))
                kind = next(
                    (key for key, value in self.receivers.items() if value is receiver), None
                )
                if kind is None:
                    return None
                owner_name, _, slot = code.co_qualname.rpartition(".")
                if not any(
                    base.__qualname__ == owner_name and base.__module__ == module
                    for base in type(receiver).__mro__
                ):
                    return None
                matches = {
                    name
                    for base in type(receiver).__mro__
                    for name, value in vars(base).items()
                    if isinstance(value, FunctionType) and value.__code__ is code
                }
                if matches != {slot}:
                    return None
            locator = _Locator(module=module, qualname=code.co_qualname, receiver=kind)
            function = _resolve(locator, namespace, self.receivers)
            if function is None or function.__code__ is not code:
                return None
            try:
                captures = _captures(function)
            except UnsupportedFingerprint:
                return None
            if key[2] != tuple((name, id(captures[name])) for name in code.co_freevars):
                return None
            # A free function installed as a method loses its dispatch-slot identity.
            if receivers and "." not in code.co_qualname:
                return None
            result.add(locator)
        return sorted(result, key=lambda item: (item.module, item.qualname, item.receiver or ""))


def _observe(code: CodeType, _offset: int) -> None:
    # Metadata collection only. No hashing, serialization, imports or cache locks here.
    if _SUSPENDED.get(get_ident(), 0):
        return
    frame = sys._getframe(1)
    namespace = frame.f_globals
    module = namespace.get("__name__", "")
    if not isinstance(module, str) or module.startswith("triplum.cache."):
        return
    binding = (
        id(code),
        id(namespace),
        tuple(
            (name, id(frame.f_locals[name]) if name in frame.f_locals else -1)
            for name in code.co_freevars
        ),
    )
    scopes = _ACTIVE.get(get_ident(), ())
    receiver = None
    if code.co_argcount:
        value = frame.f_locals.get(code.co_varnames[0])
        if value is not None and type(value) not in (str, bytes, int, float, bool, tuple):
            receiver = value
    for group in tuple(_ACTIVE.values()):
        for scope in tuple(group):
            in_application = module.partition(".")[0] == scope.context.package or (
                scope.context.directory is not None
                and code.co_filename.rpartition("/")[0] == str(scope.context.directory)
            )
            if scope not in scopes:
                if in_application:
                    scope.tainted = True
                continue
            if binding in scope.context.codes or not (
                in_application or any(receiver is value for value in scope.receivers.values())
            ):
                continue
            record = scope.records.setdefault(binding, (code, module, namespace, {}))
            if receiver is not None:
                record[3][id(receiver)] = receiver


def _propagate(
    manifest: list[_Locator] | None,
    namespace: dict[str, object] | None = None,
    receivers: dict[str, object] | None = None,
) -> None:
    thread = get_ident()
    for other, scopes in tuple(_ACTIVE.items()):
        if other != thread:
            for scope in tuple(scopes):
                scope.tainted = True
    for scope in tuple(_ACTIVE.get(thread, ())):
        if manifest is None:
            scope.tainted = True
            continue
        for locator in manifest:
            if locator.receiver is None:
                scope.extra.add(locator)
                continue
            receiver = (receivers or {}).get(locator.receiver)
            kind = next((key for key, value in scope.receivers.items() if value is receiver), None)
            if kind is None:
                scope.tainted = True
            else:
                scope.extra.add(locator.model_copy(update={"receiver": kind}))


def _receiver_settings(
    codes: Iterator[CodeType], receiver: object, context: _Definitions
) -> dict[str, object]:
    settings = {}
    for code in codes:
        for instruction in _instructions(code):
            if instruction.opname != "LOAD_ATTR":
                continue
            name = instruction.argval
            for base in type(receiver).__mro__:
                if name not in vars(base):
                    continue
                value = vars(base)[name]
                if isinstance(value, FunctionType):
                    locator = _Locator(
                        module=value.__module__, qualname=value.__qualname__, receiver="value"
                    )
                    if _resolve(locator, {}, {"value": receiver}) is not value:
                        raise UnsupportedFingerprint("receiver method aliases are not supported")
                    break
                settings[name] = _state(value, context)
                break
    return settings


def _current(
    manifest: list[_Locator],
    namespace: dict[str, object],
    receivers: dict[str, object],
    root: _Definitions,
) -> list[dict[str, str]] | None:
    resolved = []
    instrumentation = set(root.instrumentation_mutables)
    semantic = set(root.semantic_mutables)
    for locator in manifest:
        function = _resolve(locator, namespace, receivers)
        if function is None:
            return None
        try:
            identity, context = _snapshot(function)
            if locator.receiver is not None:
                settings = _receiver_settings(
                    iter(context.codes.values()), receivers[locator.receiver], context
                )
                identity = content_key(
                    "receiver-method", {"definition": identity, "settings": settings}
                )
        except UnsupportedFingerprint:
            return None
        instrumentation.update(context.instrumentation_mutables)
        semantic.update(context.semantic_mutables)
        if instrumentation & semantic:
            return None
        resolved.append(
            {"module": locator.module, "qualname": locator.qualname, "identity": identity}
        )
    return resolved


def _traced_call[I: Fingerprintable, O: Fingerprintable](
    cache: Cache,
    item: I,
    compute: Callable[[I], O],
    codec: Codec[O],
    policy: CachePolicy | None,
    *,
    process_id: str | None = None,
    owner: Fingerprintable | None = None,
    configuration: dict[str, object] | None = None,
    metadata: ComputationMetadata | None = None,
) -> O:
    """Validate small manifest templates, then fetch separately addressed result bytes."""
    function = compute.__func__ if isinstance(compute, MethodType) else compute
    if not isinstance(function, FunctionType):
        _propagate(None)
        return compute(item)
    # Input fingerprint errors are caller errors, never unsupported-inference fallback.
    from triplum.cache.steps import _digest

    data_id = _digest(item.fingerprint())
    if _receiver_namespace(item) is None or (
        owner is not None and _receiver_namespace(owner) is None
    ):
        _propagate(None)
        return compute(item)
    try:
        identity, context = _snapshot(type(owner) if owner is not None else function, configuration)
        receiver_settings = {
            "input": _receiver_settings(iter(context.codes.values()), item, context),
            "owner": (
                _receiver_settings(iter(context.codes.values()), owner, context)
                if owner is not None
                else {}
            ),
        }
        identity = content_key(
            "traced-root", {"definition": identity, "receivers": receiver_settings}
        )
    except UnsupportedFingerprint:
        _propagate(None)
        return compute(item)
    root_id = process_id if process_id is not None else identity
    index_id = bytes.fromhex(content_key("traced-index", root_id))
    key = CacheKey(index_id, data_id)
    payload = cache.get(key)
    try:
        templates = _INDEX.validate_json(payload) if payload is not None else []
    except ValidationError:
        templates = []
    namespace = function.__globals__
    receivers: dict[str, object] = {"input": item}
    if owner is not None:
        receivers["owner"] = owner
    for manifest in templates:
        current = _current(manifest, namespace, receivers, context)
        if current is None:
            continue
        process = bytes.fromhex(
            content_key("traced-result", {"root": root_id, "dependencies": current})
        )
        result = cache.get(CacheKey(process, data_id))
        if result is not None:
            _propagate(manifest, namespace, receivers)
            return codec.decode(result)
    with resume_tracing(), _Scope(context, namespace, receivers) as scope:
        result = compute(item)
    manifest = scope.manifest()
    _propagate(manifest, namespace, receivers)
    if manifest is None:
        return result
    current = _current(manifest, namespace, receivers, context)
    if current is None:
        return result
    process = bytes.fromhex(
        content_key("traced-result", {"root": root_id, "dependencies": current})
    )
    if (
        cache.put(
            CacheKey(process, data_id, metadata=metadata), codec.encode(result), policy=policy
        )
        and manifest not in templates
    ):
        templates.append(manifest)
        cache.put(
            CacheKey(index_id, data_id, metadata=metadata),
            _INDEX.dump_json(templates),
            policy=policy,
        )
    return result


@contextmanager
def suspend_tracing() -> Generator[None]:
    thread = get_ident()
    previous = _SUSPENDED.get(thread, 0)
    _SUSPENDED[thread] = previous + 1
    try:
        yield
    finally:
        if previous:
            _SUSPENDED[thread] = previous
        else:
            _SUSPENDED.pop(thread, None)


@contextmanager
def resume_tracing() -> Generator[None]:
    thread = get_ident()
    previous = _SUSPENDED.pop(thread, None)
    try:
        yield
    finally:
        if previous is not None:
            _SUSPENDED[thread] = previous


def untraced_hit() -> None:
    """A static child hit has no runtime manifest; keep its reuse but decline the parent."""
    _propagate(None)


def traced_call[I: Fingerprintable, O: Fingerprintable](
    cache: Cache,
    item: I,
    compute: Callable[[I], O],
    codec: Codec[O],
    policy: CachePolicy | None,
    *,
    process_id: str | None = None,
    owner: Fingerprintable | None = None,
    configuration: dict[str, object] | None = None,
    metadata: ComputationMetadata | None = None,
) -> O:
    with suspend_tracing():
        return _traced_call(
            cache,
            item,
            compute,
            codec,
            policy,
            process_id=process_id,
            owner=owner,
            configuration=configuration,
            metadata=metadata,
        )
