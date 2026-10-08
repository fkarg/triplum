# Runtime tracing measurements

This development record measures monitoring primitives before integrating automatic
dependency discovery. These are local measurements, not a promise about cache performance.

## Reproduce

```sh
uv run python scripts/benchmark_tracing.py > /tmp/tracing-results.json
```

The checked-in [raw primitive results](tracing-performance-primitive.json) include the
environment, UTC measurement instant, parameters, per-sample timings and medians. The
recorded run used the checkout's `.venv/bin/python` directly because sandbox access to
uv's default cache directory was read-only.

Each workload is calibrated to approximately 50 ms per baseline sample. Nine samples
rotate the three modes to reduce order bias, with three warmup calls per mode. `timeit`
disables cyclic garbage collection during timing. Registration and event activation
happen outside workload timing; a separate measurement includes tool allocation,
callback registration, activation, deactivation and release.

The collection callback inserts the entered code object into a set on every `PY_START`.
The set is cleared before each mode sample and populated during warmup. This models
repeated steady-state discovery of the same code, not a growing workload with many
new definitions. All instrumentation is interpreter-wide; the isolated script does
not start other threads. It checks that each mode returns the baseline result.

## Primitive results

CPython 3.14.7, Linux x86-64, 18 logical CPUs. Absolute times are microseconds per
complete workload invocation; ratios compare median timings with the baseline median.

| Workload | Baseline | No-op callback | Collect code objects |
| --- | ---: | ---: | ---: |
| 1,000 tiny Python calls | 28.533 | 55.537 (1.946×) | 90.457 (3.170×) |
| 10,000 arithmetic loop iterations | 252.496 | 252.783 (1.001×) | 253.606 (1.004×) |
| Normalize 800 text tokens with a Python helper | 69.062 | 90.837 (1.315×) | 126.222 (1.828×) |
| Native PBKDF2, 10,000 rounds | 1,196.063 | 1,196.234 (1.000×) | 1,195.879 (1.000×) |

Median full setup/teardown cycle: **9.034 µs**, measured separately over nine
samples of 1,000 cycles. This includes the cycle function invocation and timer loop.

The call-heavy workload adds approximately 62 µs per 1,000 helper calls when collecting
code objects. Tiny differences in the loop/native rows do not establish a speedup or a
reliable sub-percent overhead estimate. This run uses no CPU affinity or frequency
control, and concurrent machine activity can affect timings.

## What remains to measure

This benchmark does not hash definitions, resolve dependency identities, inspect frames,
validate manifests, serialize results or access a cache. Actual implementation measurements
must distinguish traced misses, validated hits, ordinary cache hits and uncached execution.
The primitive numbers cannot establish the final break-even point.

[PEP 669](https://peps.python.org/pep-0669/#performance) explains why callback frequency
and work determine monitoring cost. The
[Python monitoring API](https://docs.python.org/3.14/library/sys.monitoring.html)
documents `PY_START`, per-interpreter activation and code-location disabling. This
benchmark deliberately does not disable already-observed locations: discovery for another
invocation must still receive its events.
