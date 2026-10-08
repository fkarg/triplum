# Value fingerprints

A value fingerprint answers **“would this be the same input to the computation?”** Equal
fingerprints let a cached computation reuse a previous result. The value's producer, cache
location and observation history do not have to match.

## Start with a data model

Inherit [`FingerprintedModel`][triplum.datatype.FingerprintedModel] to get `fingerprint()` and
Pydantic serialization. By default, the fingerprint includes the model's qualified type name and
actual field values. You do not write a hash function or maintain a version string.

```python
from triplum.datatype import FingerprintedModel


class Text(FingerprintedModel):
    text: str


value = Text(text="A")
original = value.fingerprint()
value.text = "B"
print(original == value.fingerprint())
value.text = "A"
print(original == value.fingerprint())
```

```text
False
True
```

The digest is recomputed on each call. Returning to A restores its fingerprint, without including
producer identity or processing history. Model code, validators and the full schema do not enter
data identity. Changing a selected value changes its fingerprint; changing only unselected
structure does not. Different qualified model names identify different kinds of values.

## Exclude bookkeeping

Declare fields that consumers do not use in `fingerprint_exclude`. Exclusions affect identity,
not serialization, so the field remains available in stored results:

```python
from typing import ClassVar

from triplum.datatype import FingerprintedModel


class Text(FingerprintedModel):
    fingerprint_exclude: ClassVar[frozenset[str]] = frozenset({"observed_at"})

    text: str
    observed_at: int


a = Text(text="A", observed_at=1)
b = Text(text="A", observed_at=2)
print(a.fingerprint() == b.fingerprint())
print(b.model_dump()["observed_at"])
```

```text
True
2
```

Subclasses inherit exclusions; assigning a new set replaces the inherited set. Exclusions must
name declared model fields; unknown names fail when the class is defined. Allowed extra fields
always contribute unless a custom projection removes them. There is no automatic timestamp filter:
a temporal query constraint can affect the answer, while an observation time may be bookkeeping.
An operation that uses an excluded field needs an input contract that includes it.

A cache hit can return the earlier result's bookkeeping. Attach current-event metadata after
reusing the result when it must describe the current call.

## Select a custom projection

Override `fingerprint_data()` when field values need a different semantic representation. This
example projects a date explicitly into its ISO spelling:

```python
from datetime import date

from triplum.datatype import FingerprintedModel


class DatedText(FingerprintedModel):
    text: str
    day: date

    def fingerprint_data(self) -> dict[str, object]:
        return {"text": self.text, "day": self.day.isoformat()}


first = DatedText(text="Hello", day=date(2026, 1, 1))
second = DatedText(text="Hello", day=date(2026, 1, 1))
print(first.fingerprint() == second.fingerprint())
```

```text
True
```

The model's qualified name still distinguishes the projected value kind. An override defines the
whole projection: include every semantic field its consumers need and apply any exclusions there.
Subclasses inherit that projection; new subclass fields contribute only when the projection
includes them. Equal projections intentionally share identity, regardless of how they were produced.

The default projection separates declared fields under `"fields"` from allowed extras under
`"extras"`, so an extra with the same name cannot overwrite a declared field. It omits private
attributes and computed fields. `fingerprint`, `fingerprint_data` and `fingerprint_exclude` are
reserved for the identity interface, so they cannot be data-field names. Serialization aliases and `Field(exclude=True)` do not hide actual
semantic fields from it. That separation lets the default codec detect when serialization loses
semantic data; see [serialization](serialization.md).

Supported values are `None`, booleans, integers, finite floats, strings, bytes, UUIDs, paths,
lists, tuples and string-keyed mappings. Lists and tuples remain distinct; mapping insertion order
does not matter. A path identifies its spelling, not file contents. Nested values must implement `fingerprint()` themselves, normally by inheriting from
`FingerprintedModel`, or be projected explicitly. A plain nested Pydantic model is not supported
automatically. Neither are arbitrary Pydantic field types: project dates, decimals and other
unsupported values explicitly. Non-finite floats are rejected. Fingerprinting support does not
guarantee a default JSON round trip: arbitrary binary bytes may need Pydantic serialization
configuration or a [custom codec](serialization.md).

Do not silently normalize content merely to increase reuse. Perform normalization as an explicit
step when intended, then fingerprint its output. Use ordered pairs when mapping order affects the
computation. Keep recursive object graphs outside these value models.

## Use an external value type

[`Fingerprintable`][triplum.cache.Fingerprintable] is a structural Protocol. External types can
implement `fingerprint() -> str` without inheriting from our model. Return a full 64-character
SHA-256 hexadecimal digest covering every semantic field:

```python
from dataclasses import dataclass

from triplum.utils.cache import content_key


@dataclass(frozen=True)
class Text:
    text: str

    def fingerprint(self) -> str:
        return content_key("example.Text", {"text": self.text})


print(Text("Hello").fingerprint() == Text("Hello").fingerprint())
```

`content_key` hashes a kind identifier and JSON data. It is not the model's typed encoder:
JSON can collapse distinctions such as tuples versus lists, so represent them explicitly when
needed. The kind distinguishes meaning, not a manually maintained version. Both cached inputs
and outputs need a fingerprint; custom non-Pydantic outputs also need a [codec](serialization.md).
The Protocol cannot check whether a projection includes every field its consumers rely on.

## Share content without sharing provenance

Two sources can contain the same text while referring to different documents. A text-only
embedding request can reuse its vector across both. A result carrying a parent `source_id`
cannot reuse an arbitrary earlier parent reference merely because the text matches.

Project a record into the data the computation actually consumes. Include parent/context fields
when the result depends on them, or attach record references after reusing an identity-free
result. A fingerprint does not merge storage identity, provenance or access permissions.

Current `Source.fingerprint` and `Chunk.fingerprint` are **properties**, not the required method.
They also omit storage IDs, and Chunk's property omits `source_id`. They are not directly usable
as cache values. See [record identity](../fingerprints.md#existing-record-properties) for the
current behavior; defining the explicit value above does not require changing record IDs.

## Compose cached steps

A cache lookup matches the **input fingerprint and computation fingerprint together**. Its output
is another value with its own fingerprint. The next step uses that output's semantic fingerprint,
not the upstream computation's fingerprint.

Consequently, different normalizers that produce the same `Text` can share the next computation's
entry. A plain uncached function can also produce that value. There is no required pipeline
executor or requirement to cache every stage. The repository example demonstrates both reuse
across upstream computations and reuse after reopening:

```sh
uv run python examples/cached_pipeline.py
```

Next: [Computation fingerprints and configured steps](computations.md).
