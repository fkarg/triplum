# Automatic computation dependencies

Owner approves static default plus optional traced discovery, without manual dependency lists.
Static and optional traced discovery are implemented and verified.

## Interface

`cached(..., dependency_mode: Literal["static", "traced"] = "static")`
and the same keyword on `Cache.cached` and `CachedStep.__init__`.
[Decorator call arguments](cache-call-arguments.md) owns signature binding and normalized input
identity; value projections remain unchanged. Existing
`process_id` is a full override. Remove `fingerprint_dependencies`; ordinary external content
identifiers can be selected configuration. Computation definitions and settings use one engine.

## Static discovery

Freeze lazily on first invocation (standalone definition_hash on first request), allowing
helpers defined later in a module. Read loaded code, defaults, captures and referenced globals.
Follow Python helpers in the root computation’s top-level application package or standalone source directory;
resolve module attribute chains through dictionaries without descriptor execution. Include
nested code and terminate cycles with object-ID visitation and ordinal references. Hash ordinary
plain global configuration including registry mappings; global names written by computation
are outside the supported pure-computation contract. Discarded append-only instrumentation
on exact lists/sets may be excluded when there are no other reads. Statically referenced ordinary
application classes reached through global names or module attributes try the existing
loaded-definition projection in static mode: methods, bases and supported immutable constants.
If that projection raises UnsupportedFingerprint, restore traversal state and retain qualified-name
identity for the reference. External classes, Pydantic BaseModel subclasses and referenced classes
in traced mode retain qualified-name identity only. Class-valued defaults, captures and selected configuration still require explicit
projections. No class fingerprint method or Python hash is invoked; instance fingerprint
projections remain the data/configuration boundary. Arbitrary dynamic dispatch through input
objects and semantic global mutation are outside static discovery. Unsupported
semantic projections raise TypeError in static mode; traced mode will bypass only dedicated
unsupported-dependency failures, preserving exceptions from user fingerprint implementations. External functions stop at
qualified-name boundary; external implementation changes are not covered. Pydantic/data schemas
remain outside this bounded inference. Keep frozen bindings/settings unchanged after first use.

## Traced discovery and storage

On a miss, use sys.monitoring PY_START to collect executed application code objects only;
do not hash, serialize, or write cache inside callbacks. One installed tool and thread-local
collection scopes coordinate concurrent callers. Application work on another thread conservatively
taints active traces, including overlapping independent misses; results remain usable but may
not be admitted. If the tool is unavailable, compute uncached.
Resolve observed functions afterwards through module/class dictionaries. Nested code already
contained in known definitions is covered. Unresolvable application code disables admission.
Collecting runtime code supplements static identity; it does not infer native implementation,
files, services, hidden resource state or arbitrary dispatch effects.

A preliminary root computation fingerprint plus full normalized input digest addresses a small
manifest index using the existing CacheBackend get/put_many abstraction. Each manifest stores a template of resolvable function paths and known receiver slots. Refresh
their definition fingerprints and referenced receiver class settings before any result hit. Full actual process identity includes root identity
and manifest; results live under that computation/input pair. A→B→A retains old result blobs.
No schema expansion or migration layer. Index updates losing concurrent variants cause misses,
not incorrect hits. Missing result blobs also cause misses. Candidate validation is proportional
to retained variants/dependencies, not constant-time. Per-input indexes constrain unrelated
branch growth; shared-per-root indexes could reduce metadata but amplify candidate sets.

Traced mode refreshes the root settings projection at each lookup. Unknown root state,
unknown application dependencies, unavailable tracing, or unresolvable
stored manifests cause recomputation without admission. Ordinary exceptions propagate and
tracing is released. Traced child hits contribute their dependency manifest to parent traces. A static child hit
remains reusable but declines parent admission because it has no runtime manifest. Receiver
dependencies propagate only when the object is a known parent argument or owner receiver.
Multiargument receiver bindings follow the call-arguments contract; the sole-input path retains
its existing binding shape. No explicit dependency list or manually maintained version counter.

## Limits

This supports quick experimentation through bounded invalidation, not complete correctness or
proof that an arbitrary Python execution is pure. Mutable or opaque class attributes remain
outside automatic class identity. Unsupported referenced class definitions fall back to name-only
identity in static mode; explicit root class hashing can still reject unsupported descriptors.
This best-effort static refinement does not extend traced class discovery. Pydantic output
schema, validator and default changes can require clearing the affected computation by name
or supplying a complete process_id; no schema equivalence or output-value lookup key is inferred.
Captured or global state determining dynamic dispatch must enter the static projection; resources requiring
external identity need fingerprintable settings. Python interpreter/compiler changes can alter
code digests. Source filenames/timestamps are not fingerprint data.

Traced inference rejects semantic global/nonlocal writes and attribute/subscript stores or
removals. This is intentionally conservative, including local-container stores when locality
is not proven. Constructors inspected as class definitions use the static projection; executed
constructors are still subject to traced resolution. Selected configuration containing another
computation mixin currently declines traced admission, avoiding frozen nested definitions.
Known input/owner receiver class constants referenced through attribute reads are refreshed.
Append-only instrumentation is rejected if its object is also semantic state anywhere in the
root/helper/observed dependency graph. Other known mutating method sites decline traced
admission when their target cannot be established as this restricted instrumentation.
Arbitrary dynamic attribute/resource state remains outside the supported boundary.

Both index and result namespaces carry the same computation metadata, so clearing by name
removes both. Table counts include index metadata. Clearing only one digest may leave orphaned
results or missing result references, which produce misses. User identity/configuration errors
still propagate; only dedicated unsupported-inference failures bypass caching.

## Independent reviews

Claude Opus 5.5 (`claude-opus-5-5`), review `ff86122b6d0f4fb8a75d89e095cd4fba`,
critiqued the owner-approved referenced-class extension. **Changed decision / unique defects:**
naive class traversal broke application exceptions, generated dataclasses/NamedTuples/Enums,
cached-property classes and strict tracing. Referenced class expansion is static-only and falls
back to qualified-name identity on UnsupportedFingerprint; it restores visited definitions,
code records and receiver bookkeeping before discarding an unsupported subtree. Class-valued
captures/configuration retain their existing rejection. **Added verification:** real reopened
SQLite tests cover method/inherited-method/constant edits and equivalent A→B→A reuse; focused
tests cover unsupported classes, shared-helper rollback and function/class cycles. The peer tried
these class kinds, native bases, STORE_ATTR methods, receiver attribute-name collisions, Dataset
inheritance, recursive graphs, custom hash definitions and source relocation. It ran the naive
patch, not the final fallback, and did not run the repository suite. Its whole-MRO allowlist concern
supports reusing the existing encoder rather than adding a new base restriction. Generated-class
fallback and the static-only limit are deliberate best-effort behavior, not complete invalidation.

Claude Opus 5.5 (`edbd7b891661425d960158b4fd7b0a2a`) found forward references at
decoration unavailable: changed decision to first-use inference. Added ordinal cycle
references, strict global settings projection, module dictionary lookup and cached-helper
composition checks. Its external-distribution version proposal was rejected for this bounded
scope: external library bodies remain an explicit limitation.

Claude Opus 5.5 (`5ffb841c8f3e4be98395b233a1cfbc7f`) tested warmed lru_cache invisibility,
thread-local collection gaps and monitoring DISABLE across threads. These added verification
and constrain the next tracing implementation. Warm lru wrappers are statically unwrapped, but traced inference declines them because their
cache hits can hide executed dependencies.
The proposed single-slot result envelope was rejected because it loses approved traced-only
A→B→A reuse; separate small manifest index and content-addressed result blobs implement that choice.
Manifest resolution must not import missing modules. Neither review certifies arbitrary
Python semantic dependencies, lazy singleton state or hidden native resources.

Claude Opus 5.5 (`f13e7f0d5d1342fa91f2517db0db1601`) found unique stale-hit defects:
receiver class constants omitted from method identity, semantic stores published under their
post-execution state, and structurally equal code objects collapsing different globals.
Real SQLite regressions reproduced all three before fixes. Runtime code records now use
object identity; immutable code projection caches remain value keyed. Added nonlocal-store,
root receiver constant, nested configured computation and name-based clearing verification.

Root review additionally reproduced a stale hit when two functions shared exact code and
module globals but captured different values: a statically covered helper hid an aliased
receiver method from observation. Runtime coverage and records now distinguish code, globals
and capture object identities; manifest resolution checks the captures as well. These identities
are only ephemeral coverage bookkeeping, never persisted fingerprints. Direct receiver method
slots undergo the same alias validation before lookup. Direct-call and `getattr` dispatch
regressions both decline admission for the unsupported alias and return current results.
Empty closure cells are legitimate on untaken branches. The collector records an absent-value
sentinel without indexing missing frame locals; resolving an empty closure declines inference.
A deterministic regression covers monitoring, manifest resolution and snapshot fallback.
