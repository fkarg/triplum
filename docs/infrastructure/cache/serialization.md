# Serialize cached values

A [`Codec`][triplum.cache.Codec] converts a fingerprintable output value to bytes and reconstructs
it without changing its semantic content or fingerprint. Storage sees only those bytes. Use a
custom codec when you need another representation, including for non-Pydantic values.

## Use the default

A return annotation selects Pydantic serialization. `FingerprintedDataModel` supplies both the
Pydantic model and its data fingerprint, so ordinary use needs no codec configuration:

```python
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel


class Text(FingerprintedDataModel):
    text: str


@cached
def lowercase(value: Text) -> Text:
    return Text(text=value.text.lower())


print(lowercase(Text(text="Hello")).text)
```

Save it as a Python file and run it to print `hello`. The decorator opens the shared cache lazily.
The following example changes only how the text value is encoded.

## Implement a codec

This codec stores `Text` as UTF-8 instead of JSON. The data model and decorator work as before;
only `codec=` changes. Save this complete example as `cache_serialization.py` and run
`uv run python cache_serialization.py`:

```python
from triplum.cache import Codec, cached
from triplum.datatype import FingerprintedDataModel


class Text(FingerprintedDataModel):
    text: str


class TextCodec(Codec[Text]):
    def encode(self, value: Text, /) -> bytes:
        return value.text.encode("utf-8")

    def decode(self, payload: bytes, /) -> Text:
        return Text(text=payload.decode("utf-8"))


codec = TextCodec()
sample = Text(text="Grüße")
assert codec.decode(codec.encode(sample)) == sample
assert codec.decode(codec.encode(sample)).fingerprint() == sample.fingerprint()


@cached(codec=codec)
def lowercase(value: Text) -> Text:
    print("Computing")
    return Text(text=value.text.lower())


print(lowercase(sample).text)
print(lowercase(sample).text)
```

With an empty cache:

```text
Computing
grüße
grüße
```

The first call computes and encodes a result; the second decodes the cached bytes without running
the function. Results persist, so another run may print no `Computing` line. The shared cache and
its lifetime use the usual defaults; see [ownership](policies.md) to change them.

The same codec interface supports [external value types](fingerprints.md#use-an-external-value-type)
that supply their own fingerprint. Changes to an external codec are not discovered automatically;
see [computation identities](computations.md) for that boundary.

## Choose the default or an override

Without `codec=`, the concrete return annotation selects
[`PydanticCodec`][triplum.cache.PydanticCodec]. The model must inherit from Pydantic `BaseModel`
and implement `fingerprint()`; `FingerprintedDataModel` provides both. Supply `output_type=YourModel`
if the annotation cannot be resolved or does not name a concrete model. An explicit codec takes precedence over both options; it can
also be passed to `CachedStep`.

The default codec writes JSON bytes and validates them back into the configured model. Every
encode performs a decode and compares fingerprints before the result can enter the cache. Reads
only decode. Unsupported serialization or a changed fingerprint raises in the caller; it is not
silently converted into a cache miss.

Returned values must have the **exact** configured model type; a top-level subclass is rejected
rather than losing its extra fields. Nested subclasses require appropriate model annotations or
serializers. Nested `FingerprintedDataModel` values contribute their own fingerprints, so losing their
semantic fields can fail the round-trip check. Plain nested Pydantic models need an explicit
[fingerprint projection](fingerprints.md#select-a-custom-projection). With a custom fingerprint, account for all semantic fields
independently: a round-trip check cannot detect a lost field that the fingerprint itself omitted. See
[value fingerprints](fingerprints.md).

Use concrete `list[...]` or `tuple[...]` annotations when their distinction matters. A broad
sequence annotation or untyped extra field can deserialize a tuple as a list; their fingerprints
differ, so the codec rejects that loss. Fields excluded only from identity still use normal
Pydantic serialization; custom serializers or field exclusions may omit them from stored results.

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
include the relevant changed definition in the computation identity or clear its entries before
reuse. Neither automatic function identity nor the configured-step default discovers output
schemas, validators or external codec definitions automatically. No manually bumped version
string is required; the [computation guide](computations.md) explains dependency selection.

Return to the [cache introduction](../cache.md) to compose these pieces, or see
[storage backends](storage.md) to change where the encoded bytes live.
