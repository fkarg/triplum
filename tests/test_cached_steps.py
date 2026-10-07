from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from triplum.cache import Cache, CachedStep, PydanticCodec, SQLiteBackend, cached
from triplum.utils.cache import content_key


class TextValue(BaseModel):
    text: str
    observed_at: int = 0

    def fingerprint(self) -> str:
        return content_key("text-value-v1", {"text": self.text})


class Uppercase(CachedStep[TextValue, TextValue]):
    def __init__(self, cache: Cache | None, *, suffix: str = "") -> None:
        super().__init__(cache=cache, output_type=TextValue)
        self.suffix = suffix
        self.calls = 0

    def fingerprint(self) -> str:
        return content_key("uppercase-v1", {"suffix": self.suffix})

    def compute(self, item: TextValue, /) -> TextValue:
        self.calls += 1
        return TextValue(text=item.text.upper() + self.suffix)


def test_default_pydantic_roundtrip_and_identity_field_selection() -> None:
    codec = PydanticCodec(TextValue)
    value = TextValue(text="Unicode: λ", observed_at=7)
    assert codec.decode(codec.encode(value)) == value
    assert value.fingerprint() == TextValue(text=value.text, observed_at=8).fingerprint()
    assert value.fingerprint() != TextValue(text="different").fingerprint()


def test_shared_cache_reuses_equivalent_instances_and_a_b_a(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    with Cache(SQLiteBackend(path), pending_bytes=65536) as cache:
        first = Uppercase(cache)
        equivalent = Uppercase(cache)
        changed = Uppercase(cache, suffix="!")
        assert first(TextValue(text="a")) == TextValue(text="A")
        assert first(TextValue(text="b")) == TextValue(text="B")
        assert equivalent(TextValue(text="a", observed_at=100)) == TextValue(text="A")
        assert changed(TextValue(text="a")) == TextValue(text="A!")
        assert (first.calls, equivalent.calls, changed.calls) == (2, 0, 1)
    with Cache(SQLiteBackend(path), pending_bytes=65536) as cache:
        reopened = Uppercase(cache)
        assert reopened(TextValue(text="a")) == TextValue(text="A")
        assert reopened.calls == 0


def test_decorator_and_mixin_share_computation_entries(tmp_path: Path) -> None:
    with Cache(SQLiteBackend(tmp_path / "cache.sqlite"), pending_bytes=65536) as cache:
        step = Uppercase(cache)

        @cached(cache=cache, process_id=step.fingerprint(), output_type=TextValue)
        def equivalent(item: TextValue) -> TextValue:
            raise AssertionError("same computation should hit the shared entry")

        assert step(TextValue(text="a")) == equivalent(TextValue(text="a"))


def test_different_computation_kinds_do_not_share(tmp_path: Path) -> None:
    with Cache(SQLiteBackend(tmp_path / "cache.sqlite"), pending_bytes=65536) as cache:
        first = Uppercase(cache)

        @cached(cache=cache, process_id=content_key("lowercase-v1", {}), output_type=TextValue)
        def lowercase(item: TextValue) -> TextValue:
            return TextValue(text=item.text.lower())

        assert first(TextValue(text="aB")) == TextValue(text="AB")
        assert lowercase(TextValue(text="aB")) == TextValue(text="ab")


def test_disabled_cache_bypasses_fingerprint_and_serialization() -> None:
    class UncacheableText(TextValue):
        def fingerprint(self) -> str:
            raise AssertionError("disabled cache must not fingerprint")

    @cached(cache=None, process_id="unused", output_type=UncacheableText)
    def identity(item: UncacheableText) -> UncacheableText:
        return item

    value = UncacheableText(text="a")
    assert identity(value) is value
    step = Uppercase(None)
    assert step(value) == step(value) == TextValue(text="A")
    assert step.calls == 2


def test_pydantic_codec_rejects_lossy_serialization_before_storage() -> None:
    class Extended(TextValue):
        extra: str

    with pytest.raises(TypeError, match="exact"):
        PydanticCodec(TextValue).encode(Extended(text="a", extra="semantic"))

    class Excluded(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        value: object

        def fingerprint(self) -> str:
            return content_key("opaque-v1", {})

    with pytest.raises(ValueError):
        PydanticCodec(Excluded).encode(Excluded(value=object()))

    class Infinite(BaseModel):
        value: float

        def fingerprint(self) -> str:
            return content_key("float-v1", {"value": repr(self.value)})

    with pytest.raises(ValueError):
        PydanticCodec(Infinite).encode(Infinite(value=float("inf")))


def test_codec_namespace_changes_for_schema_and_explicit_format() -> None:
    class OtherText(TextValue):
        suffix: str

    assert PydanticCodec(TextValue).format_id != PydanticCodec(OtherText).format_id
    assert PydanticCodec(TextValue, format_id="text-v2").format_id == "text-v2"


def test_snapshot_isolated_from_mutating_result(tmp_path: Path) -> None:
    with Cache(SQLiteBackend(tmp_path / "cache.sqlite"), pending_bytes=65536) as cache:
        step = Uppercase(cache)
        result = step(TextValue(text="a"))
        result.text = "changed by caller"
        assert step(TextValue(text="a")) == TextValue(text="A")
        assert step.calls == 1


@pytest.mark.parametrize("process_id", ["label", "ab " * 32, "z" * 64])
def test_invalid_process_id_rejected_at_binding(tmp_path: Path, process_id: str) -> None:
    with (
        Cache(SQLiteBackend(tmp_path / "cache.sqlite"), pending_bytes=65536) as cache,
        pytest.raises(ValueError, match="digest"),
    ):
        cached(cache=cache, process_id=process_id, output_type=TextValue)


def test_custom_codec_for_fingerprintable_non_pydantic_value(tmp_path: Path) -> None:
    from dataclasses import dataclass

    from triplum.cache import Codec

    @dataclass(frozen=True)
    class Blob:
        value: bytes

        def fingerprint(self) -> str:
            return content_key("blob-v1", {"hex": self.value.hex()})

    class BinaryCodec(Codec[Blob]):
        @property
        def format_id(self) -> str:
            return "blob-binary-v1"

        def encode(self, value: Blob, /) -> bytes:
            return value.value

        def decode(self, payload: bytes, /) -> Blob:
            return Blob(payload)

    calls = 0
    with Cache(SQLiteBackend(tmp_path / "cache.sqlite"), pending_bytes=65536) as cache:

        @cached(
            cache=cache,
            process_id=content_key("blob-identity-v1", {}),
            output_type=Blob,
            codec=BinaryCodec(),
        )
        def identity(item: Blob) -> Blob:
            nonlocal calls
            calls += 1
            return item

        assert identity(Blob(b"")) == Blob(b"")
        assert identity(Blob(b"")) == Blob(b"")
        assert calls == 1
