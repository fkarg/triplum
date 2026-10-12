# Fresh effective computation context

Status: P3 draft for owner review. The owner requires changed effective globals/context to
change computation identity. This draft specifies the bounded refresh behavior; production
implementation has not started.

## Purpose and declaration

Keep experimentation caches reusable when collection/community descriptions, captured settings
or supported application helpers change between calls. Public declarations remain:

```python
def definition_hash(definition: object) -> str: ...


def function_fingerprint(compute: object) -> str: ...


class FingerprintedComputationMixin:
    def fingerprint_config(self) -> dict[str, object]: ...
    def fingerprint(self) -> str: ...
```

`definition_hash` accepts a loaded Python function or class and returns a SHA-256 hex digest of
its existing bounded loaded-definition projection. `function_fingerprint` accepts a Python
function and supplies the same automatic identity to decorators, retaining its helpful errors.
The mixin combines the current class definition digest and explicitly selected configuration.
No argument, return type or new override is introduced. Decorator ParamSpec signatures remain
those in [call arguments](cache-call-arguments.md).

## Guarantees

- Every call to these automatic fingerprint functions rereads supported loaded definitions and
  effective settings. Default static decorators calculate a call-local computation identity
  before each lookup, under suspended dependency tracing. CachedStep keeps calling its existing
  fingerprint method; its inherited class-definition digest is now fresh too.
- Refresh uses the existing static, non-strict discovery projection: code, defaults, keyword
  defaults, captures, statically resolved globals/module attributes, bounded application helpers
  and supported ordinary application classes. It changes observation time, not discovery scope.
- Removing complete-definition memoization must preserve digests for unchanged state, existing
  hash namespaces and table/input addressing. Restoring a represented context A after B restores
  A's computation identity and can reuse A's retained results, including after reopening storage.
  Equality includes the existing order-sensitive global/default/capture mapping projections.
- Cache immutable code identity and disassembly as before. Do not memoize an entire digest by
  mutable function/class object. No compiled dependency-reader representation is introduced.
- Fixed `process_id` and custom `fingerprint()` overrides retain their full-control semantics.
  Their authors cover effective context. `cache=None` keeps the exact original callable bypass.
  Codec selection remains lazy, initialized once; P3 does not refresh output-model contracts.
- Existing instrumentation exclusions, error behavior and unsupported-discovery rules remain.
  Because discovery now runs every lookup, changing supported state to unsupported state or
  removing a referenced binding raises the existing error on that next call, before reuse.
  Traced mode retains its strict snapshots, runtime manifests, conservative admission behavior
  and receiver handling; it does not become the engine for static mode.

## Example

```python
from triplum.cache import cached
from triplum.datatype import FingerprintedDataModel

DESCRIPTION = "Collection A"


class Rendered(FingerprintedDataModel):
    text: str


@cached
def render(text: str) -> Rendered:
    return Rendered(text=DESCRIPTION + ": " + text)


first = render("Evidence")  # compute or reuse A
DESCRIPTION = "Collection B"
second = render("Evidence")  # compute or reuse B
DESCRIPTION = "Collection A"
assert render("Evidence") == first  # reuse retained A
assert second.text != first.text
```

Context may also be explicit arguments, following P2. This does not require moving existing
globals into wrappers or maintaining version counters.

## Boundaries and tradeoffs

Referenced context must stay stable while identity is prepared and the computation executes.
This is not an atomic snapshot of Python process state. Mutation during a call, including by
another thread, remains outside the supported pure-computation contract. Concurrent calls with
stable context may share a wrapper; automatic identity must be local to each call.

Files, services, environment reads, native implementations, dynamic dispatch and unsupported
class/Pydantic schema state retain the existing limits. A Path still identifies spelling, not
file bytes. Effective external content requires input/configuration identity or a complete
override. Recognized bookkeeping instrumentation remains excluded. Between-call mutation of
represented data is covered; computation-internal semantic mutation remains unsupported.

Refreshing costs a dependency/settings walk and canonical hashing on each static lookup,
proportional to represented state. Existing immutable-code caches reduce this cost. The intended
unit remains expensive composite processing, not cheap chunking. A compiled reader plan could
reduce cost but introduces rebinding/invalidation machinery; it is deferred absent measured need.

## Review and evidence

Current local probe: changing DESCRIPTION from A to B on the same cached function returns A;
standalone definition_hash also stays unchanged. Both freeze layers must change.

Read-only local measurement at P2 commit `472b3a4`: CPython 3.14.8, macOS 26.7.1 arm64,
five samples of 20,000 warmed calls with cyclic GC disabled. Fresh projection medians were
25 µs for a minimal function, 165 µs for global settings plus a helper/instrumentation, and
191 µs for a configured class with helper settings. These are identity costs, not end-to-end
cache hit costs or portable throughput guarantees. Larger represented state can cost more.
Fresh and existing digests matched for unchanged state; counter/log growth stayed excluded;
description A→B→A and in-place dictionary changes were detected. The immutable code/disassembly
caches each recorded 600,017 hits and 5 misses. No production files were modified.

Primary research: Cloudpickle caches referenced names by code object but reads current globals,
defaults and captures when collecting function state ([maintainer implementation](https://github.com/cloudpipe/cloudpickle/blob/master/cloudpickle/cloudpickle.py)).
Marimo includes closed-over values and warns about mutations, imported-module limits and large
captured values ([official caching guide](https://docs.marimo.io/api/caching/)).
These support fresh value observation and retained immutable discovery work, not arbitrary
Python state completeness. Joblib's [Memory guide](https://joblib.readthedocs.io/en/latest/user_guide/memory.html)
also separates argument hashing from external-factor validity; it is not a precedent for complete
automatic helper discovery.

Claude Opus 5.5 (`claude-opus-5-5`), review `cdf47cadbb9c4b89821f95251cb40a8e`, supports the core.
It independently checked both freeze layers, A→B→A restoration, in-place dict mutation, mapping
ordering, large represented-state cost, configured-step cost, overrides/tracing and concurrent
mutation. Wording/tests now explicitly cover newly unsupported state and order-sensitive equality.
Its additional local probe found roughly 10.7 ms for a 20,000-entry represented global dict;
not an end-to-end hit measurement. This reinforces the cost boundary; compiled readers remain
deferred. Full attempted falsifications and dispositions are recorded in the ingress/cache capture.

## Q21 — post-computation validation

Owner review must settle this additional admission behavior before implementation:

- A: draft above. Stable context during a call is a required precondition; one automatic
  identity walk before lookup. This is the session recommendation: trust the supported
  computation boundary and keep this refresh change local.
- B: after an automatic static miss, recompute identity before saving; skip saving on mismatch,
  returning the computed result. This is Opus's recommendation: mitigate persistent wrong-key
  writes when another thread changes context. Costs one additional walk per miss plus an
  admission branch and observable skip accounting. Hits and full identity overrides are unchanged.

B still requires stable context: it misses A→B→A changes and unrepresented state. It detects
violations rather than providing atomic snapshots. If selected, the plan must include
deterministic thread/barrier coverage for a changed-context miss and a separately defined
skip reason; do not silently report it as background-queue pressure.
