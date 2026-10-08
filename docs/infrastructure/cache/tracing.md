# Track helpers used at runtime

Use optional runtime tracing when a computation chooses application helpers dynamically. The
usual `@cached` mode follows statically resolvable helpers; tracing additionally records the
application functions actually called while computing a missing result.

```python
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel


class Text(FingerprintedDataModel):
    text: str

    def normalized(self) -> str:
        return self.text.casefold()


@cached(dependency_mode="traced")
def normalize(value: Text) -> Text:
    return Text(text=value.normalized())


print(normalize(Text(text="Straße")).text)
print(normalize(Text(text="Straße")).text)
```

Both calls print `strasse`. The call to `value.normalized()` is dispatched through the input
object, outside the default static helper discovery. Tracing observes that application method.
On a miss, the cache computes the value while recording a dependency
manifest. On a later call, it resolves and checks that manifest before reusing the saved value.
The trace runs during computation, not by executing the function again on every cache hit.

The same `dependency_mode="traced"` keyword works with `@cache.cached` and the `CachedStep`
initializer. The default remains `"static"`; data fingerprints and serialization are unchanged.

## Validate before reusing a result

A traced call first looks up a small manifest index for the root computation and input. The index
records paths identifying the functions previously observed for that input. It does not accumulate
a list of every historical code hash. Resolving those paths and fingerprinting their current
implementations selects the separate result entry.

If a method changes from implementation A to B, B selects another result. Returning to A can reuse
A's earlier result. Missing metadata or result bytes cause computation again. The usual background
write policy applies to both records; a skipped metadata write can lose reuse without changing the
computed answer.

Unlike static mode's first-use snapshot, traced mode refreshes root definitions/settings on each
lookup and validates observed dependencies. This costs more than a direct result lookup: work
grows with the retained manifest shapes and their dependencies. Tracing also adds overhead while a
miss computes. Cache larger operations where avoided work can justify these costs; a cheap string
operation makes a readable example, not a performance recommendation.

## Keep the boundary explicit

Tracing resolves application functions and ordinary methods on the current input or `CachedStep`
owner. The same application-package/source-directory boundary as [static discovery](computations.md#know-the-automatic-boundary)
applies. Receiver state belongs in the input fingerprint or selected configuration; directly
referenced class constants are checked too.

Unknown receivers, ambiguous method aliases, custom attribute dispatch, or local functions that
cannot be resolved disable admission of the new result. A stored manifest referring to a missing
module is a miss; validation does not import it. If the monitoring tool is unavailable, the call
computes without saving a new traced result. Unsupported dependency inference likewise bypasses
caching; exceptions from user fingerprint methods, computation and serialization still propagate.

Writes to object attributes, container entries or captured nonlocals disable admission. So do
known container-mutating calls, except recognized direct append-only global instrumentation.
These checks are conservative: even a local scratch container can prevent caching.

The trace follows synchronous execution in the calling thread. Observed application work or
cached child calls on another thread conservatively prevent saving the traced result, so parallel
misses may not persist. Work delegated to other threads, native implementations, files, model
weights and external services is outside complete dependency coverage.
Represent effective external identity in input data or selected settings. A call trace does not
prove that every influence on a Python computation has been captured.

## Compose cached calls

A traced child contributes its dependency manifest even when it returns a cache hit. Methods in
that manifest must refer to the same input or owner object already known to the parent; otherwise
the parent result is not saved. A static child's cache hit is preserved too, but it has no runtime manifest, so the parent
result is not saved. The cache does not rerun the child merely to discover dependencies.

Recognized `functools.cache` and `functools.lru_cache` wrappers also prevent traced admission:
their hits hide executed dependencies, while their own reuse remains intact. A computation mixin
nested in selected settings currently prevents admission of the parent too, because its cached
definition fingerprint does not establish fresh dependency identity.

Tracing metadata uses the same backend as result bytes. [Cache statistics](administration.md)
therefore count metadata tables, entries and payloads as well as computational results.

Next: [Computation fingerprints](computations.md).
