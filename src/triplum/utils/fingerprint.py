"""Fingerprints of configured objects (steps, embedders, ...) for use in cache keys."""

import ast
import functools
import hashlib
import inspect
import textwrap
from pathlib import Path
from typing import Any, Generic, Protocol

from pydantic import BaseModel

from triplum.utils import content_key


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


def _state(value: Any) -> Any:
    """Return a fingerprintable representation of an attribute value."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_state(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _state(item) for key, item in value.items()}
    if callable(getattr(value, "fingerprint", None)):
        return value.fingerprint()
    raise TypeError(
        f"cannot fingerprint attribute of type {type(value).__qualname__}; "
        "use plain data, a pydantic model, or an object with fingerprint()"
    )


class Fingerprinted(Protocol):
    """Mix in to identify an object by its code and its (attribute) state.

    The default `fingerprint()` hashes the qualified class name, the source of the class and of
    its bases (docstrings and formatting ignored), and every instance attribute. Attributes must
    be plain data, pydantic models, or objects with their own `fingerprint()`; anything else
    raises `TypeError`, so a resource cannot silently drop out of the key. Code the class calls
    into (helper functions, libraries) is not covered; override `fingerprint()` to add it.
    """

    def fingerprint(self) -> str:
        cls = type(self)
        return content_key(
            "object",
            {
                "class": f"{cls.__module__}.{cls.__qualname__}",
                "code": [
                    source_hash(base)
                    for base in cls.__mro__
                    if base not in (object, Protocol, Generic, Fingerprinted)
                ],
                "state": {key: _state(value) for key, value in sorted(vars(self).items())},
            },
        )
