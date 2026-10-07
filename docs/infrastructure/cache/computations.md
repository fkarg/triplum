# Computation fingerprints

A computation fingerprint answers **“would the same operation run?”** It covers the implementation,
effective configuration and relevant external dependencies. Together with the
[input value's fingerprint](fingerprints.md), it selects a cached result.

The decorator's `process_id` argument supplies this digest explicitly. `CacheKey.process` holds
its 32 bytes; `cache stats` displays its 64-character hexadecimal form, which `--computation`
accepts. These are different API spellings for the same computation fingerprint.

## Define a configured step

[`CachedStep`][triplum.cache.CachedStep] implements the cache lookup and `__call__`. Implement two
methods: `compute(value)` performs the work, and `fingerprint()` identifies that work and its
configuration. Save this complete example as a `.py` file and run it with `uv run python`:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel

from triplum.cache import Cache, CachedStep, SQLiteBackend
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import source_hash


class Text(BaseModel):
    text: str

    def fingerprint(self) -> str:
        return content_key("example.Text", {"text": self.text})


class Append(CachedStep[Text, Text]):
    def __init__(self, suffix: str, cache: Cache | None) -> None:
        super().__init__(cache=cache)
        self.suffix = suffix

    def fingerprint(self) -> str:
        return content_key(
            "example.Append",
            {"code": source_hash(type(self)), "suffix": self.suffix},
        )

    def compute(self, value: Text) -> Text:
        print("Computing", self.suffix)
        return Text(text=value.text + self.suffix)


with TemporaryDirectory() as directory:
    with Cache(SQLiteBackend(Path(directory) / "cache.sqlite")) as cache:
        value = Text(text="Hello")
        for suffix in ("!", "!", "?", "!"):
            print(Append(suffix, cache)(value).text)
```

```text
Computing !
Hello!
Hello!
Computing ?
Hello?
Hello!
```

Equivalent instances share the `example.Append` computation with the same class source and `!`
configuration; changing to `?`
selects a different entry. Returning to `!` reuses its earlier result. The cache owner is not
configuration and does not enter the fingerprint.

The `compute` return annotation selects Pydantic serialization. The step borrows its cache and
never closes it. Calling `super().__init__()` without arguments instead uses the lazy shared
default; pass `cache=None` to bypass caching. If combining the mixin with a domain Protocol,
put `CachedStep` first in the bases. It does not automatically adapt existing indexing steps'
input/output shapes to fingerprintable values.

## Decide when to revise a computation

No manually bumped version number is required. This example combines the existing `source_hash`
helper with the selected suffix: editing the concrete class code or changing that setting changes
its fingerprint. `source_hash` ignores comments, formatting and docstrings. It needs inspectable
class source and does not discover called helpers, inherited behavior or external model definitions.
Those dependencies must be represented explicitly when relevant. The broader automatic class
interface is under review; this example uses existing primitives.

For ordinary functions, `@cached` and `@cache.cached` provide the automatic function identity
explained below. Supply `process_id` only when you compose the computation fingerprint yourself;
it replaces inference, so relevant function/dependency code must then enter your explicit digest.
A constant label plus settings alone does not detect implementation changes. Kind names distinguish
meanings; a manually changed version label is neither required nor a substitute for represented
code and data.

| Change | What must happen |
| --- | --- |
| A setting changes the answer | Include it in the computation fingerprint |
| A helper, model or library changes behavior | Include/revise its dependency identity |
| Output schema or codec becomes incompatible with saved results | Revise the computation fingerprint or clear its table |
| Backend, queue policy or pipeline position changes | Keep the same semantic computation fingerprint |

There is no hidden serialization-format key or migration layer. An ordinary read decodes the
saved value; it does not prove that your current code would compute that value again.

## Use automatic function identity where it fits

Bare `@cached` and `@cache.cached` infer identity for ordinary Python functions. This convenience
hashes source, module/qualified name, evaluated defaults and nonlocal captures at decoration.
Keep captured configuration unchanged afterward. Globals, called helpers, external files, model
weights and environment settings are not discovered: use an explicit `process_id` for them.

Defaults and captures can contain plain scalar values, lists, tuples, string-keyed dictionaries
or objects with `fingerprint()`. List and tuple identities differ; dictionary iteration order is
preserved. `Path` and Pydantic models without a fingerprint method are not directly supported.
Lambdas, source-unavailable functions and callable objects need explicit identity. Run source-based
examples from files rather than stdin or a REPL.

## The existing object helper is different

[`Fingerprinted`][triplum.utils.fingerprint.Fingerprinted] supplies automatic identity to several
reference indexing steps. It hashes class/base source and **every instance attribute**. It does
not implement the explicit-configuration example above, and does not share the function helper's
state rules.

Do not combine its default method with `CachedStep`: it encounters cache resources and locks.
It can also collapse distinctions such as list versus tuple and integer versus string dictionary
keys. Use an explicit computation method for types where these distinctions matter. The generic
helper's implementation is under review; its current behavior is described in
[configured-object identity](../fingerprints.md#configured-object-identity).

Next: [Serialization and custom codecs](serialization.md).
