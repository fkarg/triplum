# Computation fingerprints

A computation fingerprint answers **“would the same operation run?”** It covers the implementation,
effective configuration and relevant external dependencies. Together with the
[input value's fingerprint](fingerprints.md), it selects a cached result.

## Let the decorator identify the computation

Normally, add `@cached`. It derives computation identity, uses the shared cache, and chooses
Pydantic serialization from the return annotation. `FingerprintedDataModel` handles data identity:

```python
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel


class Text(FingerprintedDataModel):
    text: str


@cached
def normalize(value: Text) -> Text:
    return Text(text=value.text.casefold())


print(normalize(Text(text="Straße")).text)
print(normalize(Text(text="Straße")).text)
```

Both calls print `strasse`; the second can reuse the first result, including an accepted write
that has not reached disk yet. Existing persisted entries may also be reused on the first call.
Save it as a Python file to make the function source available. The
[value fingerprint](fingerprints.md) answers which inputs are equivalent; the decorator handles
which computation runs on them. No manually maintained version label is needed.

## Configure a function with a factory

Capture a setting in a function factory; the decorator includes its value in computation identity.
Continue with the imports and `Text` model above:

```python
def make_append(suffix: str):
    @cached
    def append(value: Text) -> Text:
        print("Computing", suffix)
        return Text(text=value.text + suffix)

    return append


value = Text(text="Hello")
for suffix in ("!", "!", "?", "!"):
    print(make_append(suffix)(value).text)
```

With an empty cache:

```text
Computing !
Hello!
Hello!
Computing ?
Hello?
Hello!
```

Each factory call creates a function, but equal captured settings select the same computation.
Changing `!` to `?` selects another entry; returning to `!` reuses the earlier result.
On later runs, persisted entries can also remove the `Computing` lines. Keep captured settings
unchanged after decoration.

## Use automatic function identity where it fits

Bare `@cached` and `@cache.cached` hash the function's source, module/qualified name, evaluated
defaults and nonlocal captures when decorated. Globals, called helpers, external files, model
weights and environment settings are not discovered: use an explicit `process_id` for them.

Defaults and captures can contain plain scalar values, lists, tuples, string-keyed dictionaries
or objects with `fingerprint()`. List and tuple identities differ; dictionary iteration order is
preserved. `Path` and Pydantic models without a fingerprint method are not directly supported.
Lambdas, source-unavailable functions and callable objects need explicit identity. Save these
examples as Python files; source-based inference cannot generally work from stdin or a REPL.

## Include a helper without introducing a class

When a function calls an external helper, compose `process_id` from both definitions. Keep the
`Text` model from the first example; this continuation still uses the shared cache and automatic
Pydantic serialization:

```python
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import definition_hash


def fold(text: str) -> str:
    return text.casefold()


def transform(value: Text) -> Text:
    return Text(text=fold(value.text))


transform = cached(
    transform,
    process_id=content_key(
        "example.transform",
        {"compute": definition_hash(transform), "helper": definition_hash(fold)},
    ),
)

print(transform(Text(text="Straße")).text)
print(transform(Text(text="Straße")).text)
```

Both calls print `strasse`. Changing either loaded function definition changes this process ID;
there is no label to bump. The explicit ID replaces inference, which is why it includes
`transform` as well as `fold`. Include effective settings and further dependencies when present.

`definition_hash()` supports ordinary Python function/class definitions within the boundaries
below. It is **not an arbitrary model or schema hasher**: passing a Pydantic model such as
`definition_hash(Text)` can raise `TypeError` for unsupported descriptors. For an output contract,
select its relevant semantic fields/settings and supported validator/helper definitions explicitly,
or clear existing entries when that contract becomes incompatible. A JSON schema alone does not
represent validator behavior. The fixed-schema example above tracks its two functions; it does
not promise automatic invalidation for changes to the `Text` model.

## Use a class when the operation needs one

[`CachedStep`][triplum.cache.CachedStep] is optional. It supplies cache lookup and `__call__` for
classes with a `compute(value)` method and a `fingerprint_config()` hook selecting effective
settings. Continue with the `Text` model above:

```python
from triplum.cache import CachedStep


class Append(CachedStep[Text, Text]):
    def __init__(self, suffix: str) -> None:
        super().__init__()
        self.suffix = suffix

    def fingerprint_config(self) -> dict[str, object]:
        return {"suffix": self.suffix}

    def compute(self, value: Text) -> Text:
        return Text(text=value.text + self.suffix)


print(Append("!")(Text(text="Hello")).text)
```

This prints `Hello!`. The inherited fingerprint combines loaded computation code with selected
settings, so equivalent instances can reuse results. `super().__init__()` uses the shared cache;
the `compute` return annotation selects serialization. Counters, clients, locks and cache resources
stay outside identity unless explicitly selected. Return `{}` for a stateless class. Configuration
is read on each call; do not change it while computation runs.

Pass `cache=None` to the base initializer to bypass caching, or supply an explicit owner as
shown in [cache ownership](policies.md). A step borrows its owner and never closes it.
When combining with a domain Protocol, put `CachedStep` first in the bases. This does not adapt
existing indexing steps' input/output shapes to fingerprintable values.

## Select settings and dependencies

Supported configuration contains plain finite numbers, strings, booleans, `None`, lists, tuples,
string-keyed dictionaries, paths and objects implementing `fingerprint()`. Mapping insertion order
does not affect this identity; use an ordered list of pairs when the computation observes order.
A path identifies its spelling, not the contents of the file at that path. Fingerprint file bytes
or the model's actual identity when they affect the result.

Loaded class identity covers the qualified name, application method definitions and supported
immutable class constants, including ordinary bases. Unused or overridden methods can also
invalidate entries. Comments and non-executed docstring text do not affect it; adding/removing
a docstring can conservatively change it. Pure Python classes do not need inspectable source
files. See [`definition_hash()`][triplum.utils.fingerprint.definition_hash] for the precise
supported definitions and exclusions. Reload edited implementations to run and identify the new
code; identities are not guaranteed stable across Python interpreter versions.

Other class attributes, including compiled regexes, Enum members, mutable containers and nested
classes, are not inferred. Neither are globals, helper functions or external models discovered by
following calls. Select their effective values in `fingerprint_config()`. Loaded definitions and
captured configuration must remain unchanged after their first hash; create a new definition
instead of monkey-patching an already fingerprinted class or function. Override
`fingerprint_dependencies()` to return a tuple of relevant Python function/class definitions or
objects with `fingerprint()`. Their definitions or semantic fingerprints then enter the digest.
A declared helper's own external dependencies must also be represented; this is not a recursive
import scanner. See the generated [`FingerprintedComputationMixin` reference][triplum.utils.fingerprint.FingerprintedComputationMixin]
for the hook declarations. For example, this ordinary callable declares the helper it uses:

```python
from triplum.utils.fingerprint import FingerprintedComputationMixin


def normalize(text: str) -> str:
    return text.casefold()


class Normalize(FingerprintedComputationMixin):
    def fingerprint_config(self) -> dict[str, object]:
        return {}

    def fingerprint_dependencies(self) -> tuple[object, ...]:
        return (normalize,)

    def __call__(self, text: str) -> str:
        return normalize(text)


print(Normalize()("Straße"))
print(Normalize().fingerprint() == Normalize().fingerprint())
```

```text
strasse
True
```

`definition_hash()` is also available when composing a full `process_id` explicitly. It hashes
the loaded definition with the same rules; a helper's supported closure captures contribute,
including wrapped functions. Recursive definition captures are rejected. An explicit `fingerprint()` override remains available when an
application already has a complete computation identity.

| Change | How identity follows it |
| --- | --- |
| A setting changes the answer | Select it in `fingerprint_config()` |
| Application method implementation changes | Loaded method definitions enter the automatic fingerprint |
| A helper or model changes behavior | Declare the helper or select the model's actual identity |
| Output schema or codec becomes incompatible | Represent its relevant definition explicitly, or clear the computation's table |
| Backend, queue policy or pipeline position changes | Keep the same semantic computation fingerprint |

There is no hidden serialization-format key or migration layer, and output schemas and validators
are not automatically hashed. An ordinary read decodes the saved value; it does not prove that
current code would compute that value again. Equal value projections remain interchangeable for
consumers of those projected fields, even if upstream histories differ. That does not guarantee
that another output model can decode an older stored payload. An explicit `output_type` contributes
its qualified name to the default `CachedStep` identity, not its full schema.

## Use the same mixin without caching

[`FingerprintedComputationMixin`][triplum.utils.fingerprint.FingerprintedComputationMixin] provides these configuration and
dependency hooks independently of `CachedStep`. Use it for an ordinary callable that needs
computation identity without cache lookup, as in the `Normalize` example above.
[Configured-object identity](../fingerprints.md#configured-object-identity) explains its use by reference steps. `CachedStep` already inherits it, so no extra mixin base is needed.

The decorator's source/default/capture algorithm is separate. Supply `process_id` when composing
its identity yourself; that replaces inference, so include relevant computation code as well as
configuration and dependencies. Constant kind labels distinguish meanings; they do not detect
code changes by themselves.

The optional decorator `process_id` argument overrides inference with a complete computation
digest. `CacheKey.process` stores its 32 bytes; `cache stats` displays the 64-character hexadecimal
form accepted by `--computation`. These are representations of the same identity.

Next: [Serialization and custom codecs](serialization.md).
