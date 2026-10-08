# Value fingerprints

A value fingerprint answers **“would this be the same input to the computation?”** Equal
fingerprints let a cached computation reuse a previous result. The value's producer, cache
location and observation history do not have to match.

[`Fingerprintable`][triplum.cache.Fingerprintable] is a structural Protocol: implement
`fingerprint() -> str`, returning a full 64-character SHA-256 hexadecimal digest. Inheritance is
optional for external types. Both cached inputs and outputs need this method. Serialization is
an independent requirement for outputs; Pydantic is the [default](serialization.md).

## Define your own value

This complete example can run in a Python file. `content_key` hashes a kind identifier and
JSON data; you select the fields that give the value its meaning.

```python
from pydantic import BaseModel

from triplum.utils.cache import content_key


class Text(BaseModel):
    text: str
    observed_at: int

    def fingerprint(self) -> str:
        return content_key("example.Text", {"text": self.text})


a = Text(text="A", observed_at=1)
b = Text(text="B", observed_at=2)
restored = Text(text="A", observed_at=3)
print(a.fingerprint() == b.fingerprint())
print(a.fingerprint() == restored.fingerprint())
```

```text
False
True
```

The label `example.Text` separates this meaning from other kinds of values. It is not a codec format
identifier or a manually maintained version number. The text determines identity; `observed_at` records when it was seen. A→B→A restores
A's fingerprint without retaining the intervening history. Equal selected fields intentionally
keep the same identity even when an unselected schema field changes; this method does not hash
the Pydantic schema or class implementation.

This definition is appropriate for operations that use only the text. An operation that uses
`observed_at` to change its semantic result needs a different input contract that includes it.
There is no automatic timestamp filter: a date in document text or a query's temporal constraint
can affect the answer.

## Make the equality promise explicit

An author-defined fingerprint must cover every semantic field its consumers rely on. It cannot
be checked for completeness by the Protocol. Keep these rules local to your value type:

- Include ordered inputs in order, including duplicates. If argument roles matter, name them.
- Do not silently normalize text, paths or numeric representations. Normalize as an explicit
  processing step when it is intended, then fingerprint that step's actual output.
- Use an explicit representation for non-JSON types. `content_key` is a JSON helper, not a
  general Python-object identity algorithm: tuples/lists or non-string dictionary keys can lose
  distinctions in JSON. Encode those distinctions when they matter.
- Recompute after semantic mutation, or make the value immutable before retaining a digest.
- Exclude cache handles, counters, queue policy and bookkeeping times. Serialization may retain
  excluded fields, so a hit can carry old bookkeeping. Attach current-event metadata outside
  the reusable result when freshness matters.

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
