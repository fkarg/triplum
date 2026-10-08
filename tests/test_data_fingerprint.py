from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, Field, computed_field

from triplum.cache import PydanticCodec, cached, close_default_cache
from triplum.datatype import FingerprintedDataModel, FingerprintedDataModelMixin


class Text(FingerprintedDataModel):
    text: str
    observed_at: int = 0
    fingerprint_exclude = frozenset({"observed_at"})


CALLS: list[str] = []


@cached
def normalize(value: Text) -> Text:
    CALLS.append(value.text)
    return Text(text=value.text.casefold())


def test_bare_cached_data_model_requires_no_manual_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    close_default_cache()
    CALLS.clear()
    try:
        assert normalize(Text(text="Straße", observed_at=1)) == Text(text="strasse")
        assert normalize(Text(text="Straße", observed_at=2)) == Text(text="strasse")
        assert normalize(Text(text="OTHER")) == Text(text="other")
        close_default_cache()
        assert normalize(Text(text="Straße", observed_at=3)) == Text(text="strasse")
        assert CALLS == ["Straße", "OTHER"]
    finally:
        close_default_cache()


def test_values_follow_mutation_not_construction_history() -> None:
    value = Text(text="A")
    original = value.fingerprint()
    assert original == Text(observed_at=10, text="A").fingerprint()
    value.text = "B"
    assert value.fingerprint() != original
    value.text = "A"
    assert value.fingerprint() == original


def test_bookkeeping_stays_serialized() -> None:
    value = Text(text="A", observed_at=17)
    codec = PydanticCodec(Text)
    assert codec.decode(codec.encode(value)).observed_at == 17
    assert value.fingerprint() == Text(text="A", observed_at=99).fingerprint()


def test_nested_identity_uses_selected_fields() -> None:
    class Bundle(FingerprintedDataModel):
        values: list[Text]

    first = Bundle(values=[Text(text="A", observed_at=1)])
    same = Bundle(values=[Text(text="A", observed_at=2)])
    changed = Bundle(values=[Text(text="B", observed_at=1)])
    assert first.fingerprint() == same.fingerprint()
    assert first.fingerprint() != changed.fingerprint()
    assert PydanticCodec(Bundle).decode(PydanticCodec(Bundle).encode(first)) == first


def test_actual_nested_subclass_values_expose_lossy_serialization() -> None:
    class Parent(FingerprintedDataModel):
        text: str

    class Child(Parent):
        language: str

    class Bundle(FingerprintedDataModel):
        item: Parent

    first = Bundle(item=Child(text="A", language="en"))
    changed = Bundle(item=Child(text="A", language="de"))
    assert first.model_dump() == changed.model_dump()  # The loss identity must reveal.
    assert first.fingerprint() != changed.fingerprint()
    with pytest.raises(ValueError, match="semantic fingerprint"):
        PydanticCodec(Bundle).encode(first)


def test_serialization_exclusion_does_not_exclude_semantics() -> None:
    class Hidden(FingerprintedDataModel):
        visible: str
        semantic: int = Field(default=0, exclude=True)

    first = Hidden(visible="A", semantic=1)
    second = Hidden(visible="A", semantic=2)
    assert first.model_dump() == second.model_dump()
    assert first.fingerprint() != second.fingerprint()
    with pytest.raises(ValueError, match="semantic fingerprint"):
        PydanticCodec(Hidden).encode(first)


def test_default_values_aliases_and_computed_fields() -> None:
    class Value(FingerprintedDataModel):
        text: str = Field(default="A", alias="content")

        @computed_field
        @property
        def fingerprint_for_display(self) -> str:
            return self.fingerprint()

    assert Value().fingerprint() == Value(content="A").fingerprint()
    assert Value().fingerprint() != Value(content="B").fingerprint()
    assert Value().fingerprint_for_display == Value().fingerprint()


def test_allowed_extra_values_enter_identity() -> None:
    class Extra(FingerprintedDataModel):
        model_config = ConfigDict(extra="allow")
        text: str

    assert (
        Extra(text="A", language="en").fingerprint() != Extra(text="A", language="de").fingerprint()
    )
    assert Extra(text="A", a=1, b=2).fingerprint() == Extra(text="A", b=2, a=1).fingerprint()


def test_type_and_container_distinctions() -> None:
    class Value(FingerprintedDataModel):
        value: object

    assert (
        Value(value={"a": 1, "b": 2}).fingerprint() == Value(value={"b": 2, "a": 1}).fingerprint()
    )
    assert Value(value=[1, 2]).fingerprint() != Value(value=(1, 2)).fingerprint()
    assert len({Value(value=item).fingerprint() for item in (None, True, 1, 1.0, "1")}) == 5
    assert Value(value=b"abc").fingerprint() != Value(value="abc").fingerprint()
    assert Value(value=Path("abc")).fingerprint() != Value(value="abc").fingerprint()
    identifier = UUID("00000000-0000-0000-0000-000000000001")
    assert Value(value=identifier).fingerprint() != Value(value=str(identifier)).fingerprint()


def test_projection_supports_custom_semantic_values() -> None:
    class Event(FingerprintedDataModel):
        occurred_at: datetime

        def fingerprint_data(self) -> dict[str, object]:
            return {"instant": self.occurred_at.timestamp()}

    first = Event(occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    second = Event(occurred_at=datetime(2026, 1, 2, tzinfo=UTC))
    assert first.fingerprint() != second.fingerprint()
    codec = PydanticCodec(Event)
    assert codec.decode(codec.encode(first)).fingerprint() == first.fingerprint()


def test_unsupported_values_and_exclusion_typos_fail_explicitly() -> None:
    class Value(FingerprintedDataModel):
        value: object

    with pytest.raises(TypeError, match="fingerprint"):
        Value(value=object()).fingerprint()
    with pytest.raises(TypeError, match="string"):
        Value(value={1: "one"}).fingerprint()
    with pytest.raises(ValueError, match="finite"):
        Value(value=float("nan")).fingerprint()

    with pytest.raises(ValueError, match="observed_at"):

        class Typo(FingerprintedDataModel):
            text: str
            fingerprint_exclude = frozenset({"observed_at"})


def test_model_kind_and_field_projection_are_independent_of_schema_metadata() -> None:
    from pydantic import create_model

    first = create_model("Projection", __base__=FingerprintedDataModel, text=(str, ...))
    revised = create_model(
        "Projection",
        __base__=FingerprintedDataModel,
        text=(str, Field(description="Documentation does not change this value")),
    )
    other_kind = create_model("OtherKind", __base__=FingerprintedDataModel, text=(str, ...))
    assert (
        first.model_validate({"text": "A"}).fingerprint()
        == revised.model_validate({"text": "A"}).fingerprint()
    )
    assert (
        first.model_validate({"text": "A"}).fingerprint()
        != other_kind.model_validate({"text": "A"}).fingerprint()
    )


def test_external_nested_fingerprint_is_honored() -> None:
    from triplum.utils.cache import content_key

    class External:
        def __init__(self, semantic: str, observed_at: int) -> None:
            self.semantic = semantic
            self.observed_at = observed_at

        def fingerprint(self) -> str:
            return content_key("external-value", self.semantic)

    class Envelope(FingerprintedDataModel):
        item: object

    assert (
        Envelope(item=External("A", 1)).fingerprint()
        == Envelope(item=External("A", 2)).fingerprint()
    )
    assert (
        Envelope(item=External("A", 1)).fingerprint()
        != Envelope(item=External("B", 1)).fingerprint()
    )


def test_plain_nested_model_needs_an_explicit_projection() -> None:
    class Plain(BaseModel):
        text: str

    class Envelope(FingerprintedDataModel):
        item: Plain

    with pytest.raises(TypeError, match="fingerprint"):
        Envelope(item=Plain(text="A")).fingerprint()


def test_ambiguous_container_annotation_cannot_silently_lose_tuple_identity() -> None:
    from collections.abc import Sequence

    class Value(FingerprintedDataModel):
        items: Sequence[int]

    with pytest.raises(ValueError, match="semantic fingerprint"):
        PydanticCodec(Value).encode(Value(items=(1, 2)))


def test_fingerprint_fields_cannot_shadow_identity_configuration() -> None:
    for name in ("fingerprint", "fingerprint_data", "fingerprint_exclude"):
        with pytest.warns(UserWarning, match="shadows"), pytest.raises(TypeError, match=name):
            type(
                "Shadow", (FingerprintedDataModel,), {"__annotations__": {name: str}, name: "value"}
            )


def test_alias_and_same_named_extra_cannot_hide_a_changed_input(tmp_path: Path) -> None:
    from triplum.cache import Cache, SQLiteBackend

    class Aliased(FingerprintedDataModel):
        model_config = ConfigDict(extra="allow")
        text: str = Field(alias="content")

    with Cache(SQLiteBackend(tmp_path / "cache.sqlite")) as cache:

        @cache.cached
        def project(value: Aliased) -> Text:
            return Text(text=value.text)

        assert project(Aliased(content="first", text="extra")) == Text(text="first")
        assert project(Aliased(content="second", text="extra")) == Text(text="second")


def test_exclusion_setting_must_not_treat_a_string_as_field_names() -> None:
    with pytest.raises(TypeError, match="frozenset"):
        type(
            "Invalid",
            (FingerprintedDataModel,),
            {"__annotations__": {"a": str, "b": str}, "fingerprint_exclude": "ab"},
        )


def test_mixin_composes_with_existing_model_configuration_and_hooks() -> None:
    from pydantic import field_validator

    initialized: list[str] = []

    class ExistingModel(BaseModel):
        model_config = ConfigDict(extra="allow")
        text: str
        observed_at: int = 0

        @field_validator("text")
        @classmethod
        def normalize_text(cls, value: str) -> str:
            return value.strip()

        @classmethod
        def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
            super().__pydantic_init_subclass__(**kwargs)
            initialized.append(cls.__name__)

    class Value(FingerprintedDataModelMixin, ExistingModel):
        fingerprint_exclude: ClassVar[frozenset[str]] = frozenset({"observed_at"})

    class Child(Value):
        language: str

    assert initialized == ["Value", "Child"]
    first = Value(text=" A ", observed_at=1, extra="one")
    assert first.text == "A"
    assert first.fingerprint() == Value(text="A", observed_at=2, extra="one").fingerprint()
    assert first.fingerprint() != Value(text="A", extra="two").fingerprint()
    assert PydanticCodec(Value).decode(PydanticCodec(Value).encode(first)) == first
    assert (
        Child(text="A", language="en").fingerprint() != Child(text="A", language="de").fingerprint()
    )
    with pytest.raises(ValueError, match="unknown fingerprint_exclude"):
        type("Typo", (Value,), {"fingerprint_exclude": frozenset({"missing"})})


def test_mixin_requires_composition_before_pydantic_base() -> None:
    with pytest.raises(TypeError, match="before"):
        type("WrongOrder", (BaseModel, FingerprintedDataModelMixin), {})


def test_plain_mixin_requires_custom_projection() -> None:
    class Value(FingerprintedDataModelMixin):
        def __init__(self, text: str) -> None:
            self.text = text

        def fingerprint_data(self) -> dict[str, object]:
            return {"text": self.text}

    assert not issubclass(FingerprintedDataModelMixin, BaseModel)
    assert Value("A").fingerprint() == Value("A").fingerprint()
    assert Value("A").fingerprint() != Value("B").fingerprint()
    with pytest.raises(TypeError, match="override"):
        FingerprintedDataModelMixin().fingerprint()
