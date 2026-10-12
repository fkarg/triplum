"""Public calls preserve Python binding while keying the effective named values."""

from pathlib import Path

import pytest

from triplum.cache import Cache, SQLiteBackend, cached
from triplum.datatype import FingerprintedDataModel
from triplum.utils.cache import content_key


class Value(FingerprintedDataModel):
    text: str


@pytest.mark.parametrize("owned", [False, True])
def test_named_defaults_and_mutation_reopen(tmp_path: Path, owned: bool) -> None:
    calls: list[str] = []
    path = tmp_path / "arguments.sqlite"
    for _ in range(2):
        with Cache(SQLiteBackend(path)) as cache:
            decorate = (
                cache.cached(process_id=content_key("combine", {}))
                if owned
                else cached(cache=cache, process_id=content_key("combine", {}))
            )

            @decorate
            def combine(left: Value, right: str, suffix: str = "!") -> Value:
                calls.append(left.text)
                return Value(text=left.text + right + suffix)

            value = Value(text="a")
            assert combine(value, "b").text == "ab!"
            assert combine(right="b", left=value, suffix="!").text == "ab!"
            value.text = "c"
            assert combine(value, "b", "!").text == "cb!"
            value.text = "a"
            assert combine(value, "b").text == "ab!"
    assert calls == ["a", "c"]


def test_zeroargs_and_variadic_order(tmp_path: Path) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "variadic.sqlite")) as cache:

        @cache.cached(process_id=content_key("empty", {}))
        def empty() -> Value:
            calls.append("empty")
            return Value(text="empty")

        @cache.cached(process_id=content_key("variadic", {}))
        def combine(*items: str, **named: str) -> Value:
            calls.append("combine")
            return Value(text="".join(items) + repr(list(named.items())))

        assert empty() == empty() == Value(text="empty")
        assert combine("a", "b", x="1", y="2") == combine("a", "b", x="1", y="2")
        assert combine("b", "a", x="1", y="2").text == "ba[('x', '1'), ('y', '2')]"
        assert combine("a", "b", y="2", x="1").text == "ab[('y', '2'), ('x', '1')]"
        assert combine("a", "a").text == "aa[]"
        assert combine("a").text == "a[]"
    assert calls == ["empty"] + ["combine"] * 5


def test_invalid_data_and_call_before_lookup(tmp_path: Path) -> None:
    with Cache(SQLiteBackend(tmp_path / "invalid.sqlite")) as cache:

        @cache.cached
        def operation(left: object, right: int) -> Value:
            raise AssertionError("must not execute")

        cache.close()  # Any lookup would raise RuntimeError instead of the caller error.
        with pytest.raises(TypeError):
            operation(1)  # ty: ignore[missing-argument]
        with pytest.raises(TypeError, match="cannot fingerprint"):
            operation(object(), 1)

        class Malformed:
            def fingerprint(self) -> str:
                return "broken"

        with pytest.raises(ValueError, match="64-character"):
            operation(Malformed(), 1)


def test_disabled_returns_original_with_arbitrary_arguments() -> None:
    def original(*args: object, **kwargs: object) -> Value:
        return Value(text=str(len(args) + len(kwargs)))

    assert cached(original, cache=None) is original
    assert cached(original, cache=None)(object(), other=object()).text == "2"


def test_primitive_arguments_swaps_types_and_containers(tmp_path: Path) -> None:
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "values.sqlite")) as cache:

        @cache.cached(process_id=content_key("values", {}))
        def combine(left: object, right: object, /, *, suffix: str = "!") -> Value:
            calls.append("call")
            return Value(text=repr(left) + repr(right) + suffix)

        assert combine(1, "2").text == "1'2'!"
        assert combine("2", 1).text == "'2'1!"
        assert combine(True, "2").text == "True'2'!"
        assert combine(1, "2", suffix="!").text == "1'2'!"
        assert combine([1, 2], (3,)).text == "[1, 2](3,)!"
        assert combine([1, 2], (3,)).text == "[1, 2](3,)!"
    assert calls == ["call"] * 4


def test_public_signature_types_and_keyword_only_defaults(tmp_path: Path) -> None:
    from typing import assert_type

    with Cache(SQLiteBackend(tmp_path / "types.sqlite")) as cache:

        @cached(cache=cache)
        def function(value: int, /, other: str = "x", *, enabled: bool = True) -> Value:
            return Value(text=str(value) + other + str(enabled))

        @cache.cached
        def owned(value: int, *, other: str = "x") -> Value:
            return Value(text=str(value) + other)

        @cache.cached()
        def owned_factory(value: int, *, other: str = "x") -> Value:
            return Value(text=str(value) + other)

        assert_type(function(1, enabled=False), Value)
        assert_type(owned_factory(1, other="y"), Value)
        assert_type(owned(1, other="y"), Value)
        assert function(1).text == "1xTrue"
        assert function(1, "x", enabled=True) == function(1)
        assert owned(value=1).text == "1x"


def test_direct_fingerprints_normalize_hex_in_named_and_variadic_values(tmp_path: Path) -> None:
    class Token:
        def __init__(self, digest: str):
            self.digest = digest

        def fingerprint(self) -> str:
            return self.digest

    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "hex.sqlite")) as cache:

        @cache.cached(process_id=content_key("hex", {}))
        def operation(value: Token, *extra: Token, **named: Token) -> Value:
            calls.append("computed")
            return Value(text="normalized")

        lower, upper = Token("ab" * 32), Token("AB" * 32)
        assert operation(lower, lower, other=lower).text == "normalized"
        assert operation(upper, upper, other=upper).text == "normalized"
        assert calls == ["computed"]
        cache.close()
        with pytest.raises(ValueError, match="64-character"):
            operation(lower, Token("broken"))
        with pytest.raises(ValueError, match="64-character"):
            operation(lower, other=Token("broken"))


@pytest.mark.parametrize("unsupported", [object(), float("nan"), {1: "nonstring"}])
def test_unsupported_values_fail_before_backend(tmp_path: Path, unsupported: object) -> None:
    with Cache(SQLiteBackend(tmp_path / "unsupported.sqlite")) as cache:

        @cache.cached
        def operation(value: object) -> Value:
            raise AssertionError("must not execute")

        cache.close()
        with pytest.raises((TypeError, ValueError)):
            operation(unsupported)


@pytest.mark.parametrize("mode", ["static", "traced"])
def test_type_checking_only_parameter_annotation_does_not_block_binding(
    tmp_path: Path, monkeypatch, mode: str
) -> None:
    # Binding does not require runtime values for parameter-only annotations.
    import sys
    from types import ModuleType

    calls: list[str] = []
    module = ModuleType("annotation_application")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with Cache(SQLiteBackend(tmp_path / "annotations.sqlite")) as cache:
        vars(module).update(cache=cache, mode=mode, calls=calls)
        exec(  # noqa: S102 - controlled application fixture with lazy annotations
            compile(
                """from typing import TYPE_CHECKING
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel
if TYPE_CHECKING:
    from datetime import datetime as MissingAtRuntime
class Output(FingerprintedDataModel):
    text: str
@cached(cache=cache, output_type=Output, dependency_mode=mode)
def operation(value: MissingAtRuntime, suffix: str = "!") -> Output:
    calls.append(suffix)
    return Output(text=str(value) + suffix)
""",
                "/application/annotation_application.py",
                "exec",
            ),
            vars(module),
        )
        assert module.operation("hello").text == "hello!"
        assert module.operation(value="hello", suffix="!").text == "hello!"
        assert calls == ["!"]


def test_static_binding_refreshes_defaults_without_changing_computation_identity(
    tmp_path: Path,
) -> None:
    # Static identity remains frozen, but a miss must execute the ordinary Python call.
    calls: list[str] = []
    with Cache(SQLiteBackend(tmp_path / "live-default.sqlite")) as cache:

        def original(value: str, suffix: str = "!") -> Value:
            calls.append(suffix)
            return Value(text=value + suffix)

        operation = cached(original, cache=cache, process_id=content_key("live-default", {}))
        assert operation("first").text == "first!"
        original.__defaults__ = ("?",)
        assert operation("second").text == "second?"
        assert operation("second", suffix="!").text == "second!"
        assert operation("second").text == "second?"
        assert operation("second", suffix="?").text == "second?"
        assert calls == ["!", "?", "!"]


@pytest.mark.parametrize("mode", ["static", "traced"])
def test_miss_preserves_caller_spelling_for_wrapped_function(
    tmp_path: Path, monkeypatch, mode: str
) -> None:
    import sys
    from types import ModuleType

    module = ModuleType("spelling_application")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with Cache(SQLiteBackend(tmp_path / "spelling.sqlite")) as cache:
        vars(module).update(cache=cache, mode=mode)
        exec(  # noqa: S102 - controlled wrapper that observes the ordinary call
            compile(
                """from functools import wraps
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel
class Output(FingerprintedDataModel):
    text: str
def original(value: str, suffix: str = "!") -> Output:
    raise AssertionError("wrapper handles execution")
@cached(cache=cache, output_type=Output, dependency_mode=mode)
@wraps(original)
def operation(*args, **kwargs):
    return Output(text=repr(args) + repr(kwargs))
""",
                "/application/spelling_application.py",
                "exec",
            ),
            vars(module),
        )
        assert module.operation("positional").text == "('positional',){}"
        assert module.operation(value="keyword").text == "(){'value': 'keyword'}"
        assert module.operation("explicit", "!").text == "('explicit', '!'){}"
