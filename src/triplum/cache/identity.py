"""Default identities for ordinary Python functions; explicit IDs cover dependencies."""

import ast
import inspect
import textwrap
from types import FunctionType

from triplum.utils.cache import content_key


def _state(value: object) -> object:
    if isinstance(value, type):
        raise TypeError("captured classes require an explicit process_id")
    fingerprint = getattr(value, "fingerprint", None)
    if callable(fingerprint):
        return {"fingerprint": fingerprint()}
    if value is None or type(value) in (str, int, float, bool):
        return value
    if type(value) is list:
        return {"list": [_state(item) for item in value]}
    if type(value) is tuple:
        return {"tuple": [_state(item) for item in value]}
    if type(value) is dict and all(type(key) is str for key in value):
        return {"dict": [[key, _state(item)] for key, item in value.items()]}
    raise TypeError("captured configuration needs fingerprint(); supply an explicit process_id")


def function_fingerprint(compute: object) -> str:
    """Identify source, function kind, evaluated defaults and captured configuration.

    Bind once and keep captured configuration immutable. Globals, helper/library
    definitions, files and environment are not tracked: use an explicit process_id
    covering them. Source-less functions and callable objects need explicit identity.
    """
    if not isinstance(compute, FunctionType):
        raise TypeError("automatic identity requires a Python function; supply process_id")
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(compute)))
    except (OSError, TypeError, SyntaxError) as error:
        raise ValueError("function source unavailable or unparseable; supply process_id") from error
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("automatic identity requires a function definition; supply process_id")
    definition = tree.body[0]
    definition.decorator_list = []
    if ast.get_docstring(definition, clean=False) is not None:
        definition.body.pop(0)
    return content_key(
        "python-function",
        {
            "kind": f"{compute.__module__}.{compute.__qualname__}",
            "code": ast.dump(tree),
            "defaults": _state(compute.__defaults__),
            "kwdefaults": _state(compute.__kwdefaults__),
            "captures": _state(inspect.getclosurevars(compute).nonlocals),
        },
    )
