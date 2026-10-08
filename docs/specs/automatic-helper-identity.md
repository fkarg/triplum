# Automatic computation dependencies

Owner approves static default plus optional traced discovery, without manual dependency lists.
Static discovery is implemented for review; the optional traced interface below is the next
implementation checkpoint and is not yet available.

## Interface

`cached(..., dependency_mode: Literal["static", "traced"] = "static")`
and the same keyword on `CachedStep.__init__`. Data identity remains unchanged. Existing
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
on exact lists/sets may be excluded when there are no other reads. Arbitrary class/input method
calls and semantic global mutation are outside static discovery. Unsupported
semantic projections raise TypeError in static mode; traced mode will bypass only dedicated
unsupported-dependency failures, preserving exceptions from user fingerprint implementations. External functions stop at
qualified-name boundary; external implementation changes are not covered. Class/data schemas
remain outside this bounded inference. Keep frozen bindings/settings unchanged after first use.

## Traced discovery and storage

On a miss, use sys.monitoring PY_START to collect executed application code objects only;
do not hash, serialize, or write cache inside callbacks. One installed tool and thread-local
collection scopes coordinate concurrent callers. If the tool is unavailable, compute uncached.
Resolve observed functions afterwards through module/class dictionaries. Nested code already
contained in known definitions is covered. Unresolvable application code disables admission.
Collecting runtime code supplements static identity; it does not infer native implementation,
files, services, hidden resource state or arbitrary dispatch effects.

A preliminary root computation fingerprint plus full input fingerprint addresses a small
manifest index using the existing CacheBackend get/put_many abstraction. Each manifest lists
resolvable function paths and their observed definition fingerprints. Validate candidates against
current definitions before any result hit. Full actual process identity includes root identity
and manifest; results live under that computation/input pair. A→B→A retains old result blobs.
No schema expansion or migration layer. Index updates losing concurrent variants cause misses,
not incorrect hits. Missing result blobs also cause misses. Candidate validation is proportional
to retained variants/dependencies, not constant-time. Per-input indexes constrain unrelated
branch growth; shared-per-root indexes could reduce metadata but amplify candidate sets.

Traced mode refreshes the root settings projection at each lookup. Unknown root state,
unknown application dependencies, unavailable tracing, or unresolvable
stored manifests cause recomputation without admission. Ordinary exceptions propagate and
tracing is released. Cached child calls must contribute their dependency manifest to parent
traces even on hits. No explicit dependency list or manually maintained version counter.

## Limits

This is bounded invalidation, not proof that an arbitrary Python execution is pure. Captured or
global state determining dynamic dispatch must enter the static projection; resources requiring
external identity need fingerprintable settings. Python interpreter/compiler changes can alter
code digests. Source filenames/timestamps are not fingerprint data.

## Independent reviews

Claude Opus 5.5 (`edbd7b891661425d960158b4fd7b0a2a`) found forward references at
decoration unavailable: changed decision to first-use inference. Added ordinal cycle
references, strict global settings projection, module dictionary lookup and cached-helper
composition checks. Its external-distribution version proposal was rejected for this bounded
scope: external library bodies remain an explicit limitation.

Claude Opus 5.5 (`5ffb841c8f3e4be98395b233a1cfbc7f`) tested warmed lru_cache invisibility,
thread-local collection gaps and monitoring DISABLE across threads. These added verification
and constrain the next tracing implementation. Warm lru wrappers are statically unwrapped.
The proposed single-slot result envelope was rejected because it loses approved traced-only
A→B→A reuse; separate small manifest index and content-addressed result blobs remain planned.
Manifest resolution must not import missing modules. Neither review certifies arbitrary
Python semantic dependencies, lazy singleton state or hidden native resources.
