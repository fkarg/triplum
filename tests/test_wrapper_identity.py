"""Identity of decorated functions: wrapper and wrapped both count; scope follows the computation.

Modules are compiled with real-looking file names, so directory-based application scope applies:
`/app/*.py` is the application (a flat script layout), `/venv/lib/*.py` an installed library.
"""

import functools
import sys
from types import FunctionType, ModuleType

import pytest

from triplum.utils.fingerprint import UnsupportedFingerprint, definition_hash

EXTLIB = """
import functools, os

def logged(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        return function(*args, **kwargs)
    return wrapper

def env_logged(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        if os.environ.get("DEBUG"):
            print("call")
        return function(*args, **kwargs)
    return wrapper

def logged_one(function):
    @functools.wraps(function)
    def wrapper(value):
        return function(value)
    return wrapper

def scale(factor):
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args):
            return factor * function(*args)
        return wrapper
    return decorate

def scale_by_default(factor):
    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, by=factor):
            return by * function(*args)
        return wrapper
    return decorate
"""


@pytest.fixture
def load(monkeypatch):
    """Compile `source` as module `name` from file `path`, registered in `sys.modules`."""

    def load(name: str, path: str, source: str) -> ModuleType:
        module = ModuleType(name)
        vars(module)["__file__"] = path
        monkeypatch.setitem(sys.modules, name, module)
        exec(compile(source, path, "exec"), vars(module))  # noqa: S102 - controlled fixture
        return module

    load("extlib", "/venv/lib/extlib.py", EXTLIB)
    return load


def _step(load, helper_body: str, decorator: str = "@extlib.logged"):
    load("helpers", "/app/helpers.py", f"def h(x):\n    return {helper_body}\n")
    source = f"import extlib, helpers\n{decorator}\ndef compute(x):\n    return helpers.h(x)\n"
    return load("step", "/app/step.py", source).compute


def test_a_third_party_decorator_does_not_hide_application_helpers(load):
    # Regression: the decorator's library file set the application directory, so sibling helper
    # modules became external and editing them kept the identity (stale cached results).
    first = definition_hash(_step(load, "x + 1"))
    assert definition_hash(_step(load, "x + 1")) == first
    assert definition_hash(_step(load, "x + 2")) != first


def test_a_helper_edit_misses_a_real_cache_and_a_repeat_hits(load, tmp_path):
    from triplum.cache import Cache, SQLiteBackend

    calls: list[int] = []
    results = []
    for body in ("x + 1", "x + 1", "x + 2"):
        load("helpers", "/app/helpers.py", f"def h(x):\n    return {body}\n")
        with Cache(SQLiteBackend(tmp_path / "c.sqlite")) as cache:
            module = load("cached_step", "/app/cached_step.py", "")
            vars(module).update(cache=cache, calls=calls)
            source = """import extlib, helpers
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel
class Out(FingerprintedDataModel):
    value: int
@cached(cache=cache)
@extlib.logged
def compute(x: int) -> Out:
    calls.append(x)
    return Out(value=helpers.h(x))
"""
            exec(compile(source, "/app/cached_step.py", "exec"), vars(module))  # noqa: S102
            results.append(module.compute(10).value)
    assert results == [11, 11, 12]
    assert calls == [10, 10]  # the unchanged repeat was served from the cache


def test_traced_caching_accepts_an_external_wrapper_with_named_parameters(load, tmp_path):
    # Regression: shallow wrapper projections did not register the wrapper's code, so traced
    # discovery observed an unknown binding and never admitted results.
    from triplum.cache import Cache, SQLiteBackend

    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "t.sqlite")) as cache:
        module = load("traced_step", "/app/traced_step.py", "")
        vars(module).update(cache=cache, calls=calls)
        source = """import extlib
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel
class Value(FingerprintedDataModel):
    text: str
@cached(cache=cache, dependency_mode="traced")
@extlib.logged_one
def compute(value: Value) -> Value:
    calls.append(value.text)
    return Value(text=value.text + "!")
"""
        exec(compile(source, "/app/traced_step.py", "exec"), vars(module))  # noqa: S102
        for _ in range(2):
            assert module.compute(module.Value(text="hi")).text == "hi!"
    assert calls == ["hi"]


def test_an_external_wrapper_reading_the_environment_counts_by_code(load):
    # Regression: copied `__module__` made the library wrapper look like application code, so its
    # `os.environ` read raised instead of the wrapper counting as external.
    first = definition_hash(_step(load, "x + 1", "@extlib.env_logged"))
    assert definition_hash(_step(load, "x + 2", "@extlib.env_logged")) != first


@pytest.mark.parametrize("factory", ["scale", "scale_by_default"])
def test_external_wrapper_arguments_enter_identity(load, factory):
    hashes = {definition_hash(_step(load, "x", f"@extlib.{factory}({n})")) for n in (2, 3)}
    assert len(hashes) == 2


def test_an_outer_wrapper_around_a_cached_function_counts(load):
    # Regression: `functools.wraps` copied triplum's markers onto the outer wrapper, which was then
    # skipped entirely although it changes the result.
    def outer(addend: int) -> FunctionType:
        source = f"""import functools
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel
class Out(FingerprintedDataModel):
    value: int
@cached
def inner(x: int) -> Out:
    return Out(value=x)
@functools.wraps(inner)
def outer(x):
    return Out(value=inner(x).value + {addend})
"""
        return load("outer_app", "/app/outer_app.py", source).outer

    assert definition_hash(outer(100)) != definition_hash(outer(200))


def test_an_application_wrapper_counts_its_external_target(load):
    def wrapped_by_app(body: str) -> FunctionType:
        load("vendor", "/venv/lib/vendor.py", f"def operation(x):\n    return {body}\n")
        source = """import functools, vendor
def mine(function):
    @functools.wraps(function)
    def wrapper(x):
        return function(x) + 1
    return wrapper
operation = mine(vendor.operation)
"""
        return load("app_wraps", "/app/app_wraps.py", source).operation

    assert definition_hash(wrapped_by_app("x * 2")) != definition_hash(wrapped_by_app("x * 3"))


def test_an_application_wrapper_around_an_external_function_counts_its_own_code(load):
    def wrapper_adding(addend: int) -> FunctionType:
        load("vendor", "/venv/lib/vendor.py", "def operation(x):\n    return x\n")
        source = f"""import functools, vendor
@functools.wraps(vendor.operation)
def operation(x):
    return vendor.operation(x) + {addend}
"""
        return load("app_around", "/app/app_around.py", source).operation

    assert definition_hash(wrapper_adding(1)) != definition_hash(wrapper_adding(2))


def test_a_target_reachable_only_through_wrapped_counts(load):
    def wrapper_over(body: str) -> FunctionType:
        source = f"""def target(x):
    return {body}
def wrapper(x):
    return x
wrapper.__wrapped__ = target
"""
        return load("only_wrapped", "/app/only_wrapped.py", source).wrapper

    assert definition_hash(wrapper_over("x + 1")) != definition_hash(wrapper_over("x + 2"))


@pytest.mark.parametrize("cycle", ["self", "pair"])
def test_wrapped_cycles_terminate(load, cycle):
    source = """def f(x):
    return x
def g(x):
    return x
"""
    module = load("cycles", "/app/cycles.py", source)
    if cycle == "self":
        module.f.__wrapped__ = module.f
    else:
        module.f.__wrapped__, module.g.__wrapped__ = module.g, module.f
    assert definition_hash(module.f) == definition_hash(module.f)


def test_a_class_whose_first_method_is_externally_decorated_keeps_its_scope(load):
    def tool(body: str) -> type:
        load("helpers", "/app/helpers.py", f"def h(x):\n    return {body}\n")
        source = """import extlib, helpers
class Tool:
    @extlib.logged
    def first(self, x):
        return x
    def second(self, x):
        return helpers.h(x)
"""
        return load("tools", "/app/tools.py", source).Tool

    assert definition_hash(tool("x + 1")) != definition_hash(tool("x + 2"))


def test_lru_cache_around_an_external_wrapper_still_counts_the_target(load):
    def cached_step(body: str) -> object:
        step = _step(load, body)
        return functools.lru_cache(step)

    assert definition_hash(cached_step("x + 1")) != definition_hash(cached_step("x + 2"))


def test_lru_cache_around_a_triplum_cached_function_unwraps_both(load):
    # Regression: unwrapping stopped at triplum's wrapper under `lru_cache`, which then declined.
    def stacked(body: str) -> object:
        source = f"""import functools
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel
class Out(FingerprintedDataModel):
    value: int
@functools.lru_cache
@cached
def compute(x: int) -> Out:
    return Out(value={body})
"""
        return load("stacked", "/app/stacked.py", source).compute

    assert definition_hash(stacked("x + 1")) != definition_hash(stacked("x + 2"))


def test_unsupported_captures_decline_instead_of_crashing(load):
    class Raising:
        @property
        def fingerprint(self):
            raise RuntimeError("broken descriptor")

    looped: list[object] = []
    looped.append(looped)
    for captured in (looped, Raising()):
        module = load("captures", "/app/captures.py", "")
        vars(module)["value"] = captured
        source = """def make(value):
    def uses():
        return value
    return uses
uses = make(value)
"""
        exec(compile(source, "/app/captures.py", "exec"), vars(module))  # noqa: S102
        with pytest.raises(UnsupportedFingerprint):
            definition_hash(module.uses)


def test_functions_without_a_module_name_keep_their_application_helpers(load):
    # Regression: without `__name__` in its globals a root lost its package, so helpers in another
    # directory of the same package stopped counting.
    def root(body: str) -> FunctionType:
        helpers = load("app.helpers", "/app/pkg/helpers.py", f"def h(x):\n    return {body}\n")
        namespace: dict[str, object] = {"helpers": helpers}
        code = compile("def f(x):\n    return helpers.h(x)\n", "/app/other/root.py", "exec")
        exec(code, namespace)  # noqa: S102 - controlled fixture
        function = namespace["f"]
        assert isinstance(function, FunctionType)
        function.__module__ = "app.root"
        return function

    assert definition_hash(root("x + 1")) != definition_hash(root("x + 2"))


def test_library_functions_decorated_inside_their_library_stay_name_only(load):
    # Regression: application code calling a `warnings.deprecated` library function descended
    # into the decorator's captures (a class) and failed to fingerprint at all.
    load(
        "vlib",
        "/venv/lib/vlib.py",
        "import warnings\n@warnings.deprecated('old')\ndef old(x):\n    return x\n",
    )
    root = load(
        "uses_vlib", "/app/uses_vlib.py", "import vlib\ndef compute(x):\n    return vlib.old(x)\n"
    )
    assert definition_hash(root.compute) == definition_hash(root.compute)


def test_renamed_library_functions_keep_distinct_names(load):
    # Regression: name-only identity used the code's own name, so factory-made functions given
    # different `__qualname__`s collapsed to one identity although they compute differently.
    factory = """def make(name, offset):
    def operation(x):
        return x + offset
    operation.__qualname__ = name
    return operation
"""
    load("vfac", "/venv/lib/vfac.py", factory)

    def root(name: str, offset: int) -> FunctionType:
        source = f"import vfac\nchosen = vfac.make({name!r}, {offset})\ndef compute(x):\n    return chosen(x)\n"
        return load("uses_vfac", "/app/uses_vfac.py", source).compute

    assert definition_hash(root("first", 1)) != definition_hash(root("second", 2))


def test_local_decorator_edits_change_identity(load):
    def decorated(addend: int) -> FunctionType:
        source = f"""import functools
def mine(function):
    @functools.wraps(function)
    def wrapper(x):
        return function(x) + {addend}
    return wrapper
@mine
def compute(x):
    return x
"""
        return load("local_deco", "/app/local_deco.py", source).compute

    assert definition_hash(decorated(1)) != definition_hash(decorated(2))


def test_cycles_through_external_wrappers_and_lru_terminate(load):
    module = load("ext_cycle", "/venv/lib/ext_cycle.py", "def f(x):\n    return x\n")
    module.f.__wrapped__ = module.f
    memo = functools.lru_cache(module.f)
    memo.__wrapped__ = memo  # nothing to unwrap to: declines instead of recursing forever
    app = load("app_cycle", "/app/app_cycle.py", "")
    vars(app).update(f=module.f, memo=memo)
    code = compile(
        "def a(x):\n    return f(x)\ndef b(x):\n    return memo(x)\n", "/app/app_cycle.py", "exec"
    )
    exec(code, vars(app))  # noqa: S102 - controlled fixture
    assert definition_hash(app.a) == definition_hash(app.a)
    with pytest.raises(UnsupportedFingerprint):
        definition_hash(app.b)
