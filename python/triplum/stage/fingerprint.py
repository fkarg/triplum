"""What code is: which code objects are first-party, what a function's normalised source hashes
to, which module constants it reads, and the manifest that records all of it for a stage.

A manifest is built from the code objects a stage executed (`trace`) and validated later by
resolving every entry in the current process and hashing it again. Any entry that cannot be
resolved is a mismatch: a needless miss is safe, a stale hit is not.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import importlib
import importlib.metadata
import inspect
import linecache
import sys
import sysconfig
import textwrap
from collections.abc import Iterable, Iterator, Mapping
from importlib.resources import files
from pathlib import Path
from types import CodeType, FunctionType, ModuleType
from typing import Any

from pydantic import BaseModel, ConfigDict

from triplum.cache import canonical_json, content_key

SITE = tuple(
    sorted(
        {
            Path(p)
            for k, p in sysconfig.get_paths().items()
            if k in ("purelib", "platlib", "stdlib", "platstdlib")
        }
    )
)
MODULE = "<module>"


def is_first_party(filename: str) -> bool:
    """Source, as opposed to an installed distribution or the standard library, decided by
    path: editable installs and a user's own modules are source. A synthetic filename is
    source only when its lines are registered (notebooks do that); frozen modules are not."""
    if filename.startswith("<"):
        return filename in linecache.cache
    path = Path(filename)
    return not any(path.is_relative_to(site) for site in SITE)


def outer(code: CodeType) -> str:
    """The qualified name of the outermost function or method containing a code object; a
    nested function, lambda or generator expression is recorded under it."""
    return code.co_qualname.split(".<locals>")[0]


def _unwrap(obj: Any) -> Any:
    if isinstance(obj, property):
        obj = obj.fget
    if isinstance(obj, (staticmethod, classmethod)):
        obj = obj.__func__
    try:
        return inspect.unwrap(obj)
    except ValueError:
        return obj


def resolve(module: str, qualname: str) -> FunctionType | ModuleType | None:
    """The function a manifest entry names, in the current process, or the module itself for
    a `<module>` entry. Decorators, properties, static and class methods are seen through.
    None when the module does not import or the name is not a function."""
    mod = sys.modules.get(module)
    if mod is None:
        try:
            mod = importlib.import_module(module)
        except ImportError:
            return None
    if qualname == MODULE:
        return mod
    obj: Any = mod
    for part in qualname.split("."):
        try:
            obj = inspect.getattr_static(obj, part)
        except AttributeError:
            return None
        obj = _unwrap(obj)
    return obj if isinstance(obj, FunctionType) else None


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _bytecode_hash(code: CodeType) -> str:
    h = hashlib.sha256()

    def walk(c: CodeType) -> None:
        h.update(c.co_code)
        h.update(repr(c.co_names).encode())
        for const in c.co_consts:
            if isinstance(const, CodeType):
                walk(const)
            else:
                h.update(repr(const).encode())

    walk(code)
    return "bytecode:" + h.hexdigest()[:16]


def source_hash(obj: FunctionType | CodeType | ModuleType) -> str:
    """The hash of an object's source with comments, whitespace and docstrings removed: the
    AST dump without positions. Falls back to bytecode and constants when no source exists."""
    code = obj.__code__ if isinstance(obj, FunctionType) else obj
    try:
        src = inspect.getsource(code)
    except (OSError, TypeError):
        if isinstance(code, CodeType):
            return _bytecode_hash(code)
        raise
    tree = _strip_docstrings(ast.parse(textwrap.dedent(src)))
    return hashlib.sha256(ast.dump(tree).encode()).hexdigest()[:16]


def as_plain(value: Any) -> tuple[bool, Any]:
    """Whether a value is plain data, and its JSON-ready form: scalars, and tuples, lists,
    sets and dicts of plain data. Anything else (a module, a function, an object) is not."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
        return True, value
    if isinstance(value, bytes):
        return True, value.hex()
    if isinstance(value, (tuple, list)):
        items = [as_plain(v) for v in value]
        return all(ok for ok, _ in items), [v for _, v in items]
    if isinstance(value, (set, frozenset)):
        items = [as_plain(v) for v in value]
        if not all(ok for ok, _ in items):
            return False, None
        return True, sorted((v for _, v in items), key=canonical_json)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                return False, None
            ok, pv = as_plain(v)
            if not ok:
                return False, None
            out[k] = pv
        return True, out
    return False, None


def _names(code: CodeType) -> Iterator[str]:
    yield from code.co_names
    for const in code.co_consts:
        if isinstance(const, CodeType):
            yield from _names(const)


def constants(fn: FunctionType) -> dict[str, str]:
    """The module globals a function reads that are plain data, as canonical JSON, keyed by
    name. Dunder names are skipped (`__file__` would tie a manifest to a machine)."""
    out: dict[str, str] = {}
    for name in sorted(set(_names(fn.__code__))):
        if name.startswith("__") or name not in fn.__globals__:
            continue
        ok, value = as_plain(fn.__globals__[name])
        if ok:
            out[name] = canonical_json(value)
    return out


@functools.cache
def _packages() -> Mapping[str, list[str]]:
    return importlib.metadata.packages_distributions()


def distribution(module: str) -> tuple[str, str] | None:
    """The distribution and version owning an installed module, or None for the standard
    library and for modules no distribution claims."""
    top = module.partition(".")[0]
    if top in sys.stdlib_module_names:
        return None
    dists = _packages().get(top)
    if not dists:
        return None
    name = min(dists)
    try:
        return name, importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


@functools.cache
def fixed_inputs() -> dict[str, str]:
    """The non-Python inputs every manifest carries: the Rust extension and the migrations."""
    from triplum import _core

    out = {}
    if _core.__file__:
        out["triplum._core"] = hashlib.sha256(Path(_core.__file__).read_bytes()).hexdigest()[:16]
    sql = files("triplum.store.sqlite").joinpath("migrations.sql").read_bytes()
    out["migrations.sql"] = hashlib.sha256(sql).hexdigest()[:16]
    return out


class Manifest(BaseModel):
    """What code answered a stage: first-party functions by `module:qualname` with their source
    hashes, the plain-data constants they read by `module:name`, the distributions whose code
    ran with versions, and the fixed inputs. `code` is its content key."""

    model_config = ConfigDict(frozen=True)

    functions: dict[str, str]
    constants: dict[str, str]
    distributions: dict[str, str]
    fixed: dict[str, str]

    @property
    def code(self) -> str:
        return content_key("manifest", self.model_dump())[:16]


def _module_of(filename: str, by_file: dict[str, str]) -> str | None:
    return by_file.get(filename)


def _files_to_modules() -> dict[str, str]:
    out: dict[str, str] = {}
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if f and f not in out:
            out[f] = name
    return out


def build(codes: Iterable[CodeType]) -> Manifest:
    """The manifest for a set of executed code objects. A first-party code object whose module
    cannot be found in `sys.modules` is recorded under its file name and hashed directly, so it
    fails to resolve at validation and the artifact is recomputed."""
    by_file = _files_to_modules()
    functions: dict[str, str] = {}
    consts: dict[str, str] = {}
    dists: dict[str, str] = {}
    for code in codes:
        module = _module_of(code.co_filename, by_file)
        if not is_first_party(code.co_filename):
            if module is not None and (d := distribution(module)) is not None:
                dists[d[0]] = d[1]
            continue
        qual = outer(code)
        if module is None:
            functions[f"{code.co_filename}:{qual}"] = source_hash(code)
            continue
        key = f"{module}:{qual}"
        if key in functions:
            continue
        target = resolve(module, qual)
        if target is None:
            functions[key] = source_hash(code)
            continue
        functions[key] = source_hash(target)
        if isinstance(target, FunctionType):
            for name, value in constants(target).items():
                consts[f"{module}:{name}"] = value
    return Manifest(
        functions=functions, constants=consts, distributions=dists, fixed=fixed_inputs()
    )


def validate(manifest: Manifest) -> bool:
    """Whether the code the manifest names still hashes the same in this process."""
    for key, expected in manifest.functions.items():
        module, _, qual = key.rpartition(":")
        target = resolve(module, qual)
        if target is None or source_hash(target) != expected:
            return False
    for key, expected in manifest.constants.items():
        module, _, name = key.rpartition(":")
        mod = sys.modules.get(module)
        if mod is None or not hasattr(mod, name):
            return False
        ok, value = as_plain(getattr(mod, name))
        if not ok or canonical_json(value) != expected:
            return False
    for dist, version in manifest.distributions.items():
        try:
            if importlib.metadata.version(dist) != version:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return manifest.fixed == fixed_inputs()
