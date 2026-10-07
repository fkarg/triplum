"""Default Pydantic serialization for fingerprintable cache values."""

from pydantic import BaseModel, TypeAdapter

from triplum.cache.protocols import Codec, Fingerprintable
from triplum.utils.cache import content_key


class PydanticCodec[T: Fingerprintable](Codec[T]):
    """Serialize a fingerprintable Pydantic model to JSON bytes.

    The default namespace includes the qualified model name and both JSON schemas.
    Supply a versioned format_id when custom serializers or validators change behavior
    without changing those schemas. A format namespace is a compatibility promise.
    Schema documentation edits can also change this conservative default namespace.

    Each encode verifies a semantic fingerprint round-trip before cache admission.
    This costs a decode on writes; reads only decode. Unsupported or lossy fields fail
    in the caller. Exact model types prevent silent top-level subclass truncation.
    Nested subclasses need appropriate Pydantic annotations/serializers. Fingerprints
    must include every semantic field; model_dump alone can omit nested subclass fields.
    """

    def __init__(self, model: type[T], *, format_id: str | None = None) -> None:
        if not issubclass(model, BaseModel):
            raise TypeError("default cache serialization requires a Pydantic model")
        if not callable(getattr(model, "fingerprint", None)):
            raise TypeError("cached models must implement fingerprint()")
        self._model = model
        self._adapter: TypeAdapter[T] = TypeAdapter[T](model)
        self._format = (
            format_id
            if format_id is not None
            else content_key(
                "pydantic-json-v1",
                {
                    "model": f"{model.__module__}.{model.__qualname__}",
                    "validation": model.model_json_schema(mode="validation"),
                    "serialization": model.model_json_schema(mode="serialization"),
                },
            )
        )
        if not self._format:
            raise ValueError("codec format_id must not be empty")

    @property
    def format_id(self) -> str:
        return self._format

    def encode(self, value: T, /) -> bytes:
        if type(value) is not self._model:
            raise TypeError("Pydantic cache values must have the exact configured model type")
        payload = self._adapter.dump_json(value, round_trip=True, warnings="error")
        if self.decode(payload).fingerprint() != value.fingerprint():
            raise ValueError("serialization changed the value's semantic fingerprint")
        return payload

    def decode(self, payload: bytes, /) -> T:
        return self._adapter.validate_json(payload)
