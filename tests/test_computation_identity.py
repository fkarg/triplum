"""Configured identity follows loaded computations and selected semantics, not resources."""

from pathlib import Path
from threading import Lock
from types import FunctionType

import pytest
from pydantic import BaseModel

from triplum.cache import Cache, CachedStep, SQLiteBackend
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import Fingerprinted


class Text(BaseModel):
    text: str
    observed_at: int = 0

    def fingerprint(self) -> str:
        return content_key("identity.Text", {"text": self.text})


class Append(CachedStep[Text, Text]):
    def __init__(self, cache: Cache, suffix: str) -> None:
        super().__init__(cache=cache)
        self.suffix = suffix
        self.calls = 0
        self.resource = Lock()

    def fingerprint_config(self) -> dict[str, object]:
        return {"suffix": self.suffix}

    def compute(self, item: Text, /) -> Text:
        self.calls += 1
        return Text(text=item.text + self.suffix)


def test_automatic_cached_step_reuses_config_without_runtime_resources(tmp_path: Path) -> None:
    # Hashing vars(self) would include counters, locks and separate cache owners.
    path = tmp_path / "cache.sqlite"
    with Cache(SQLiteBackend(path)) as cache:
        step = Append(cache, "!")
        first = step.fingerprint()
        assert step(Text(text="a")) == Text(text="a!")
        assert step.fingerprint() == first
        step.suffix = "?"
        assert step(Text(text="a")) == Text(text="a?")
        step.suffix = "!"
        assert step.fingerprint() == first
        assert step(Text(text="a", observed_at=10)) == Text(text="a!")
        assert step.calls == 2
    with Cache(SQLiteBackend(path)) as cache:
        equivalent = Append(cache, "!")
        assert equivalent(Text(text="a")) == Text(text="a!")
        assert equivalent.calls == 0


class Configured(Fingerprinted):
    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    def fingerprint_config(self) -> dict[str, object]:
        return self.config


def test_config_requires_explicit_projection_and_honors_nested_value_identity() -> None:
    with pytest.raises(NotImplementedError, match="fingerprint_config"):
        Fingerprinted().fingerprint()
    assert (
        Configured({"value": Text(text="a", observed_at=1)}).fingerprint()
        == Configured({"value": Text(text="a", observed_at=2)}).fingerprint()
    )
    assert Configured({"a": 1, "b": 2}).fingerprint() == Configured({"b": 2, "a": 1}).fingerprint()
    assert Configured({"value": [1]}).fingerprint() != Configured({"value": (1,)}).fingerprint()


@pytest.mark.parametrize("unsupported", [object(), float("nan"), {1: "a"}])
def test_config_rejects_values_without_a_stable_projection(unsupported: object) -> None:
    with pytest.raises((TypeError, ValueError), match="fingerprint|finite|string"):
        Configured({"value": unsupported}).fingerprint()


def load(source: str, path: Path) -> type:
    """Execute actual loaded definitions without relying on their current source file."""
    namespace: dict[str, object] = {"__name__": "identity_fixture"}
    path.write_text(source)
    exec(compile(source, str(path), "exec"), namespace)  # noqa: S102 - controlled Python fixture
    cls = namespace["Step"]
    assert isinstance(cls, type)
    return cls


TEMPLATE = '''from triplum.utils.fingerprint import Fingerprinted
class Base:
    def transform(self, value={default}):
        """{doc}"""
        return [item + {delta} for item in value]  # {comment}
class Step(Base, Fingerprinted):
    def fingerprint_config(self):
        return {{}}
'''


def test_loaded_inherited_code_defaults_and_nested_code_define_identity(tmp_path: Path) -> None:
    baseline = {"default": "(1,)", "doc": "first", "delta": "2", "comment": "a"}
    original = load(TEMPLATE.format(**baseline), tmp_path / "original.py")()
    same = load(
        TEMPLATE.format(**{**baseline, "doc": "different", "comment": "b"}),
        tmp_path / "relocated.py",
    )()
    assert original.transform() == same.transform() == [3]
    assert original.fingerprint() == same.fingerprint()
    for changed in ({"delta": "3"}, {"default": "(2,)"}):
        other = load(TEMPLATE.format(**{**baseline, **changed}), tmp_path / "other.py")()
        assert other.transform() == [4]
        assert original.fingerprint() != other.fingerprint()


def test_editing_file_before_first_object_fingerprint_keeps_loaded_identity(tmp_path: Path) -> None:
    baseline = {"default": "(1,)", "doc": "first", "delta": "2", "comment": "a"}
    path = tmp_path / "live.py"
    original = load(TEMPLATE.format(**baseline), path)()
    updated = load(TEMPLATE.format(**{**baseline, "delta": "3"}), path)()
    assert original.transform() == [3]
    assert updated.transform() == [4]
    assert original.fingerprint() != updated.fingerprint()


DEPENDENT = """from triplum.utils.fingerprint import Fingerprinted
def helper(value):
    return value + {delta}
class Step(Fingerprinted):
    def fingerprint_config(self):
        return {{}}
    def fingerprint_dependencies(self):
        return (helper,)
    def __call__(self, value):
        return helper(value)
"""


def test_explicit_helper_definition_changes_identity_without_revision_counter(
    tmp_path: Path,
) -> None:
    first = load(DEPENDENT.format(delta=1), tmp_path / "first.py")()
    second = load(DEPENDENT.format(delta=2), tmp_path / "second.py")()
    same = load(DEPENDENT.format(delta=1), tmp_path / "same.py")()
    assert first(1) == same(1) == 2
    assert second(1) == 3
    assert first.fingerprint() == same.fingerprint()
    assert first.fingerprint() != second.fingerprint()


def test_exception_table_changes_loaded_behavior_and_identity(tmp_path: Path) -> None:
    source = """from triplum.utils.fingerprint import Fingerprinted
class Step(Fingerprinted):
    def fingerprint_config(self):
        return {}
    def __call__(self):
        try:
            return 1 / 0
        except ZeroDivisionError:
            return 42
"""
    caught = load(source, tmp_path / "caught.py")
    uncaught = load(source, tmp_path / "uncaught.py")
    # Different loaded exception behavior can have identical co_code bytes.
    implementation = vars(uncaught)["__call__"]
    assert isinstance(implementation, FunctionType)
    implementation.__code__ = implementation.__code__.replace(co_exceptiontable=b"")
    assert caught()() == 42
    with pytest.raises(ZeroDivisionError):
        uncaught()()
    assert caught().fingerprint() != uncaught().fingerprint()


def test_definition_closure_configuration_is_not_lost(tmp_path: Path) -> None:
    source = """from triplum.utils.fingerprint import Fingerprinted
def factory(prefix):
    class Step(Fingerprinted):
        def fingerprint_config(self):
            return {{}}
        def __call__(self):
            return prefix
    return Step
Step = factory({prefix!r})
"""
    first = load(source.format(prefix="a"), tmp_path / "first.py")()
    second = load(source.format(prefix="b"), tmp_path / "second.py")()
    assert first() == "a"
    assert second() == "b"
    assert first.fingerprint() != second.fingerprint()


@pytest.mark.parametrize(
    "body",
    [
        "    PROMPT = {value!r}\n    def __call__(self):\n        return self.PROMPT\n",
        "    def __call__(self):\n        return {value!r}\n",
        '    def __call__(self):\n        """{value}"""\n        return {value!r}\n',
    ],
)
def test_class_constants_and_returned_literals_are_semantic(tmp_path: Path, body: str) -> None:
    source = (
        "from triplum.utils.fingerprint import Fingerprinted\nclass Step(Fingerprinted):\n"
        "    def fingerprint_config(self):\n        return {}\n"
    )
    first = load(source + body.format(value="a"), tmp_path / "first.py")()
    second = load(source + body.format(value="b"), tmp_path / "second.py")()
    assert first() == "a"
    assert second() == "b"
    assert first.fingerprint() != second.fingerprint()


def test_wrapped_method_body_changes_identity(tmp_path: Path) -> None:
    source = """from functools import wraps
from triplum.utils.fingerprint import Fingerprinted
def decorate(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapped
class Step(Fingerprinted):
    def fingerprint_config(self):
        return {{}}
    @decorate
    def __call__(self):
        return {value!r}
"""
    first = load(source.format(value="a"), tmp_path / "first.py")()
    second = load(source.format(value="b"), tmp_path / "second.py")()
    assert first() == "a"
    assert second() == "b"
    assert first.fingerprint() != second.fingerprint()


def test_annotation_only_change_changes_definition_identity(tmp_path: Path) -> None:
    source = """from triplum.utils.fingerprint import Fingerprinted
class Step(Fingerprinted):
    def fingerprint_config(self):
        return {{}}
    def __call__(self) -> {annotation}:
        return 1
"""
    first = load(source.format(annotation="int"), tmp_path / "first.py")()
    second = load(source.format(annotation="float"), tmp_path / "second.py")()
    assert first.fingerprint() != second.fingerprint()


@pytest.mark.parametrize(
    "implementation",
    [
        "    @staticmethod\n    def transform():\n        return {value!r}\n",
        "    @classmethod\n    def transform(cls):\n        return {value!r}\n",
        "    @property\n    def transform(self):\n        return {value!r}\n",
    ],
)
def test_static_class_and_property_definitions_are_included(
    tmp_path: Path, implementation: str
) -> None:
    source = (
        "from triplum.utils.fingerprint import Fingerprinted\nclass Step(Fingerprinted):\n"
        "    def fingerprint_config(self):\n        return {}\n"
    )
    first = load(source + implementation.format(value="a"), tmp_path / "first.py")()
    second = load(source + implementation.format(value="b"), tmp_path / "second.py")()
    assert first.fingerprint() != second.fingerprint()


def test_concrete_protocol_implementation_code_is_not_excluded(tmp_path: Path) -> None:
    source = """from typing import Protocol
from triplum.utils.fingerprint import Fingerprinted
class Operation(Protocol):
    def __call__(self): ...
class Step(Operation, Fingerprinted):
    def fingerprint_config(self):
        return {{}}
    def __call__(self):
        return {value!r}
"""
    first = load(source.format(value="a"), tmp_path / "first.py")()
    second = load(source.format(value="b"), tmp_path / "second.py")()
    assert first() == "a"
    assert second() == "b"
    assert first.fingerprint() != second.fingerprint()


class Depends(Fingerprinted):
    def __init__(self, dependency: object) -> None:
        self.dependency = dependency

    def fingerprint_config(self) -> dict[str, object]:
        return {}

    def fingerprint_dependencies(self) -> tuple[object, ...]:
        return (self.dependency,)


def test_dependency_values_follow_their_semantics_and_reject_opaque_resources() -> None:
    value = Text(text="a")
    step = Depends(value)
    identity = step.fingerprint()
    value.observed_at = 10
    assert step.fingerprint() == identity
    value.text = "b"
    assert step.fingerprint() != identity
    with pytest.raises(TypeError, match="dependency"):
        Depends(object()).fingerprint()


def test_explicit_output_type_is_part_of_default_cached_step_identity(tmp_path: Path) -> None:
    class Alternate(Text):
        pass

    class Identity(CachedStep[Text, Text]):
        def fingerprint_config(self) -> dict[str, object]:
            return {}

        def compute(self, item: Text, /) -> Text:
            return item

    with Cache(SQLiteBackend(tmp_path / "cache.sqlite")) as cache:
        first = Identity(cache=cache, output_type=Text)
        second = Identity(cache=cache, output_type=Alternate)
        assert first.fingerprint() != second.fingerprint()


def test_recursive_function_capture_fails_without_recursing_forever() -> None:
    from triplum.utils.fingerprint import definition_hash

    def recursive():
        return recursive()

    with pytest.raises(TypeError, match="recursive"):
        definition_hash(recursive)


def test_unsupported_method_descriptor_requires_explicit_identity() -> None:
    from functools import cached_property

    class Opaque(Fingerprinted):
        def fingerprint_config(self) -> dict[str, object]:
            return {}

        @cached_property
        def result(self) -> int:
            return 1

    with pytest.raises(TypeError, match="descriptor"):
        Opaque().fingerprint()


def test_postponed_annotation_change_changes_definition_identity(tmp_path: Path) -> None:
    source = """from __future__ import annotations
from triplum.utils.fingerprint import Fingerprinted
class Step(Fingerprinted):
    def fingerprint_config(self):
        return {{}}
    def __call__(self) -> {annotation}:
        return 1
"""
    first = load(source.format(annotation="int"), tmp_path / "first.py")()
    second = load(source.format(annotation="float"), tmp_path / "second.py")()
    assert first.fingerprint() != second.fingerprint()


def test_inherited_protocol_default_behavior_changes_identity(tmp_path: Path) -> None:
    source = """from typing import Protocol
from triplum.utils.fingerprint import Fingerprinted
class Operation(Protocol):
    def helper(self):
        return {value!r}
class Step(Operation, Fingerprinted):
    def fingerprint_config(self):
        return {{}}
    def __call__(self):
        return self.helper()
"""
    first = load(source.format(value="a"), tmp_path / "first.py")()
    second = load(source.format(value="b"), tmp_path / "second.py")()
    assert first() == "a"
    assert second() == "b"
    assert first.fingerprint() != second.fingerprint()


def test_frozenset_class_constant_is_included(tmp_path: Path) -> None:
    source = """from triplum.utils.fingerprint import Fingerprinted
class Step(Fingerprinted):
    allowed = frozenset({values!r})
    def fingerprint_config(self):
        return {{}}
    def __call__(self, text):
        return text in self.allowed
"""
    first = load(source.format(values="ab"), tmp_path / "first.py")()
    second = load(source.format(values="cd"), tmp_path / "second.py")()
    assert first("a") is True
    assert second("a") is False
    assert first.fingerprint() != second.fingerprint()


def test_opaque_class_configuration_can_be_projected_explicitly(tmp_path: Path) -> None:
    source = """import re
from triplum.utils.fingerprint import Fingerprinted
class Step(Fingerprinted):
    pattern = re.compile({pattern!r})
    def fingerprint_config(self):
        return {{"pattern": self.pattern.pattern, "flags": self.pattern.flags}}
    def __call__(self, text):
        return bool(self.pattern.fullmatch(text))
"""
    first = load(source.format(pattern=r"\d+"), tmp_path / "first.py")()
    second = load(source.format(pattern=r"\s+"), tmp_path / "second.py")()
    assert first("12") is True
    assert second("12") is False
    assert first.fingerprint() != second.fingerprint()
