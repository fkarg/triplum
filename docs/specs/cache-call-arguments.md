# Cache decorator call arguments

Status: owner-approved and implemented. Owner requested multiple positional/keyword arguments with
deterministic named input identity. The underlying cache continues to receive one input digest.

## Declaration

Existing imports/options retain their meanings. Replace the single input type variable with a
ParamSpec in both decorator forms:

```python
@overload
def cached[**P, O: Fingerprintable](
    compute: Callable[P, O],
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
    dependency_mode: Literal["static", "traced"] = "static",
) -> Callable[P, O]: ...


@overload
def cached[**P, O: Fingerprintable](
    compute: None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: None = None,
    codec: None = None,
    policy: CachePolicy | None = None,
    dependency_mode: Literal["static", "traced"] = "static",
) -> Callable[[Callable[P, O]], Callable[P, O]]: ...


@overload
def cached[**P, O: Fingerprintable](
    compute: None = None,
    /,
    *,
    cache: Cache | None | _DefaultCache = _DefaultCache.SHARED,
    process_id: str | None = None,
    output_type: type[O] | None = None,
    codec: Codec[O] | None = None,
    policy: CachePolicy | None = None,
    dependency_mode: Literal["static", "traced"] = "static",
) -> Callable[[Callable[P, O]], Callable[P, O]]: ...
```

`Cache.cached` uses the same overloads with `self` and without the `cache` option. The wrapper
is `def call(*args: P.args, **kwargs: P.kwargs) -> O`. Return-value codec selection is unchanged.
ParamSpec preserves the callable's parameter/return types; input value support is validated at
runtime rather than imposing one Fingerprintable bound on every parameter.
The factory overload with no output type or codec keeps return-type inference tied to the
eventually decorated function rather than the initial decorator-factory call.

## Call identity

1. Inspect the current signature with `annotation_format=Format.FORWARDREF`, bind args/kwargs
   and apply defaults before computation identity, codecs or lookup. Refresh binding metadata
   on every call so current defaults/signatures determine effective input values in both modes.
2. Under `suspend_tracing()`, encode the bound values by parameter name. Values implementing
   `fingerprint()` contribute that digest (top-level digests validated by `_digest`, normalized
   to lowercase hex). Other values use the existing typed value encoder in `datatype.fingerprint`.
   Reuse that private helper internally rather than duplicating it or adding a public utility.
3. A sole non-variadic fingerprintable parameter keeps its current direct input digest. This
   preserves the approved decorator/CachedStep/manual entry-sharing contract and stored keys.
4. Other calls use `content_key("cached-arguments", named_encoded_values)`. Names retain the
   association between parameters and values; canonical JSON ignores named-key ordering.
5. On a miss, invoke the original function with the caller's args/kwargs and return its ordinary
   result. `cache=None` returns the original callable without any binding or fingerprinting.

Signature inspection does not require resolving parameter annotations. Current defaults belong
in input identity; computation definitions retain their existing static/traced identity policies.

Positional versus keyword spelling and omitted versus explicit defaults are equivalent.
Swapping values between named parameters is different. `*args` preserves element order and
multiplicity. Encode unmatched `**kwargs` as ordered key/value pairs: Python functions can
observe their order. Spelling order of declared named parameters remains irrelevant. Ordinary
mapping-valued parameters retain the existing encoder's order-independent value contract.

The supported data domain remains finite primitives, bytes, UUIDs, path spelling, lists/tuples,
string-keyed mappings and fingerprintable values. There is no arbitrary-object/model-dump
fallback. Malformed calls or unsupported values fail before lookup. Per-value validation does
not change the approved encoder's nested fingerprint semantics.

## Example

Supporting output type:

```python
class Rendered(FingerprintedDataModel):
    text: str


@cached
def render(text: str, context: str, *, separator: str = "\n") -> Rendered:
    return Rendered(text=context + separator + text)


render("Evidence", "Collection")
render(context="Collection", text="Evidence", separator="\n")  # same input digest
```

Equal effective arguments reuse the result within the same computation identity. Record IDs
retain their current projections; a fingerprintable record argument does not secretly become
a complete record/binding key. Separate ID/context arguments participate normally.

## Static and traced plumbing

The shared static lookup helper accepts a prepared digest and invocation; CachedStep continues
to supply its existing item digest and `compute(item)` call. No backend/schema change.

Tracing receives the original function, actual args/kwargs, prepared digest and named receiver
bindings. Keep root snapshots on that function, not on a thunk or synthetic argument object.
Only fingerprintable argument objects become receivers; primitives/containers contribute data
without native-method settings inspection. Multiargument receiver names are namespaced by
parameter/variadic position; the existing sole-input path retains its `input` binding and root
shape. Owner binding remains separate. Observed methods shared by multiple known receivers
must validate every relevant binding, including one object aliased under multiple parameters.
Nested/unknown receiver discovery remains bounded and may decline admission.

All fingerprint preparation remains suspended from dependency tracing. Preserve cached-child
manifest propagation and the rule that an untraced child hit may prevent parent admission;
never force a child hit to rerun.

## Independent review

Claude Opus 5.5 (`claude-opus-5-5`), review `48b121d8b31043c6a617af49de3d4d1b`, challenged
primitive receiver registration, fingerprinting outside suspension, thunk root snapshots,
one-input key sharing, digest validation and variadic order. These added implementation checks
and tests; original binding/hash approach retained. Full dispositions live in the capture.

Peer favored initially rejecting **kwargs; this proposal handles its ordered pairs without a
new option. It suggested a traced parent stay admitted after a static child hit; that expectation
conflicts with the approved unsupported-dependency rule and is rejected. The repo uses ty, not
the peer's suggested pyright/mypy commands. Static-global refresh is a separate owner requirement.

Primary guidance: [inspect binding/defaults](https://docs.python.org/3/library/inspect.html#inspect.Signature.bind),
[unevaluated annotation references](https://docs.python.org/3.14/library/annotationlib.html#annotationlib.Format.FORWARDREF),
[ParamSpec decorators](https://typing.python.org/en/latest/reference/generics.html#declaring-decorators),
[wraps](https://docs.python.org/3/library/functools.html#functools.wraps),
[observable variadic keyword order](https://peps.python.org/pep-0468/#specification).
