"""Optional runtime discovery validates persisted dependencies before serving results."""

import sys
from pathlib import Path
from types import ModuleType

import pytest

from triplum.cache import Cache, SQLiteBackend


def application(cache: Cache, suffix: str, calls: list[str], monkeypatch, *, owned: bool = False):
    module = ModuleType("traced_application")
    vars(module).update(cache=cache, calls=calls)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    source = """from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel
class Value(FingerprintedDataModel):
    text: str
    def render(self):
        calls.append(self.text)
        return self.text + SUFFIX
@cached(cache=cache, dependency_mode="traced")
def operation(value: Value) -> Value:
    return Value(text=value.render())
"""
    if owned:
        source = source.replace(
            '@cached(cache=cache, dependency_mode="traced")',
            '@cache.cached(dependency_mode="traced")',
        )
    vars(module)["SUFFIX"] = suffix
    exec(compile(source, "/application/traced_application.py", "exec"), vars(module))  # noqa: S102 - controlled fixture
    return module


def test_traced_method_changes_reuse_a_b_a_across_reopened_sqlite(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    results = []
    for suffix in ("!", "?", "!"):
        with Cache(SQLiteBackend(tmp_path / "trace.sqlite")) as cache:
            module = application(cache, suffix, calls, monkeypatch)
            results.append(module.operation(module.Value(text="hello")).text)
    assert results == ["hello!", "hello?", "hello!"]
    assert calls == ["hello", "hello"]


@pytest.mark.parametrize("owned", [False, True])
def test_traced_selector_state_is_refreshed_before_lookup(
    tmp_path: Path, monkeypatch, owned: bool
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "trace.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch, owned=owned)
        value = module.Value(text="hello")
        assert module.operation(value).text == "hello!"
        module.SUFFIX = "?"
        assert module.operation(value).text == "hello?"
        module.SUFFIX = "!"
        assert module.operation(value).text == "hello!"
        assert calls == ["hello", "hello"]


def test_unresolvable_runtime_local_method_is_not_cached(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "trace.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)

        def local(self):
            calls.append(self.text)
            return self.text.upper()

        module.Value.render = local
        value = module.Value(text="hello")
        assert module.operation(value).text == "HELLO"
        assert module.operation(value).text == "HELLO"
        assert calls == ["hello", "hello"]


def test_tracing_does_not_hide_user_fingerprint_errors(tmp_path: Path) -> None:
    from triplum.cache import cached
    from triplum.datatype import FingerprintedDataModel

    class Broken(FingerprintedDataModel):
        text: str

        def fingerprint(self) -> str:
            raise TypeError("broken user identity")

    with Cache(SQLiteBackend(tmp_path / "trace.sqlite")) as cache:

        @cached(cache=cache, dependency_mode="traced", output_type=Broken)
        def operation(value: Broken) -> Broken:
            return value

        with pytest.raises(TypeError, match="broken user identity"):
            operation(Broken(text="hello"))


def test_traced_new_dispatch_branch_refreshes_without_redecoration(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "branch.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """MODE = "render"
def alternative(self):
    calls.append("alternative")
    return self.text.upper()
Value.alternative = alternative
@cached(cache=cache, dependency_mode="traced")
def branch(value: Value) -> Value:
    return Value(text=getattr(value, MODE)())
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        item = module.Value(text="hello")
        assert module.branch(item).text == "hello!"
        module.MODE = "alternative"
        assert module.branch(item).text == "HELLO"
        module.MODE = "render"
        assert module.branch(item).text == "hello!"
        assert calls == ["hello", "alternative"]


def test_busy_monitoring_tool_computes_without_admission(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "busy.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        sys.monitoring.use_tool_id(4, "test-owner")
        try:
            for _ in range(2):
                assert module.operation(module.Value(text="hello")).text == "hello!"
            assert sys.monitoring.get_tool(4) == "test-owner"
        finally:
            sys.monitoring.free_tool_id(4)
        assert calls == ["hello", "hello"]
        module.operation(module.Value(text="hello"))
        module.operation(module.Value(text="hello"))
        assert calls == ["hello", "hello", "hello"]


def test_tracer_releases_tool_after_computation_exception(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "exception.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """FAIL = True
@cached(cache=cache, dependency_mode="traced")
def failing(value: Value) -> Value:
    if FAIL:
        raise ValueError("computation failed")
    return Value(text=value.render())
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        with pytest.raises(ValueError, match="computation failed"):
            module.failing(module.Value(text="hello"))
        assert sys.monitoring.get_tool(4) is None
        module.FAIL = False
        assert module.failing(module.Value(text="hello")).text == "hello!"
        assert module.failing(module.Value(text="hello")).text == "hello!"
        assert calls == ["hello"]


def test_static_child_hit_is_reused_but_parent_is_not_admitted(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "child.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """parent_calls = []
@cached(cache=cache)
def child(value: Value) -> Value:
    return Value(text=value.render())
@cached(cache=cache, dependency_mode="traced")
def parent(value: Value) -> Value:
    parent_calls.append(value.text)
    return child(value)
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        module.child(value)
        assert module.parent(value).text == "hello!"
        assert module.parent(value).text == "hello!"
        assert calls == ["hello"]
        assert module.parent_calls == ["hello", "hello"]


def test_traced_child_hit_propagates_input_method_dependencies(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "child-traced.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """parent_calls = []
@cached(cache=cache, dependency_mode="traced")
def parent(value: Value) -> Value:
    parent_calls.append(value.text)
    return operation(value)
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        module.operation(value)
        assert module.parent(value).text == "hello!"
        assert module.parent(value).text == "hello!"
        module.SUFFIX = "?"
        assert module.parent(value).text == "hello?"
        assert calls == ["hello", "hello"]
        assert module.parent_calls == ["hello", "hello"]


def test_instance_method_shadow_never_creates_an_empty_valid_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "shadow.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        value = module.Value(text="hello")
        object.__setattr__(value, "render", lambda: "first")
        assert module.operation(value).text == "first"
        object.__setattr__(value, "render", lambda: "second")
        assert module.operation(value).text == "second"


def test_cross_class_method_alias_is_not_admitted(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "alias.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        original = module.Value.render
        value = module.Value(text="hello")
        assert module.operation(value).text == "hello!"
        exec(  # noqa: S102 - controlled fixture
            compile(
                """class Other(Value):
    def render(self):
        calls.append("other")
        return self.text.upper()
Value.render = Other.render
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        assert module.operation(value).text == "HELLO"
        assert module.operation(value).text == "HELLO"
        module.Value.render = original
        assert module.operation(value).text == "hello!"
        assert calls == ["hello", "other", "other"]


def test_traced_step_invalid_configuration_is_a_user_error(tmp_path: Path) -> None:
    from triplum.cache import CachedStep
    from triplum.datatype import FingerprintedDataModel

    class Value(FingerprintedDataModel):
        text: str

    class Broken(CachedStep[Value, Value]):
        def fingerprint_config(self):
            return []

        def compute(self, value: Value) -> Value:
            return value

    with Cache(SQLiteBackend(tmp_path / "invalid.sqlite")) as cache:
        step = Broken(cache=cache, dependency_mode="traced", output_type=Value)
        with pytest.raises(TypeError, match="fingerprint_config"):
            step(Value(text="hello"))


def test_traced_cache_reuses_across_fresh_interpreters(tmp_path: Path) -> None:
    import subprocess

    script = tmp_path / "application.py"
    script.write_text("""import sys
from triplum.cache import Cache, SQLiteBackend, cached
from triplum.datatype import FingerprintedDataModel
SUFFIX = sys.argv[2]
class Value(FingerprintedDataModel):
    text: str
    def render(self):
        print("COMPUTE")
        return self.text + SUFFIX
with Cache(SQLiteBackend(sys.argv[1])) as cache:
    @cached(cache=cache, dependency_mode="traced")
    def operation(value: Value) -> Value:
        return Value(text=value.render())
    print(operation(Value(text="hello")).text)
""")
    outputs = []
    for suffix in ("!", "?", "!"):
        result = subprocess.run(
            [sys.executable, str(script), str(tmp_path / "process.sqlite"), suffix],
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(result.stdout.splitlines())
    assert outputs == [["COMPUTE", "hello!"], ["COMPUTE", "hello?"], ["hello!"]]


def test_traced_step_live_change_and_fresh_definition_share_identity(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "step.sqlite")) as cache:

        def make(suffix: str):
            module = application(cache, suffix, calls, monkeypatch)
            exec(  # noqa: S102 - controlled fixture
                compile(
                    """from triplum.cache import CachedStep
def helper(value):
    calls.append(value.text)
    return Value(text=value.text + SUFFIX)
class Step(CachedStep[Value, Value]):
    def fingerprint_config(self): return {}
    def compute(self, value: Value) -> Value:
        return helper(value)
""",
                    "/application/traced_application.py",
                    "exec",
                ),
                vars(module),
            )
            return module, module.Step(cache=cache, dependency_mode="traced")

        first, live = make("!")
        live.fingerprint()  # Prime the static identity; traced identity must ignore its snapshot.
        assert live(first.Value(text="hello")).text == "hello!"
        first.SUFFIX = "?"
        assert live(first.Value(text="hello")).text == "hello?"
        fresh, same = make("?")
        assert same(fresh.Value(text="hello")).text == "hello?"
        assert calls == ["hello", "hello"]


def test_delegated_traced_child_does_not_hide_dependencies_from_parent(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "threads.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """from concurrent.futures import ThreadPoolExecutor
@cached(cache=cache, dependency_mode="traced")
def parent(value: Value) -> Value:
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(operation, value).result()
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        assert module.parent(value).text == "hello!"
        module.SUFFIX = "?"
        assert module.parent(value).text == "hello?"
        assert calls == ["hello", "hello"]
        assert sys.monitoring.get_tool(4) is None


def test_delegated_warm_child_hit_does_not_admit_incomplete_parent(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "warm-thread.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """from concurrent.futures import ThreadPoolExecutor
@cached(cache=cache, dependency_mode="traced")
def parent(value: Value) -> Value:
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(operation, value).result()
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        module.operation(value)
        assert module.parent(value).text == "hello!"
        module.SUFFIX = "?"
        assert module.parent(value).text == "hello?"


def test_overlapping_traces_keep_results_isolated_and_release_monitoring(
    tmp_path: Path, monkeypatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    calls: list[str] = []
    barrier = Barrier(2)

    def synchronize():
        barrier.wait()

    with Cache(SQLiteBackend(tmp_path / "parallel.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        module.SYNC = synchronize
        exec(  # noqa: S102 - controlled fixture
            compile(
                """class Value(FingerprintedDataModel):
    text: str
    def render(self):
        SYNC()
        return self.finish()
    def finish(self):
        calls.append(self.text)
        return self.text + SUFFIX
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(module.operation, [module.Value(text="a"), module.Value(text="b")])
            )
        assert [value.text for value in results] == ["a!", "b!"]
        assert sorted(calls) == ["a", "b"]
        assert sys.monitoring.get_tool(4) is None
        module.SYNC = lambda: None
        assert module.operation(module.Value(text="a")).text == "a!"
        assert module.operation(module.Value(text="a")).text == "a!"
        assert calls.count("a") == 2
        assert sys.monitoring.get_tool(4) is None


def test_warm_external_memo_cannot_hide_input_method_dependencies(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "memo.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """from functools import lru_cache
@lru_cache
def memo(text):
    return Value(text=text).render()
@cached(cache=cache, dependency_mode="traced")
def parent(value: Value) -> Value:
    return Value(text=memo(value.text))
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        module.memo("hello")
        assert module.parent(value).text == "hello!"
        module.SUFFIX = "?"
        module.memo.cache_clear()
        assert module.parent(value).text == "hello?"
        assert calls == ["hello", "hello"]


def test_receiver_classvar_change_invalidates_method_result(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "classvar.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """from typing import ClassVar
class Value(FingerprintedDataModel):
    text: str
    SUFFIX: ClassVar[str] = "!"
    def render(self):
        calls.append(self.text)
        return self.text + self.SUFFIX
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        assert module.operation(value).text == "hello!"
        module.Value.SUFFIX = "?"
        assert module.operation(value).text == "hello?"
        module.Value.SUFFIX = "!"
        assert module.operation(value).text == "hello!"
        assert calls == ["hello", "hello"]


def test_mutable_global_store_is_not_admitted_under_post_execution_state(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "state.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """STATE = {"n": 0}
class Value(FingerprintedDataModel):
    text: str
    def render(self):
        STATE["n"] += 1
        return self.text + str(STATE["n"])
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        assert module.operation(value).text == "hello1"
        assert module.operation(value).text == "hello2"


@pytest.mark.parametrize("shared_code", [False, True])
def test_equal_code_objects_with_distinct_globals_are_both_tracked(
    tmp_path: Path, monkeypatch, shared_code: bool
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "equal-code.sqlite")) as cache:
        module = application(cache, "!", [], monkeypatch)
        helpers = []
        source = """from triplum.datatype import FingerprintedDataModel
class Value(FingerprintedDataModel):
    text: str
    def render(self):
        OBSERVED.append(__name__)
        return self.text + SUFFIX
"""
        for name, suffix in (("first", "!"), ("second", "?")):
            helper = ModuleType("traced_application." + name)
            vars(helper).update(SUFFIX=suffix, OBSERVED=calls)
            monkeypatch.setitem(sys.modules, helper.__name__, helper)
            exec(compile(source, "/application/helper.py", "exec"), vars(helper))  # noqa: S102 - controlled fixture
            helpers.append(helper)
        first, second = helpers
        if shared_code:
            second.Value.render.__code__ = first.Value.render.__code__
        module.first_render = first.Value.render
        module.Value = second.Value
        exec(  # noqa: S102 - controlled fixture
            compile(
                """@cached(cache=cache, dependency_mode="traced")
def combined(value: Value) -> Value:
    first_render(value)
    return Value(text=value.render())
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        assert first.Value.render.__code__ == second.Value.render.__code__
        value = module.Value(text="hello")
        assert module.combined(value).text == "hello?"
        vars(second)["SUFFIX"] = "changed"
        assert module.combined(value).text == "hellochanged"
        assert calls == ["traced_application.first", "traced_application.second"] * 2


def test_traced_names_clear_index_and_result_tables(tmp_path: Path, monkeypatch) -> None:
    from triplum.cache import cache_stats, clear_cache

    path = tmp_path / "metadata.sqlite"
    with Cache(SQLiteBackend(path)) as cache:
        module = application(cache, "!", [], monkeypatch)
        module.operation(module.Value(text="hello"))
    rows = cache_stats(path, details=True).computations
    assert len(rows) == 2
    assert {row.name for row in rows} == {"traced_application.operation"}
    assert clear_cache(path, name="traced_application.operation") == 2
    assert cache_stats(path).computations == ()


def test_nonlocal_mutation_cannot_publish_post_execution_identity(
    tmp_path: Path, monkeypatch
) -> None:
    with Cache(SQLiteBackend(tmp_path / "nonlocal.sqlite")) as cache:
        module = application(cache, "!", [], monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """def make():
    n = 0
    class Value(FingerprintedDataModel):
        text: str
        def render(self):
            nonlocal n
            n += 1
            return self.text + str(n)
    return Value
Value = make()
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        assert module.operation(value).text == "hello1"
        assert module.operation(value).text == "hello2"


def test_nested_configured_step_declines_parent_traced_admission(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "nested-config.sqlite")) as cache:
        module = application(cache, "!", calls, monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """from triplum.cache import CachedStep
class Child(CachedStep):
    def fingerprint_config(self):
        return {}
    def compute(self, value: Value) -> Value:
        calls.append(value.text)
        return Value(text=value.text + "!")
class Parent(CachedStep):
    def __init__(self, child, **kwargs):
        super().__init__(**kwargs)
        self.child = child
    def fingerprint_config(self):
        return {"child": self.child}
    def compute(self, value: Value) -> Value:
        return self.child(value)
child = Child(cache=cache, dependency_mode="traced")
parent = Parent(child, cache=cache, dependency_mode="traced")
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        assert module.parent(value).text == "hello!"
        exec(  # noqa: S102 - controlled fixture
            compile(
                """def changed(self, value: Value) -> Value:
    calls.append(value.text)
    return Value(text=value.text + "?")
Child.compute = changed
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        assert module.parent(value).text == "hello?"
        assert calls == ["hello", "hello"]


def test_root_direct_receiver_class_setting_is_refreshed(tmp_path: Path, monkeypatch) -> None:
    with Cache(SQLiteBackend(tmp_path / "root-classvar.sqlite")) as cache:
        module = application(cache, "!", [], monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """from typing import ClassVar
class Value(FingerprintedDataModel):
    text: str
    SUFFIX: ClassVar[str] = "!"
@cached(cache=cache, dependency_mode="traced")
def direct(value: Value) -> Value:
    return Value(text=value.text + value.SUFFIX)
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        value = module.Value(text="hello")
        assert module.direct(value).text == "hello!"
        module.Value.SUFFIX = "?"
        assert module.direct(value).text == "hello?"


@pytest.mark.parametrize(
    "dynamic_reader,nested_state", [(False, False), (True, False), (False, True)]
)
def test_instrumentation_mutation_read_by_helper_declines_admission(
    tmp_path: Path, monkeypatch, dynamic_reader: bool, nested_state: bool
) -> None:
    with Cache(SQLiteBackend(tmp_path / "helper-mutation.sqlite")) as cache:
        module = application(cache, "!", [], monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """STATE = []
def count():
    return str(len(STATE))
class Value(FingerprintedDataModel):
    text: str
    def render(self):
        STATE.append(self.text)
        return count()
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        if dynamic_reader:
            exec(  # noqa: S102 - controlled fixture
                compile(
                    """class Value(FingerprintedDataModel):
    text: str
    def record(self):
        STATE.append(self.text)
    def count(self):
        return str(len(STATE))
    def render(self):
        self.record()
        return self.count()
""",
                    "/application/traced_application.py",
                    "exec",
                ),
                vars(module),
            )
        if nested_state:
            exec(  # noqa: S102 - controlled fixture
                compile(
                    """STATE = {"xs": []}
def count():
    return str(len(STATE["xs"]))
class Value(FingerprintedDataModel):
    text: str
    def render(self):
        STATE["xs"].append(self.text)
        return count()
""",
                    "/application/traced_application.py",
                    "exec",
                ),
                vars(module),
            )
        value = module.Value(text="hello")
        assert [module.operation(value).text for _ in range(3)] == ["1", "2", "3"]


@pytest.mark.parametrize("dynamic_dispatch", [False, True])
def test_shared_code_with_distinct_closures_cannot_hide_receiver_alias(
    tmp_path: Path, monkeypatch, dynamic_dispatch: bool
) -> None:
    with Cache(SQLiteBackend(tmp_path / "closure-alias.sqlite")) as cache:
        module = application(cache, "!", [], monkeypatch)
        exec(  # noqa: S102 - controlled fixture
            compile(
                """def make(suffix):
    def render(value):
        return value.text + suffix
    return render
helper = make("!")
Value.render = make("?")
@cached(cache=cache, dependency_mode="traced")
def operation(value: Value) -> Value:
    helper(value)
    return Value(text=value.render())
""",
                "/application/traced_application.py",
                "exec",
            ),
            vars(module),
        )
        if dynamic_dispatch:
            exec(  # noqa: S102 - controlled fixture
                compile(
                    """@cached(cache=cache, dependency_mode="traced")
def operation(value: Value) -> Value:
    helper(value)
    return Value(text=getattr(value, "render")())
""",
                    "/application/traced_application.py",
                    "exec",
                ),
                vars(module),
            )
        value = module.Value(text="hello")
        assert module.operation(value).text == "hello?"
        module.Value.render = module.make("#")
        assert module.operation(value).text == "hello#"


def test_empty_unused_closure_cell_does_not_break_monitoring(monkeypatch) -> None:
    from triplum.cache.tracing import _Scope
    from triplum.utils.fingerprint import UnsupportedFingerprint, _Definitions, _snapshot

    module = ModuleType("empty_closure_application")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(  # noqa: S102 - controlled fixture
        compile(
            """FLAG = False
def make():
    unused = "unreachable"
    def empty():
        if FLAG:
            return unused
        return "ok"
    del unused
    return empty
empty = make()
empty.__code__ = empty.__code__.replace(co_qualname="empty")
empty.__qualname__ = "empty"
""",
            "/application/empty_closure.py",
            "exec",
        ),
        vars(module),
    )
    with _Scope(_Definitions(module.empty), vars(module), {}) as scope:
        assert module.empty() == "ok"
    assert scope.manifest() is None
    assert sys.monitoring.get_tool(4) is None
    with pytest.raises(UnsupportedFingerprint, match="closure"):
        _snapshot(module.empty)
