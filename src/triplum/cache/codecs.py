"""Default Pydantic serialization for fingerprintable cache values."""

from pydantic import BaseModel, TypeAdapter

from triplum.cache.protocols import Codec, Fingerprintable


class PydanticCodec[T: Fingerprintable](Codec[T]):
    """Serialize a fingerprintable Pydantic model to JSON bytes.

    Encoding is not part of cache identity. For incompatible model/encoding changes,
    revise the computation fingerprint or clear its table; cache rows are not migrated.

    Each encode verifies a semantic fingerprint round-trip before cache admission.
    This costs a decode on writes; reads only decode. Unsupported or lossy fields fail
    in the caller. Exact model types prevent silent top-level subclass truncation.
    Nested subclasses need appropriate Pydantic annotations/serializers. Fingerprints
    must include every semantic field; model_dump alone can omit nested subclass fields.
    """

    def __init__(self, model: type[T]) -> None:
        if not issubclass(model, BaseModel):
            raise TypeError("default cache serialization requires a Pydantic model")
        if not callable(getattr(model, "fingerprint", None)):
            raise TypeError("cached models must implement fingerprint()")
        self._model = model
        self._adapter: TypeAdapter[T] = TypeAdapter[T](model)

    def encode(self, value: T, /) -> bytes:
        if type(value) is not self._model:
            raise TypeError("Pydantic cache values must have the exact configured model type")
        payload = self._adapter.dump_json(value, round_trip=True, warnings="error")
        if self.decode(payload).fingerprint() != value.fingerprint():
            raise ValueError("serialization changed the value's semantic fingerprint")
        return payload

    def decode(self, payload: bytes, /) -> T:
        return self._adapter.validate_json(payload)
