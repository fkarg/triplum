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
from types import CodeType, FunctionType
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


def _state(value: object, active: set[int], *, ordered: bool = False) -> object:
    """Encode selected settings without arbitrary serialization or type coercion."""
    if isinstance(value, FunctionType):
        return _definition(value, active)
    if isinstance(value, type):
        raise TypeError("captured/configured classes need an explicit fingerprint projection")
    fingerprint = getattr(value, "fingerprint", None)
    if callable(fingerprint):
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
            raise TypeError("fingerprint configuration requires string mapping keys")
        items = value.items() if ordered else sorted(value.items())
        return {"dict": [[key, _state(item, active, ordered=ordered)] for key, item in items]}
    raise TypeError(
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
    raise TypeError(f"unsupported Python constant: {type(value).__qualname__}")


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
    vars(typing)["_proto_hook"],
    vars(typing)["_no_init_or_replace_init"],
}


def _definition(value: object, active: set[int]) -> object:
    if id(value) in active:
        raise TypeError("recursive definition capture requires an explicit fingerprint")
    active.add(id(value))
    try:
        if isinstance(value, FunctionType):
            captures = dict(inspect.getclosurevars(value).nonlocals)
            captures.pop("__class__", None)  # super() is covered by the class ancestry.
            captures.pop("__classdict__", None)  # Python 3.14 annotation namespace.
            return {
                "function": f"{value.__module__}.{value.__qualname__}",
                "code": _constant(value.__code__),
                "defaults": _state(value.__defaults__, active, ordered=True),
                "kwdefaults": _state(value.__kwdefaults__, active, ordered=True),
                "captures": _state(captures, active, ordered=True),
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
                        members[name] = _definition(member, active)
                    elif isinstance(member, (staticmethod, classmethod)):
                        if member.__func__ in _FRAMEWORK_FUNCTIONS:
                            continue
                        members[name] = {
                            type(member).__name__: _definition(member.__func__, active)
                        }
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
                        raise TypeError(
                            f"cannot fingerprint descriptor {base.__qualname__}.{name}; "
                            "supply an explicit fingerprint"
                        )
                bases.append(
                    {"class": f"{base.__module__}.{base.__qualname__}", "members": members}
                )
            return {"class": f"{value.__module__}.{value.__qualname__}", "bases": bases}
        raise TypeError("definition_hash requires a Python function or class")
    finally:
        active.remove(id(value))


@functools.cache
def definition_hash(definition: object) -> str:
    """Hash loaded Python methods, constants, defaults, captures and annotation definitions.

    Includes inherited methods and domain Protocol bodies; excludes exact framework helpers.
    Helpers/globals, mutable class attributes and schemas are not inferred. Declare them
    explicitly. Definitions/captures must remain fixed after the first hash. Filename and
    source positions are ignored; interpreter/compiler upgrades can change the digest.
    """
    return content_key("python-definition", _definition(definition, set()))


class Fingerprinted:
    """Identify a configured computation by loaded definitions and selected settings.

    Implement fingerprint_config, returning {} for stateless computations. Use
    fingerprint_dependencies for external Python definitions or fingerprintable values.
    No instance attributes are implicitly inspected. Override fingerprint for full control.
    """

    def fingerprint_config(self) -> dict[str, object]:
        """Select semantic settings; Paths identify names, not file contents.

        Values support finite scalars, lists/tuples, string-keyed mappings, Paths and
        nested fingerprint() values. Mapping order is irrelevant: select ordered pairs
        explicitly if iteration order affects the computation.
        """
        raise NotImplementedError("implement fingerprint_config() or override fingerprint()")

    def fingerprint_dependencies(self) -> tuple[object, ...]:
        """Select external Python definitions or values with their own fingerprint()."""
        return ()

    def fingerprint(self) -> str:
        """Return a SHA-256 digest; selected configuration is evaluated each time."""
        config = self.fingerprint_config()
        if type(config) is not dict:
            raise TypeError("fingerprint_config() must return a string-keyed dictionary")
        dependencies = []
        for dependency in self.fingerprint_dependencies():
            if isinstance(dependency, (FunctionType, type)):
                dependencies.append({"definition": definition_hash(dependency)})
            else:
                fingerprint = getattr(dependency, "fingerprint", None)
                if not callable(fingerprint):
                    raise TypeError(
                        "fingerprint dependency needs a Python definition or fingerprint()"
                    )
                dependencies.append({"fingerprint": fingerprint()})
        return content_key(
            "configured-computation",
            {
                "definition": definition_hash(type(self)),
                "config": _state(config, set()),
                "dependencies": dependencies,
            },
        )


_FRAMEWORK_BASES.add(Fingerprinted)
