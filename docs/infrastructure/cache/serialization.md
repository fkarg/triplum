# Serialize cached values

A [`Codec`][triplum.cache.Codec] converts a fingerprintable output value to bytes and reconstructs
it without changing its semantic content or fingerprint. Storage sees only those bytes. Use a
custom codec when your output is not a Pydantic model or needs another representation.

## Implement a codec

This codec stores the single text field of a frozen dataclass as UTF-8. Both the input and the
output implement `fingerprint()`. Save the complete example as `cache_serialization.py` and run
`uv run python cache_serialization.py` from a checkout:

```python
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from triplum.cache import Cache, Codec, SQLiteBackend
from triplum.utils.cache import content_key


@dataclass(frozen=True)
class Text:
    text: str

    def fingerprint(self) -> str:
        return content_key("example.Text", {"text": self.text})


class TextCodec(Codec[Text]):
    def encode(self, value: Text, /) -> bytes:
        return value.text.encode("utf-8")

    def decode(self, payload: bytes, /) -> Text:
        return Text(payload.decode("utf-8"))


codec = TextCodec()
sample = Text("Grüße")
assert codec.decode(codec.encode(sample)) == sample
assert codec.decode(codec.encode(sample)).fingerprint() == sample.fingerprint()

with TemporaryDirectory() as directory:
    with Cache(SQLiteBackend(Path(directory) / "cache.sqlite")) as cache:

        @cache.cached(
            codec=codec,
            process_id=content_key("lowercase-example.Text", {}),
        )
        def lowercase(value: Text) -> Text:
            print("Computing")
            return Text(value.text.lower())

        print(lowercase(Text("Grüße")).text)
        cache.flush()
        print(lowercase(Text("Grüße")).text)
```

Output:

```text
Computing
grüße
grüße
```

The first call computes and encodes a result. After `flush()`, the second call decodes the stored
bytes without running the function. The temporary SQLite cache is owned by the context and closed
before the directory is removed. The decorator derives computation identity from the function;
changes to an external codec are not discovered automatically. See
[computation identities](computations.md) for the boundary.

## Choose the default or an override

Without `codec=`, the concrete return annotation selects
[`PydanticCodec`][triplum.cache.PydanticCodec]. The model must inherit from Pydantic `BaseModel`
and implement `fingerprint()`. Supply `output_type=YourModel` if the annotation cannot be resolved
or does not name a concrete model. An explicit codec takes precedence over both options; it can
also be passed to `CachedStep`.

The default codec writes JSON bytes and validates them back into the configured model. Every
encode performs a decode and compares fingerprints before the result can enter the cache. Reads
only decode. Unsupported serialization or a changed fingerprint raises in the caller; it is not
silently converted into a cache miss.

Returned values must have the **exact** configured model type; a top-level subclass is rejected
rather than losing its extra fields. Nested subclasses require appropriate model annotations or
serializers. A fingerprint must account for all semantic fields independently: a round-trip check
cannot detect a lost field that the fingerprint itself omitted. See
[value fingerprints](fingerprints.md).

## Responsibilities of a custom codec

`encode(value)` returns immutable `bytes`; `decode(payload)` returns the corresponding value.
Preserve semantic content and the fingerprint, including empty strings, Unicode and any other
values your type permits. Reject payloads that cannot be decoded rather than substituting a
different result. For the example, invalid UTF-8 raises a decoding error.

The runtime does not add a round-trip check to custom codecs: the assertions above illustrate
the invariant your own tests should cover. Encoding and decoding happen in caller threads, not
the background writer. A shared codec must therefore support concurrent calls; this one has no
mutable state. Codecs have no lifecycle methods in this interface. Arrange cleanup yourself if
your implementation owns resources; closing `Cache` closes its backend, not its codec.

Encoding is not part of the cache key. There is no separate format identity or migration of old
rows. If an output model, validator or encoding change makes existing results incompatible,
revise the computation identity or clear its entries before reuse. Automatic function identity
does not discover changes to an external codec class.

Return to the [cache introduction](../cache.md) to compose these pieces, or see
[storage backends](storage.md) to change where the encoded bytes live.
