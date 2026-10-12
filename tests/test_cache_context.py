"""Same loaded computations must observe represented context changes between calls."""

from pathlib import Path
from types import FunctionType, ModuleType

import pytest

from triplum.cache import Cache, CachedStep, SQLiteBackend, cached
from triplum.datatype import FingerprintedDataModel
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import (
    FingerprintedComputationMixin,
    _code_identity,
    _instructions,
    definition_hash,
)


class Text(FingerprintedDataModel):
    text: str


def application(source: str, tmp_path: Path, **values: object) -> dict[str, object]:
    namespace: dict[str, object] = {"__name__": "context_application", "Text": Text, **values}
    exec(compile(source, str(tmp_path / "application.py"), "exec"), namespace)  # noqa: S102 - controlled fixture
    return namespace


@pytest.mark.parametrize("owned", [False, True])
def test_description_refreshes_same_decorator_and_reuses_a_after_reopen(
    tmp_path: Path, owned: bool
) -> None:
    # Previously both the wrapper and definition_hash froze A on the first call.
    calls: list[str] = []
    namespace = application(
        "def render(item: Text) -> Text:\n"
        "    calls.append(DESCRIPTION)\n"
        "    return Text(text=DESCRIPTION + item.text)\n",
        tmp_path,
        DESCRIPTION="A",
        calls=calls,
    )
    function = namespace["render"]
    assert isinstance(function, FunctionType)
    path = tmp_path / "context.sqlite"
    for _ in range(2):
        with Cache(SQLiteBackend(path)) as cache:
            operation = cache.cached(function) if owned else cached(function, cache=cache)
            for description in ("A", "B", "A"):
                namespace["DESCRIPTION"] = description
                assert operation(Text(text="x")) == Text(text=description + "x")
            assert calls == ["A", "B"]


def test_global_mapping_refreshes_values_replacement_and_iteration_order(tmp_path: Path) -> None:
    calls: list[str] = []
    settings = {"a": "A", "b": "B"}
    namespace = application(
        "def render(item: Text) -> Text:\n"
        "    calls.append(item.text)\n"
        "    return Text(text=''.join(settings.values()) + item.text)\n",
        tmp_path,
        settings=settings,
        calls=calls,
    )
    function = namespace["render"]
    assert isinstance(function, FunctionType)
    with Cache(SQLiteBackend(tmp_path / "mapping.sqlite")) as cache:
        operation = cached(function, cache=cache)
        assert operation(Text(text="x")) == Text(text="ABx")
        settings["a"] = "C"
        assert operation(Text(text="x")) == Text(text="CBx")
        namespace["settings"] = {"b": "B", "a": "A"}
        assert operation(Text(text="x")) == Text(text="BAx")
        namespace["settings"] = {"a": "A", "b": "B"}
        assert operation(Text(text="x")) == Text(text="ABx")
        assert calls == ["x", "x", "x"]


@pytest.mark.parametrize(
    ("source", "change", "restore"),
    [
        (
            "def operation(value='A'): return value",
            "operation.__defaults__ = ('B',)",
            "operation.__defaults__ = ('A',)",
        ),
        (
            "def operation(*, value='A'): return value",
            "operation.__kwdefaults__['value'] = 'B'",
            "operation.__kwdefaults__ = {'value': 'A'}",
        ),
        (
            "def make():\n    value = 'A'\n    def operation(): return value\n    return operation\noperation = make()",
            "operation.__closure__[0].cell_contents = 'B'",
            "operation.__closure__[0].cell_contents = 'A'",
        ),
        (
            "def helper(): return 'A'\ndef operation(): return helper()\noriginal = helper",
            "def helper(): return 'B'",
            "helper = original",
        ),
        (
            "def operation(): return settings.description",
            "settings.description = 'B'",
            "settings.description = 'A'",
        ),
        (
            (
                "def original(): return 'A'\ndef changed(): return 'B'\n"
                "settings.helper = original\ndef operation(): return settings.helper()"
            ),
            "settings.helper = changed",
            "settings.helper = original",
        ),
        (
            "class Settings:\n    description = 'A'\ndef operation(): return Settings.description",
            "Settings.description = 'B'",
            "Settings.description = 'A'",
        ),
    ],
    ids=[
        "defaults",
        "kwdefaults",
        "closure",
        "helper-binding",
        "module-attribute",
        "module-helper-binding",
        "class-constant",
    ],
)
@pytest.mark.parametrize("configured", [False, True], ids=["definition", "mixin"])
def test_loaded_definition_refreshes_without_replacing_computation(
    tmp_path: Path, source: str, change: str, restore: str, configured: bool
) -> None:
    settings = ModuleType("context_application.settings")
    vars(settings)["description"] = "A"
    namespace = application(
        source + "\nclass Step(FingerprintedComputationMixin):\n"
        "    def fingerprint_config(self): return {}\n"
        "    def __call__(self): return operation()\n",
        tmp_path,
        settings=settings,
        FingerprintedComputationMixin=FingerprintedComputationMixin,
    )
    operation = namespace["operation"]
    assert isinstance(operation, FunctionType)
    step_type = namespace["Step"]
    assert isinstance(step_type, type)
    step = step_type()
    first = step.fingerprint() if configured else definition_hash(operation)
    assert (step.fingerprint() if configured else definition_hash(operation)) == first
    exec(change, namespace)  # noqa: S102 - controlled context mutation
    assert operation() == "B"
    assert (step.fingerprint() if configured else definition_hash(operation)) != first
    exec(restore, namespace)  # noqa: S102 - controlled context restoration
    assert operation() == "A"
    assert (step.fingerprint() if configured else definition_hash(operation)) == first


def test_cached_step_refreshes_helper_globals_with_unchanged_configuration(tmp_path: Path) -> None:
    calls: list[str] = []
    namespace = application(
        "def helper(item):\n"
        "    calls.append(DESCRIPTION)\n"
        "    return Text(text=DESCRIPTION + item.text)\n"
        "class Step(CachedStep):\n"
        "    def fingerprint_config(self): return {}\n"
        "    def compute(self, item): return helper(item)\n",
        tmp_path,
        CachedStep=CachedStep,
        DESCRIPTION="A",
        calls=calls,
    )
    step_type = namespace["Step"]
    assert isinstance(step_type, type)
    for _ in range(2):
        with Cache(SQLiteBackend(tmp_path / "step.sqlite")) as cache:
            step = step_type(cache=cache, output_type=Text)
            first = step.fingerprint()
            for description in ("A", "B", "A"):
                namespace["DESCRIPTION"] = description
                assert step(Text(text="x")) == Text(text=description + "x")
            assert step.fingerprint() == first
            assert calls == ["A", "B"]


@pytest.mark.parametrize("removed", [False, True], ids=["unsupported", "missing"])
def test_changed_unsupported_global_errors_before_reusing_entry(
    tmp_path: Path, removed: bool
) -> None:
    calls: list[str] = []
    namespace = application(
        "def render(item: Text) -> Text:\n"
        "    calls.append(item.text)\n"
        "    return Text(text=DESCRIPTION + item.text)\n",
        tmp_path,
        DESCRIPTION="A",
        calls=calls,
    )
    function = namespace["render"]
    assert isinstance(function, FunctionType)
    with Cache(SQLiteBackend(tmp_path / "unsupported.sqlite")) as cache:
        operation = cached(function, cache=cache)
        assert operation(Text(text="x")) == Text(text="Ax")
        if removed:
            del namespace["DESCRIPTION"]
        else:
            namespace["DESCRIPTION"] = object()
        with pytest.raises(TypeError, match="process_id"):
            operation(Text(text="x"))
        assert calls == ["x"]


def test_fresh_identity_excludes_counter_and_log_growth_and_reuses_immutable_code(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    namespace = application(
        "def operation():\n"
        "    global count\n"
        "    count += 1\n"
        "    calls.append(DESCRIPTION)\n"
        "    return DESCRIPTION\n",
        tmp_path,
        DESCRIPTION="A",
        count=0,
        calls=calls,
    )
    operation = namespace["operation"]
    assert isinstance(operation, FunctionType)
    first = definition_hash(operation)
    code_before, instructions_before = _code_identity.cache_info(), _instructions.cache_info()
    assert operation() == "A"
    assert definition_hash(operation) == first
    namespace["DESCRIPTION"] = "B"
    assert definition_hash(operation) != first
    assert _code_identity.cache_info().hits > code_before.hits
    assert _instructions.cache_info().hits > instructions_before.hits
    assert namespace["count"] == 1
    assert calls == ["A"]


def test_fixed_process_identity_keeps_full_control_over_changed_context(tmp_path: Path) -> None:
    calls: list[str] = []
    namespace = application(
        "def render(item: Text) -> Text:\n"
        "    calls.append(item.text)\n"
        "    return Text(text=DESCRIPTION + item.text)\n",
        tmp_path,
        DESCRIPTION="A",
        calls=calls,
    )
    function = namespace["render"]
    assert isinstance(function, FunctionType)
    with Cache(SQLiteBackend(tmp_path / "override.sqlite")) as cache:
        operation = cached(function, cache=cache, process_id=content_key("explicit", {}))
        assert operation(Text(text="x")) == Text(text="Ax")
        namespace["DESCRIPTION"] = object()
        assert operation(Text(text="x")) == Text(text="Ax")
        assert calls == ["x"]


def test_custom_step_fingerprint_keeps_full_control_over_changed_context(tmp_path: Path) -> None:
    calls: list[str] = []
    namespace = application(
        "class Step(CachedStep):\n"
        "    def fingerprint(self): return process_id\n"
        "    def compute(self, item):\n"
        "        calls.append(item.text)\n"
        "        return Text(text=DESCRIPTION + item.text)\n",
        tmp_path,
        CachedStep=CachedStep,
        DESCRIPTION="A",
        process_id=content_key("explicit-step", {}),
        calls=calls,
    )
    step_type = namespace["Step"]
    assert isinstance(step_type, type)
    with Cache(SQLiteBackend(tmp_path / "custom-step.sqlite")) as cache:
        step = step_type(cache=cache, output_type=Text)
        assert step(Text(text="x")) == Text(text="Ax")
        namespace["DESCRIPTION"] = object()
        assert step(Text(text="x")) == Text(text="Ax")
        assert calls == ["x"]


def test_static_step_identity_preparation_is_hidden_from_enclosing_trace(tmp_path: Path) -> None:
    from triplum.cache.tracing import _Scope
    from triplum.utils.fingerprint import _Definitions

    namespace = application(
        "def identity_settings(): return {}\n"
        "class Step(CachedStep):\n"
        "    def fingerprint_config(self): return identity_settings()\n"
        "    def compute(self, item): return Text(text=item.text.upper())\n"
        "def parent(item): return step(item)\n",
        tmp_path,
        CachedStep=CachedStep,
    )
    step_type = namespace["Step"]
    parent, identity_settings = namespace["parent"], namespace["identity_settings"]
    assert isinstance(step_type, type)
    assert isinstance(parent, FunctionType)
    assert isinstance(identity_settings, FunctionType)
    config, compute = vars(step_type)["fingerprint_config"], vars(step_type)["compute"]
    assert isinstance(config, FunctionType)
    assert isinstance(compute, FunctionType)
    with Cache(SQLiteBackend(tmp_path / "suspended-step.sqlite")) as cache:
        namespace["step"] = step_type(cache=cache, output_type=Text)
        for text in ("first", "second"):
            with _Scope(_Definitions(parent), namespace, {}) as scope:
                assert parent(Text(text=text)) == Text(text=text.upper())
            observed = {record[0] for record in scope.records.values()}
            assert compute.__code__ in observed
            assert config.__code__ not in observed
            assert identity_settings.__code__ not in observed
