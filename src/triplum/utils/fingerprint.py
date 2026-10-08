"""Fingerprints of configured objects (steps, embedders, ...) for use in cache keys."""

import ast
import dis
import functools
import hashlib
import inspect
import math
import textwrap
import typing
from abc import ABC
from pathlib import Path
from types import BuiltinFunctionType, CodeType, FunctionType, ModuleType
from typing import Generic, Protocol

from triplum.utils.cache import canonical_json, content_key


@functools.cache
def source_hash(cls: type) -> str:
    """Hash of a class's source with comments, formatting and docstrings removed."""
    try:
        source = inspect.getsource(cls)
    except (OSError, TypeError) as error:
        raise TypeError(
            f"cannot fingerprint {cls.__qualname__}: its source is unavailable"
        ) from error
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0]
            is_docstring = (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            )
            if is_docstring:
                node.body = node.body[1:] or [ast.Pass()]
    return hashlib.sha256(ast.dump(tree).encode()).hexdigest()


class UnsupportedFingerprint(TypeError):
    """Automatic inference cannot describe this dependency without guessing."""


def _state(value: object, active: _Definitions, *, ordered: bool = False) -> object:
    """Encode selected settings without arbitrary serialization or type coercion."""
    if active.strict_mutation and type(value) in (list, dict, set):
        active.semantic_mutables.add(id(value))
        if id(value) in active.instrumentation_mutables:
            raise UnsupportedFingerprint("mutated instrumentation is also semantic state")
    if isinstance(value, FunctionType) or _wrapped(value) is not value:
        return _reference(value, active)
    if isinstance(value, ModuleType):
        raise UnsupportedFingerprint("module dependencies require direct static attribute access")
    if isinstance(value, type):
        raise UnsupportedFingerprint(
            "captured/configured classes need an explicit fingerprint projection"
        )
    if active.strict_mutation and isinstance(value, FingerprintedComputationMixin):
        raise UnsupportedFingerprint(
            "nested configured computations require fresh dependency identity"
        )
    fingerprint = getattr(value, "fingerprint", None)
    if callable(fingerprint):
        active.receivers.add(id(value))
        return {"fingerprint": fingerprint()}
    if value is None or type(value) in (str, bool, int):
        return {type(value).__name__: value}
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("fingerprint configuration requires finite floats")
        return {"float": value.hex()}
    if isinstance(value, Path):
        return {"path": str(value)}
    if type(value) is list or type(value) is tuple:
        return {type(value).__name__: [_state(item, active, ordered=ordered) for item in value]}
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise UnsupportedFingerprint("fingerprint configuration requires string mapping keys")
        items = value.items() if ordered else sorted(value.items())
        return {"dict": [[key, _state(item, active, ordered=ordered)] for key, item in items]}
    raise UnsupportedFingerprint(
        f"cannot fingerprint {type(value).__qualname__}; select plain settings or fingerprint()"
    )


def _constant(value: object) -> object:
    """Lossless typed projection of constants emitted by the Python compiler."""
    if isinstance(value, CodeType):
        constants = [_constant(item) for item in value.co_consts]
        # Python may reuse the docstring's constant slot in executable code.
        if value.co_flags & inspect.CO_HAS_DOCSTRING and not any(
            instruction.opcode in dis.hasconst and instruction.arg == 0
            for instruction in dis.get_instructions(value)
        ):
            constants[0] = {"docstring": None}
        return {
            "code": value.co_code.hex(),
            "exceptions": value.co_exceptiontable.hex(),
            "args": [value.co_argcount, value.co_posonlyargcount, value.co_kwonlyargcount],
            "flags": value.co_flags,
            "names": value.co_names,
            "vars": value.co_varnames,
            "free": value.co_freevars,
            "cells": value.co_cellvars,
            "constants": constants,
        }
    if value is None or value is Ellipsis:
        return {type(value).__name__: None}
    if type(value) in (str, bool, int):
        return {type(value).__name__: value}
    if type(value) is float:
        return {"float": value.hex()}
    if type(value) is complex:
        return {"complex": [float(value.real).hex(), float(value.imag).hex()]}
    if type(value) is bytes:
        return {"bytes": value.hex()}
    if type(value) is tuple:
        return {"tuple": [_constant(item) for item in value]}
    if type(value) is frozenset:
        return {"frozenset": sorted((_constant(item) for item in value), key=canonical_json)}
    raise UnsupportedFingerprint(f"unsupported Python constant: {type(value).__qualname__}")


@functools.lru_cache(maxsize=4096)
def _code_identity(code: CodeType) -> str:
    return content_key("python-code", _constant(code))


@functools.lru_cache(maxsize=4096)
def _instructions(code: CodeType) -> tuple[dis.Instruction, ...]:
    return tuple(dis.get_instructions(code))


def _immutable_constant(value: object) -> bool:
    return (
        value is None
        or type(value) in (str, bool, int, float, bytes, complex)
        or (type(value) is tuple or type(value) is frozenset)
        and all(_immutable_constant(item) for item in value)
    )


_FRAMEWORK_BASES: set[type] = {object, ABC, Protocol, Generic}
# typing installs these exact helpers on user-defined Protocols, including concrete ones.
_FRAMEWORK_FUNCTIONS = {
    vars(typing)["_proto_hook"].__func__,
    vars(typing)["_no_init_or_replace_init"],
}


def _wrapped(value: object) -> object:
    # Only documented wrapper metadata stored directly on the object; never descriptors.
    if not isinstance(value, (FunctionType, functools._lru_cache_wrapper)):
        return value
    namespace = vars(value)
    original = namespace.get("_triplum_compute")
    if original is None and not isinstance(value, FunctionType):
        original = namespace.get("__wrapped__")
    return original if isinstance(original, FunctionType) else value


class _Definitions:
    def __init__(self, root: object, *, strict_mutation: bool = False) -> None:
        root = _wrapped(root)
        self.strict_mutation = strict_mutation
        self.receivers: set[int] = set()
        self.instrumentation_mutables: set[int] = set()
        self.semantic_mutables: set[int] = set()
        self.package = getattr(root, "__module__", "").partition(".")[0]
        function = (
            root
            if isinstance(root, FunctionType)
            else next(
                (member for member in vars(root).values() if isinstance(member, FunctionType)), None
            )
        )
        filename = function.__code__.co_filename if function else ""
        self.directory = (
            Path(filename).parent if filename and not filename.startswith("<") else None
        )
        self.visited: dict[int, int] = {}
        self.codes: dict[tuple[int, int, tuple[tuple[str, int], ...]], CodeType] = {}

    def contains(self, function: FunctionType) -> bool:
        return function.__module__.partition(".")[0] == self.package or (
            self.directory is not None
            and not function.__code__.co_filename.startswith("<")
            and Path(function.__code__.co_filename).parent == self.directory
        )


def _codes(code: CodeType):
    yield code
    for value in code.co_consts:
        if isinstance(value, CodeType):
            yield from _codes(value)


def _reference(value: object, active: _Definitions) -> object:
    if active.strict_mutation and isinstance(value, functools._lru_cache_wrapper):
        raise UnsupportedFingerprint("external memoization has no runtime dependency manifest")
    if isinstance(value, FunctionType) and vars(value).get("_triplum_process_id") is not None:
        return {"cached_process": vars(value)["_triplum_process_id"]}
    value = _wrapped(value)
    if isinstance(value, FunctionType):
        if active.contains(value):
            return _definition(value, active)
        return {"external": f"{value.__module__}.{value.__qualname__}"}
    if isinstance(value, (type, BuiltinFunctionType)):
        return {"external": f"{value.__module__}.{value.__qualname__}"}
    return _state(value, active, ordered=True)


_MUTATING_METHODS = {
    "append",
    "extend",
    "insert",
    "pop",
    "clear",
    "remove",
    "update",
    "add",
    "discard",
}
_MISSING = object()


def _discarded_call(block: tuple[dis.Instruction, ...], start: int) -> bool:
    for index in range(start + 2, len(block) - 1):
        operation = block[index].opname
        if operation == "CALL" and block[index + 1].opname == "POP_TOP":
            return True
        if "JUMP" in operation or operation.startswith(("STORE_", "RETURN_")):
            return False
    return False


def _captures(function: FunctionType) -> dict[str, object]:
    try:
        return dict(inspect.getclosurevars(function).nonlocals)
    except ValueError as error:
        raise UnsupportedFingerprint("cannot fingerprint an empty closure cell") from error


def _globals(function: FunctionType, active: _Definitions) -> object:
    references: dict[str, object] = {}
    captures = _captures(function)
    codes = list(_codes(function.__code__))
    instructions = [_instructions(code) for code in codes]
    writes = {
        instruction.argval
        for block in instructions
        for instruction in block
        if instruction.opname in {"STORE_GLOBAL", "DELETE_GLOBAL"}
    }
    stores = any(
        instruction.opname in {"STORE_ATTR", "DELETE_ATTR", "STORE_SUBSCR", "DELETE_SUBSCR"}
        or instruction.opname in {"STORE_DEREF", "DELETE_DEREF"}
        and instruction.argval in captures
        for block in instructions
        for instruction in block
    )
    if active.strict_mutation and (writes or stores):
        raise UnsupportedFingerprint("traced identity does not support semantic global writes")
    # Append-only instrumentation may be skipped; a second semantic read is rejected.
    reads: dict[str, int] = {}
    mutations: dict[str, int] = {}
    instrumentation_sites: set[int] = set()
    for block in instructions:
        for index, instruction in enumerate(block):
            if instruction.opname not in {
                "LOAD_GLOBAL",
                "LOAD_NAME",
                "LOAD_FROM_DICT_OR_GLOBALS",
                "LOAD_DEREF",
            }:
                continue
            name = instruction.argval
            if not isinstance(name, str) or (
                instruction.opname == "LOAD_DEREF" and name not in captures
            ):
                continue
            reads[name] = reads.get(name, 0) + 1
            if (
                index + 1 < len(block)
                and block[index + 1].opname == "LOAD_ATTR"
                and block[index + 1].argval in _MUTATING_METHODS
            ):
                collection = function.__globals__.get(name)
                method = block[index + 1].argval
                append_only = (type(collection) is list and method in {"append", "extend"}) or (
                    type(collection) is set and method == "add"
                )
                if not append_only or not _discarded_call(block, index):
                    raise UnsupportedFingerprint(f"cannot fingerprint mutated global {name}")
                instrumentation_sites.add(id(block[index + 1]))
                if active.strict_mutation:
                    active.instrumentation_mutables.add(id(collection))
                    if id(collection) in active.semantic_mutables:
                        raise UnsupportedFingerprint(
                            "mutated instrumentation is also semantic state"
                        )
                mutations[name] = mutations.get(name, 0) + 1
    if active.strict_mutation and any(
        instruction.opname == "LOAD_ATTR"
        and instruction.argval in _MUTATING_METHODS
        and id(instruction) not in instrumentation_sites
        for block in instructions
        for instruction in block
    ):
        raise UnsupportedFingerprint("traced identity cannot infer indirect mutable state")
    for name, count in mutations.items():
        if reads[name] != count:
            raise UnsupportedFingerprint(
                f"cannot fingerprint mutated global {name}; keep semantic settings immutable"
            )
        writes.add(name)
    for block in instructions:
        for index, instruction in enumerate(block):
            if instruction.opname not in {
                "LOAD_GLOBAL",
                "LOAD_NAME",
                "LOAD_FROM_DICT_OR_GLOBALS",
                "LOAD_DEREF",
            }:
                continue
            name = instruction.argval
            if (
                not isinstance(name, str)
                or name in writes
                or (instruction.opname == "LOAD_DEREF" and name not in captures)
            ):
                continue
            value = (
                captures[name]
                if instruction.opname == "LOAD_DEREF"
                else function.__globals__.get(name, function.__builtins__.get(name, _MISSING))
            )
            path = name
            while (
                isinstance(value, ModuleType)
                and index + 1 < len(block)
                and block[index + 1].opname == "LOAD_ATTR"
            ):
                index += 1
                attribute = block[index].argval
                assert isinstance(attribute, str)
                path += "." + attribute
                value = vars(value).get(attribute, _MISSING)
            if value is _MISSING:
                raise UnsupportedFingerprint(f"cannot resolve computation dependency {path}")
            references[path] = value
    return {name: _reference(value, active) for name, value in sorted(references.items())}


def _definition(value: object, active: _Definitions) -> object:
    value = _wrapped(value)
    if id(value) in active.visited:
        return {"reference": active.visited[id(value)]}
    active.visited[id(value)] = len(active.visited)
    if isinstance(value, FunctionType):
        captures = _captures(value)
        active.codes.update(
            (
                (
                    id(code),
                    id(value.__globals__),
                    tuple(
                        (name, id(captures[name]) if name in captures else -1)
                        for name in code.co_freevars
                    ),
                ),
                code,
            )
            for code in _codes(value.__code__)
        )
        captures.pop("__class__", None)  # super() is covered by the class ancestry.
        captures.pop("__classdict__", None)  # Python 3.14 annotation namespace.
        return {
            "function": f"{value.__module__}.{value.__qualname__}",
            "code": _code_identity(value.__code__),
            "globals": {} if value.__name__ == "__annotate__" else _globals(value, active),
            "defaults": _state(value.__defaults__, active, ordered=True),
            "kwdefaults": _state(value.__kwdefaults__, active, ordered=True),
            "captures": (
                {name: _reference(item, active) for name, item in captures.items()}
                if value.__name__ == "__annotate__"
                else {
                    name: (
                        {"module": item.__name__}
                        if isinstance(item, ModuleType)
                        else _state(item, active, ordered=True)
                    )
                    for name, item in captures.items()
                }
            ),
            "annotations": (
                _definition(value.__annotate__, active) if value.__annotate__ else None
            ),
        }
    if isinstance(value, type):
        bases = []
        for base in value.__mro__:
            if base in _FRAMEWORK_BASES:
                continue
            members = {}
            for name, member in sorted(vars(base).items()):
                # Protocol installs object.__init__ on stateless concrete subclasses.
                if name == "__init__" and member is object.__init__:
                    continue
                if isinstance(member, FunctionType):
                    if member in _FRAMEWORK_FUNCTIONS:
                        continue
                    if name == "__init__" and active.strict_mutation:
                        constructor = _Definitions(member)
                        members[name] = _definition(member, constructor)
                    else:
                        members[name] = _definition(member, active)
                elif isinstance(member, (staticmethod, classmethod)):
                    if member.__func__ in _FRAMEWORK_FUNCTIONS:
                        continue
                    members[name] = {type(member).__name__: _definition(member.__func__, active)}
                elif isinstance(member, property):
                    members[name] = {
                        "property": [
                            _definition(fn, active) if fn else None
                            for fn in (member.fget, member.fset, member.fdel)
                        ]
                    }
                elif not name.startswith("__") and _immutable_constant(member):
                    members[name] = _constant(member)
                elif inspect.ismethoddescriptor(member):
                    raise UnsupportedFingerprint(
                        f"cannot fingerprint descriptor {base.__qualname__}.{name}; "
                        "supply an explicit fingerprint"
                    )
            bases.append({"class": f"{base.__module__}.{base.__qualname__}", "members": members})
        return {"class": f"{value.__module__}.{value.__qualname__}", "bases": bases}
    raise UnsupportedFingerprint("definition_hash requires a Python function or class")


def _snapshot(
    definition: object, configuration: dict[str, object] | None = None
) -> tuple[str, _Definitions]:
    """Refresh definitions and selected dependency state for a traced lookup."""
    context = _Definitions(definition, strict_mutation=True)
    identity = content_key("python-definition", _definition(definition, context))
    if configuration is not None:
        identity = content_key(
            "configured-computation",
            {"definition": identity, "config": _state(configuration, context)},
        )
    return identity, context


@functools.cache
def definition_hash(definition: object) -> str:
    """Hash loaded Python methods, constants, defaults, captures and annotation definitions.

    Includes inherited methods and domain Protocol bodies; excludes exact framework helpers.
    Application helpers and their referenced settings are followed statically. External
    libraries, mutable class attributes and schemas are not inferred. Definitions and
    settings must remain fixed after the first hash. Filename and
    source positions are ignored; interpreter/compiler upgrades can change the digest.
    """
    return content_key("python-definition", _definition(definition, _Definitions(definition)))


class FingerprintedComputationMixin:
    """Identify a configured computation by loaded definitions and selected settings.

    Implement fingerprint_config, returning {} for stateless computations. Referenced
    application helpers contribute automatically; select external content IDs as settings.
    No instance attributes are implicitly inspected. Override fingerprint for full control.
    """

    def fingerprint_config(self) -> dict[str, object]:
        """Select semantic settings; Paths identify names, not file contents.

        Values support finite scalars, lists/tuples, string-keyed mappings, Paths and
        nested fingerprint() values. Mapping order is irrelevant: select ordered pairs
        explicitly if iteration order affects the computation.
        """
        raise NotImplementedError("implement fingerprint_config() or override fingerprint()")

    def fingerprint(self) -> str:
        """Return a SHA-256 digest; selected configuration is evaluated each time."""
        config = self.fingerprint_config()
        if type(config) is not dict:
            raise TypeError("fingerprint_config() must return a string-keyed dictionary")
        return content_key(
            "configured-computation",
            {
                "definition": definition_hash(type(self)),
                "config": _state(config, _Definitions(type(self))),
            },
        )


_FRAMEWORK_BASES.add(FingerprintedComputationMixin)
