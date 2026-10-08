# Runtime tracing measurements

Validated traced hits cost **0.66–1.23 ms** in these local workloads after caching immutable
code metadata. They remain slower than recomputation for the short examples. The longer
arithmetic computation benefits: a traced hit takes **0.659 ms** versus **4.085 ms** uncached,
about **6.2× faster**. Ordinary static hits take approximately **39–72 µs**.

These are development measurements of the implementation, not general throughput promises.

## Reproduce and identify the implementation

```sh
uv run python scripts/benchmark_tracing.py --suite cache --traced > /tmp/traced-results.json
uv run python scripts/benchmark_tracing.py > /tmp/primitive-results.json
```

The recorded commands used `.venv/bin/python` directly because sandbox access to uv's default
cache directory was read-only. No additional benchmark dependencies are required.

- [Current traced results](tracing-performance-traced.json): full sample distributions,
  source SHA-256 hashes, UTC measurement instant, environment and parameters.
- [Initial optimized results](tracing-performance-traced-optimized-initial.json): measurements
  immediately after the optimization, before the final correctness guards.
- [Before code-metadata caching](tracing-performance-traced-before.json): comparable production
  measurements that identified repeated definition inspection as expensive.
- [Original static baseline](tracing-performance-static.json): implementation at `66fe652`,
  before automatic helper discovery and tracing.
- [Primitive monitoring results](tracing-performance-primitive.json): callback overhead alone.

The traced implementation was measured before its commit. The recorded source hashes, rather
than HEAD alone, identify it; the script rejects a run if these sources change while measuring.
After this run, `tracing.py` changed only its context-manager return annotations from `Iterator`
to `Generator[None]` and the corresponding import to satisfy the commit hook's type checker.
The raw source hash precedes that annotation-only correction; runtime behavior is unchanged.
The machine runs CPython 3.14.7 on Linux x86-64 with 18 logical CPUs. CPU affinity and frequency
are uncontrolled, so concurrent work and normal timing variation affect absolute results.

## Current production paths

Inputs and outputs are frozen `FingerprintedDataModel` records. The decorator uses automatic
computation identity, Pydantic serialization and a real temporary SQLite database. Initial
writes are flushed before timing hits. An independent temporary `PY_START` probe verifies
that a claimed hit actually skips the original computation; the probe is removed for timing.
Neither semantic globals nor the computations contain instrumentation counters.

All times below are microseconds per call. Nine samples rotate modes with three warmup calls.
Each warm path is independently calibrated toward a 50 ms sample. `timeit` disables cyclic
GC during each sample. Input construction, decoration, first-use initialization, opening the
cache and warmup are excluded from hit measurements.

| Workload | Uncached | Static hit | Traced hit | Static miss | Traced miss |
| --- | ---: | ---: | ---: | ---: | ---: |
| Normalize two words | 1.655 | 40.564 | 721.164 | 85.789 | 1,046.917 |
| Normalize 800 words | 130.089 | 72.483 | 787.969 | 292.710 | 2,879.704 |
| 10,000 arithmetic iterations | 409.458 | 40.927 | 655.659 | 480.605 | 1,238.800 |
| 100,000 arithmetic iterations | 4,085.449 | 42.401 | 659.494 | 4,175.770 | 4,923.394 |
| Dynamic input-method dispatch | 1.100 | 38.664 | 1,228.336 | 85.497 | 1,607.670 |

The dynamic-method workload calls `item.normalize()`, which calls a module-level helper,
exercising runtime-discovered dependencies. The other workloads can have empty runtime
manifests because static discovery already covers their helpers. Static and traced modes
have different invalidation guarantees; their timing comparison does not make them
interchangeable.

Misses use disjoint preconstructed inputs, 50 calls per batch and nine batches per mode,
with rotating mode order. Unique text suffixes distinguish inputs. The uncached column
uses the warm inputs; the raw miss results also include an uncached disjoint-input comparator:
2.296, 128.722, 387.002, 4,002.201 and 1.367 µs respectively. Different inputs, timer structure
and ordinary variation make these separate observations, not interchangeable overhead terms.

The writer runs concurrently during miss timing. `Cache.flush()` after each batch is timed
separately; the remaining traced drain amortizes to roughly 67–293 µs per miss in these runs.
All writes were admitted, with zero skipped writes.

## Measured optimization

The first actual benchmark found root-definition snapshots alone costing roughly 0.45–0.53 ms
for the text/arithmetic workloads. The implementation then cached immutable code digests and
disassembly in bounded 4,096-entry caches, while continuing to inspect live globals, captures
and settings. The immediate rerun showed lower absolute hit costs. Additional correctness
guards and metadata integration landed before the current final run.

These runs are not a controlled isolation of the optimization: the uncached 100,000-iteration
baseline changed from 2.682 ms before optimization to 2.323 ms in the initial optimized run,
then 4.085 ms in the final run. The final run followed test-suite completion, but that did not
restore the earlier baseline. Machine variation and implementation changes therefore prevent
attributing all before/after differences to code-metadata caching. Current measurements above
are the authoritative observations for the final recorded source hashes.

| Workload | Before caching metadata | Initial optimized run | Current implementation |
| --- | ---: | ---: | ---: |
| Normalize two words | 605.205 µs | 378.821 µs | 721.164 µs |
| Normalize 800 words | 632.361 µs | 412.559 µs | 787.969 µs |
| 10,000 arithmetic iterations | 532.778 µs | 364.544 µs | 655.659 µs |
| 100,000 arithmetic iterations | 509.668 µs | 367.994 µs | 659.494 µs |
| Dynamic input-method dispatch | 900.827 µs | 672.489 µs | 1,228.336 µs |

The script also directly times production methods, using prepared keys for reads. Component
rows are written through `Cache.put` and flushed. These isolated medians must not be summed
or subtracted to claim an exact breakdown of the whole hit.

| Component | Two words | 800 words | 100,000 iterations | Dynamic method |
| --- | ---: | ---: | ---: | ---: |
| Input `fingerprint()` | 12.973 µs | 31.964 µs | 13.356 µs | 13.021 µs |
| `SQLiteBackend.get` | 3.836 µs | 4.423 µs | 3.871 µs | 3.906 µs |
| `Cache.get` | 12.504 µs | 14.311 µs | 13.098 µs | 13.144 µs |
| `PydanticCodec.decode` | 0.815 µs | 4.277 µs | 0.838 µs | 0.816 µs |
| Root `_snapshot(compute)` | 553.083 µs | 557.940 µs | 491.934 µs | 235.937 µs |

Full traced-hit timings include actual manifest validation and both storage lookups. No
synthetic replacement stands in for those operations. Manifest-validation time is not
separately attributed. Definition inspection and hashing remain substantial costs; static
hits capture computation identity once, while traced hits validate current identity each time.

## Break-even estimate

For the 100,000-iteration workload, a simple average-cost model using the disjoint-input
comparator gives a traced hit-rate break-even near **22%** before the final batch drain:

```text
average cached cost = hit_fraction * hit_cost + (1 - hit_fraction) * miss_cost
hit_fraction > (4923.394 - 4002.201) / (4923.394 - 659.494) ≈ 0.22
```

Adding the measured remaining drain of 292.950 µs per traced miss moves this estimate to
approximately **27%**. This derives from separate measurements; it is not a measured mixed
hit-rate workload or a universal threshold. First-use initialization, process startup, cache
opening and durability guarantees beyond `flush` remain outside the estimate. Traced hits
are slower than direct computation for every shorter workload in the table, so no hit rate
makes tracing a speed win for those particular examples.

## Primitive monitoring costs and limits

The primitive suite enables interpreter-wide `PY_START` with either a no-op callback or a
callback inserting each entered code object into a set. It clears the set before each sample
and warms it before timing, modeling repeated entry to known code. It does not start other
threads. Setup/teardown is outside workload timing and measured separately.

| Workload | Baseline | No-op callback | Collect code objects |
| --- | ---: | ---: | ---: |
| 1,000 tiny Python calls | 28.533 µs | 55.537 µs (1.946×) | 90.457 µs (3.170×) |
| 10,000 loop iterations | 252.496 µs | 252.783 µs (1.001×) | 253.606 µs (1.004×) |
| Normalize 800 tokens | 69.062 µs | 90.837 µs (1.315×) | 126.222 µs (1.828×) |
| Native PBKDF2, 10,000 rounds | 1,196.063 µs | 1,196.234 µs (1.000×) | 1,195.879 µs (1.000×) |

Median full tool allocation, callback registration, activation, deactivation and release:
**9.034 µs**, over nine samples of 1,000 cycles, including the cycle function and timer loop.
Sub-percent differences in loop/native rows do not establish a speedup or reliable overhead.
The primitive suite omits frame inspection, hashing, manifest validation, serialization and
cache IO; it cannot substitute for the production measurements above.

[PEP 669](https://peps.python.org/pep-0669/#performance) explains why callback frequency and
work determine monitoring cost. The [Python monitoring API](https://docs.python.org/3.14/library/sys.monitoring.html)
documents `PY_START` and code-location disabling. This benchmark leaves observed locations
active so later invocations still receive their events.
