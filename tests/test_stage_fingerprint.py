"""A function's fingerprint ignores comments, docstrings and formatting and sees every change
that can alter its output; a manifest validates by resolving its entries in the live process."""

import importlib
import linecache
import sys
import textwrap
from pathlib import Path

import polars
import pytest
from triplum.stage import fingerprint as fp

SOURCE = '''
"""Module docstring."""

THRESHOLD = 3
PROMPT = "You answer questions"
TABLE = {"a": 1, "b": [1, 2]}
import logging
LOGGER = logging.getLogger("probe")


def helper(x):
    """A helper."""
    return x + THRESHOLD  # comment


class Thing:
    def method(self, x):
        return helper(x) * 2

    @property
    def prop(self):
        return 1

    @staticmethod
    def stat(x):
        return x

    @classmethod
    def cls(cls, x):
        return x


def outer(x):
    def inner(y):
        return y + 1

    return inner(x)


def uses_logger():
    LOGGER.info(PROMPT)
    return TABLE
'''


@pytest.fixture
def module(tmp_path, monkeypatch):
    """A first-party module on disk that a test can edit and reload."""
    path = tmp_path / "probe_mod.py"
    path.write_text(SOURCE)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)  # a same-size edit in the same
    # second would otherwise be served from a stale .pyc
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("probe_mod", None)
    mod = importlib.import_module("probe_mod")
    yield mod, path
    sys.modules.pop("probe_mod", None)


def rewrite(mod, path: Path, old: str, new: str):
    path.write_text(path.read_text().replace(old, new))
    linecache.checkcache(str(path))
    return importlib.reload(mod)


def test_cosmetic_edits_keep_the_hash_and_semantic_edits_change_it(module):
    mod, path = module
    before = fp.source_hash(mod.helper)
    mod = rewrite(mod, path, "# comment", "# another comment")
    mod = rewrite(mod, path, '"""A helper."""', '"""A different docstring."""')
    mod = rewrite(mod, path, "    return x + THRESHOLD", "    return (x + THRESHOLD)")
    assert fp.source_hash(mod.helper) == before
    mod = rewrite(mod, path, "return (x + THRESHOLD)", "return x - THRESHOLD")
    assert fp.source_hash(mod.helper) != before
    changed = fp.source_hash(mod.helper)
    mod = rewrite(mod, path, "def helper(x):", "def helper(x, y=0):")
    assert fp.source_hash(mod.helper) not in (before, changed)


def test_constants_capture_plain_data_and_skip_objects(module):
    mod, _ = module
    c = fp.constants(mod.uses_logger)
    assert c == {"PROMPT": '"You answer questions"', "TABLE": '{"a":1,"b":[1,2]}'}
    assert fp.constants(mod.helper) == {"THRESHOLD": "3"}


def test_first_party_is_decided_by_path(module):
    mod, _ = module
    assert fp.is_first_party(mod.__file__)
    assert fp.is_first_party(fp.__file__)  # the editable install of the package itself
    assert not fp.is_first_party(polars.__file__)
    assert not fp.is_first_party("<frozen importlib._bootstrap>")
    assert fp.distributions()["polars"] == polars.__version__


def test_resolve_sees_through_descriptors_and_decorators(module):
    mod, _ = module
    assert fp.resolve("probe_mod", "Thing.method") is mod.Thing.method
    assert fp.resolve("probe_mod", "Thing.prop") is mod.Thing.prop.fget
    assert fp.resolve("probe_mod", "Thing.stat") is mod.Thing.__dict__["stat"].__func__
    assert fp.resolve("probe_mod", "Thing.cls") is mod.Thing.__dict__["cls"].__func__
    assert fp.resolve("probe_mod", "outer") is mod.outer
    assert fp.resolve("probe_mod", "nothing") is None
    assert fp.resolve("no_such_module", "f") is None


def test_outer_names_the_containing_function(module):
    mod, _ = module
    inner_code = next(c for c in mod.outer.__code__.co_consts if hasattr(c, "co_qualname"))
    assert inner_code.co_qualname == "outer.<locals>.inner"
    assert fp.outer(inner_code) == "outer"


def test_manifest_validates_until_the_code_changes(module):
    mod, path = module
    codes = {mod.Thing.method.__code__, mod.helper.__code__, polars.DataFrame.__init__.__code__}
    manifest = fp.build(codes)
    assert set(manifest.functions) == {"probe_mod:Thing.method", "probe_mod:helper"}
    assert manifest.constants == {"probe_mod:THRESHOLD": "3"}
    assert manifest.distributions["polars"] == polars.__version__
    assert set(manifest.fixed) == {"triplum._core", "migrations.sql"}
    assert fp.validate(manifest)
    code = manifest.code
    assert fp.build(codes).code == code
    # a constant the helper reads changes: the manifest no longer validates
    mod = rewrite(mod, path, "THRESHOLD = 3", "THRESHOLD = 4")
    assert not fp.validate(manifest)
    # the rebuilt manifest differs only in that constant
    rebuilt = fp.build({mod.Thing.method.__code__, mod.helper.__code__})
    assert rebuilt.functions == manifest.functions and rebuilt.code != code


def test_monkeypatch_and_unresolvable_entries_fail_closed(module):
    mod, _ = module
    manifest = fp.build({mod.helper.__code__})
    assert fp.validate(manifest)
    original = mod.helper
    mod.helper = lambda x: x
    try:
        assert not fp.validate(manifest)
    finally:
        mod.helper = original
    assert fp.validate(manifest)
    orphan = manifest.model_copy(update={"functions": {"probe_mod:gone": "abcd"}})
    assert not fp.validate(orphan)
    stale_dist = manifest.model_copy(
        update={"distributions": {**manifest.distributions, "polars": "0.0.0"}}
    )
    assert not fp.validate(stale_dist)


def test_code_without_source_hashes_its_bytecode():
    code = compile(textwrap.dedent("def f(x):\n    return x * 2\n"), "<probe>", "exec")
    fn_code = next(c for c in code.co_consts if hasattr(c, "co_code"))
    assert fp.source_hash(fn_code).startswith("bytecode:")
    assert not fp.is_first_party("<probe>")


def test_as_plain():
    assert fp.as_plain(("a", 1, None, True)) == (True, ["a", 1, None, True])
    assert fp.as_plain(frozenset({"b", "a"})) == (True, ["a", "b"])
    assert fp.as_plain({"k": b"\x01"}) == (True, {"k": "01"})
    assert fp.as_plain({1: "x"})[0] is False
    assert fp.as_plain(object())[0] is False
    assert fp.as_plain([1, object()])[0] is False
