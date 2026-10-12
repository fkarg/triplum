# Computation fingerprints

A computation fingerprint answers **“would the same operation run?”** It covers the implementation,
effective configuration and relevant external dependencies. Together with the
[input value's fingerprint](fingerprints.md), it selects a cached result.
Automatic discovery is a bounded aid for quick experimentation: it does not guarantee that
every change affecting a result invalidates the cache. The limits below explain when to reload
definitions, provide an explicit identity or clear retained entries.

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
The [value fingerprint](fingerprints.md) answers which inputs are equivalent; the decorator handles
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
unchanged after the first call.

## Call helpers normally

The decorator follows ordinary Python helpers in application code. Continue with `Text` above:

```python
def fold(text: str) -> str:
    return text.casefold()


@cached
def transform(value: Text) -> Text:
    return Text(text=fold(value.text))


print(transform(Text(text="Straße")).text)
print(transform(Text(text="Straße")).text)
```

Both calls print `strasse`. Editing `fold` and loading the new decorated function changes its
computation identity, even if `transform` itself is unchanged. No dependency list or version
string is needed.

Ordinary application classes can be helpers too. Continue with the same imports and `Text` model:

```python
class Folder:
    def run(self, text: str) -> str:
        return text.casefold()


@cached
def transform_with_class(value: Text) -> Text:
    return Text(text=Folder().run(value.text))


print(transform_with_class(Text(text="Straße")).text)
print(transform_with_class(Text(text="Straße")).text)
```

Both calls print `strasse`. In the default static mode, editing `Folder.run` and loading the
new definitions changes the computation identity. Supported referenced application classes use
loaded-definition hashing: methods, bases and supported immutable constants contribute. This
does not call a class's `fingerprint()` or Python's `hash()`; an instance's `fingerprint()` still defines its selected
value when that instance is an input or configuration.

## Know the automatic boundary

Bare `@cached` and `@cache.cached` identify loaded Python definitions, evaluated defaults,
nonlocal captures and statically resolved application helpers on the first call. Helpers may be
defined later in the module, provided they exist when the function is first called. Referenced helpers
can call further helpers; recursive calls are supported. Direct global names and module attribute
chains are resolved without executing properties or descriptors.

Application helpers belong to the same top-level package, or the same source directory for a
standalone script. Calls outside that boundary contribute the callable's qualified name, not
its implementation. Supported referenced global settings contribute too, including mappings of
application helpers. Discarded append-only instrumentation on plain lists or sets, and counters
updated only by `NAME += constant`, are excluded. Semantic mutation of global settings is
unsupported: a global that the computation assigns and otherwise reads raises `TypeError`. Keep
counters and diagnostic collections separate from semantic settings. Import application helpers
at module level; a function-local import of application code raises `TypeError`, while local
imports of external libraries are outside identity like other external calls.
In static mode, ordinary application classes referenced through global names or module attributes
follow the same boundary on a best-effort basis. If the existing class projection cannot handle
a definition, such as a generated class with unsupported descriptors or native bases, that
reference falls back to its qualified name. External classes, Pydantic model classes and class
references in traced mode also contribute their qualified names, not their definitions.
Class-valued defaults, captures and selected configuration still require an explicit projection.
Changing an external library, file, model weight or hidden resource state is therefore not
automatically detected.
Arbitrary dynamic dispatch through input objects also remains outside static helper discovery.
Optional [runtime tracing](tracing.md) can record supported
input/owner method calls and validate those dependencies on later lookups.

Defaults and captures support finite scalars, lists, tuples, string-keyed mappings, paths and
objects with `fingerprint()`. A path identifies its spelling, not file contents. Keep helper
bindings and captured settings fixed after the first call; reload edited implementations to run and
identify the new code. Loaded-code identity also works without inspectable source, including
functions defined interactively. It is not guaranteed stable across Python interpreter versions.
Module references work through statically resolved attributes; module-valued defaults/configuration
and dynamic module passing are unsupported. Unsupported identity projections raise `TypeError`
rather than silently omitting state.

When external state affects an answer, make its effective identity part of the input or captured
configuration. An explicit `process_id` remains available for applications that already have a
complete computation identity; it replaces automatic inference. There is no manual dependency
parameter.

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

## Select settings for a computation class

Supported configuration contains plain finite numbers, strings, booleans, `None`, lists, tuples,
string-keyed dictionaries, paths and objects implementing `fingerprint()`. Mapping insertion order
does not affect selected class configuration; use ordered pairs when the computation observes
order. A path identifies its spelling, not file bytes. Select the model's actual identity or file
content fingerprint when it affects the result.

Loaded class identity covers the qualified name, application method definitions and supported
immutable class constants, including ordinary bases. Its helper discovery uses the same boundary
as the decorator. Unused or overridden methods can also invalidate entries. Comments and
non-executed docstring text do not affect identity; adding or removing a docstring can
conservatively change it. Configuration is selected explicitly rather than scanning instance
attributes, so resources and counters remain outside identity.

Other class attributes, including compiled regexes, Enum members, mutable containers and nested
classes, are not inferred. Select their effective values in `fingerprint_config()` when needed.
Keep loaded definitions and helper bindings unchanged after their first hash; recreate a class
rather than monkey-patching it after fingerprinting.

## Use the computation mixin without caching

[`FingerprintedComputationMixin`][triplum.utils.fingerprint.FingerprintedComputationMixin]
supplies computation identity independently of cache lookup. For an ordinary configured callable:

```python
from triplum.utils.fingerprint import FingerprintedComputationMixin


class Append(FingerprintedComputationMixin):
    def __init__(self, suffix: str) -> None:
        self.suffix = suffix

    def fingerprint_config(self) -> dict[str, object]:
        return {"suffix": self.suffix}

    def __call__(self, text: str) -> str:
        return text + self.suffix


print(Append("!")("Hello"))
print(Append("!").fingerprint() == Append("!").fingerprint())
```

This prints `Hello!` and `True`. `CachedStep` already inherits this mixin, so it needs no extra base.
See [configured-object identity](../fingerprints.md#configured-object-identity) for reference steps
that use it. [`definition_hash()`][triplum.utils.fingerprint.definition_hash] exposes the shared
loaded-definition digest when an application needs to compose its own identity. A custom
`fingerprint()` override can supply a complete computation identity instead.

| Change | How identity follows it |
| --- | --- |
| A setting changes the answer | Select it in `fingerprint_config()` |
| Application method implementation changes | Loaded method definitions enter the automatic fingerprint |
| An application helper changes behavior | Statically resolved helper definitions enter automatically |
| External model or file content changes | Include its actual identity in effective settings or input data |
| Output schema or codec becomes incompatible | Represent its relevant definition explicitly, or clear the computation's table |
| Backend, queue policy or pipeline position changes | Keep the same semantic computation fingerprint |

Automatic identity is a useful aid for quick experiments, with bounded discovery rather than
complete correctness for arbitrary Python code. Mutable or opaque class attributes and hidden
state are not inferred. Unsupported referenced class definitions fall back to name-only identity;
explicit root class hashing with `definition_hash()` or the computation mixin can still reject
unsupported descriptors. Static definitions and bindings freeze on first use, so reload edited
code instead of monkey-patching a warmed computation.
Output-model schema, validator and default changes are not automatically hashed: stop writers and
use `uv run triplum cache clear --name my_pipeline.normalize` for the affected computation, or
supply a complete `process_id` that includes those definitions. See
[administration](administration.md#find-and-clear-a-functions-retained-versions) for name selection.

There is no hidden serialization-format key or migration layer. An ordinary read decodes the
saved value; it does not prove that current code would compute that value again. Equal value
projections remain interchangeable for consumers of those projected fields, even if upstream
histories differ. That does not guarantee
that another output model can decode an older stored payload. An explicit `output_type` contributes
its qualified name to the default `CachedStep` identity, not its full schema.

The optional decorator `process_id` argument overrides inference with a complete computation
digest. `CacheKey.process` stores its 32 bytes; `cache stats` displays the 64-character hexadecimal
form accepted by `--computation`. These are representations of the same identity.

Next: [Administration](administration.md) to inspect and clear stored results. The advanced
pages cover [runtime dependency tracing](tracing.md) and [serialization](serialization.md).
