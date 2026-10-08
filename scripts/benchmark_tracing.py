"""Measure PY_START instrumentation or production SQLite cache paths.

Run with ``uv run python scripts/benchmark_tracing.py > tracing-results.json``.
Modes rotate between repeats. Setup is outside workload timing and measured separately.
Select production cache timings with ``--suite cache``.
"""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import timeit
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from types import CodeType, FunctionType

from pydantic import ConfigDict

from triplum.cache import Cache, CacheKey, PydanticCodec, SQLiteBackend, cached
from triplum.datatype import FingerprintedDataModel


class TextInput(FingerprintedDataModel):
    model_config = ConfigDict(frozen=True)
    text: str
    rounds: int = 0

    def normalize(self) -> str:
        return normalize_word(self.text)


class TextOutput(FingerprintedDataModel):
    model_config = ConfigDict(frozen=True)
    text: str


def cached_text_transform(item: TextInput) -> TextOutput:
    return TextOutput(text=" ".join(normalize_word(word) for word in item.text.split()))


def cached_compute_heavy(item: TextInput) -> TextOutput:
    total = 0
    for index in range(item.rounds):
        total += index % 13
    return TextOutput(text=f"{item.text.casefold()}:{total}")


def cached_dynamic_dispatch(item: TextInput) -> TextOutput:
    return TextOutput(text=item.normalize())


def measure_calls(
    calls: dict[str, Callable[[], object]], repeat: int, warmup: int, target_ms: float
) -> dict[str, dict[str, object]]:
    """Time real operations independently, retaining their complete sample distributions."""
    timers = {name: timeit.Timer(call) for name, call in calls.items()}
    numbers = {}
    samples: dict[str, list[float]] = {name: [] for name in calls}
    for name, call in calls.items():
        for _ in range(warmup):
            call()
        probe_seconds = timers[name].timeit(number=10) / 10
        numbers[name] = max(1, int(target_ms / 1_000 / probe_seconds))
    names = tuple(calls)
    for index in range(repeat):
        for name in names[index % len(names) :] + names[: index % len(names)]:
            for _ in range(warmup):
                calls[name]()
            number = numbers[name]
            samples[name].append(timers[name].timeit(number=number) * 1e9 / number)
    return {
        name: {
            "iterations_per_sample": numbers[name],
            "median_ns": statistics.median(values),
            "median_us": statistics.median(values) / 1_000,
            "samples_ns": values,
        }
        for name, values in samples.items()
    }


def assert_cached_hit(
    compute: FunctionType, wrapped: Callable[[TextInput], TextOutput], item: TextInput
) -> None:
    """Verify that a measured hit really skips execution, without mutating the computation."""
    monitoring = sys.monitoring
    tool_id = next(value for value in range(6) if value != 4 and monitoring.get_tool(value) is None)
    entries = []

    def observe(code: CodeType, offset: int) -> None:
        entries.append(code)

    monitoring.use_tool_id(tool_id, "benchmark-hit-verification")
    try:
        monitoring.register_callback(tool_id, monitoring.events.PY_START, observe)
        monitoring.set_local_events(tool_id, compute.__code__, monitoring.events.PY_START)
        wrapped(item)
    finally:
        monitoring.free_tool_id(tool_id)
    assert not entries, "claimed cache hit executed the underlying computation"


def measure_misses(
    calls: dict[str, Callable[[TextInput], TextOutput]],
    item: TextInput,
    cache: Cache,
    repeat: int,
    batch_size: int,
) -> dict[str, dict[str, object]]:
    samples: dict[str, list[float]] = {name: [] for name in calls}
    flush_samples: dict[str, list[float]] = {name: [] for name in calls}
    names = tuple(calls)
    for index in range(repeat):
        for name in names[index % len(names) :] + names[: index % len(names)]:
            inputs = [
                item.model_copy(update={"text": f"{item.text} miss-{name}-{index}-{number}"})
                for number in range(batch_size)
            ]
            compute = calls[name]

            def batch(
                inputs: list[TextInput] = inputs,
                compute: Callable[[TextInput], TextOutput] = compute,
            ) -> None:
                for fresh_item in inputs:
                    compute(fresh_item)

            samples[name].append(timeit.Timer(batch).timeit(number=1) * 1e9 / batch_size)
            flush_samples[name].append(
                timeit.Timer(cache.flush).timeit(number=1) * 1e9 / batch_size
            )
    return {
        name: {
            "iterations_per_sample": batch_size,
            "median_ns": statistics.median(values),
            "median_us": statistics.median(values) / 1_000,
            "samples_ns": values,
            "flush_amortized_median_us": statistics.median(flush_samples[name]) / 1_000,
            "flush_amortized_samples_ns": flush_samples[name],
        }
        for name, values in samples.items()
    }


def benchmark_cache(
    repeat: int, warmup: int, target_ms: float, traced: bool, miss_batch: int
) -> dict[str, object]:
    workloads = {
        "tiny_text": (cached_text_transform, TextInput(text="Alpha, beta!")),
        "text_800_words": (cached_text_transform, TextInput(text=TEXT)),
        "compute_10000_iterations": (
            cached_compute_heavy,
            TextInput(text="Alpha", rounds=10_000),
        ),
        "compute_100000_iterations": (
            cached_compute_heavy,
            TextInput(text="Alpha", rounds=100_000),
        ),
        "dynamic_method_dispatch": (cached_dynamic_dispatch, TextInput(text="Alpha!")),
    }
    results = {}
    with TemporaryDirectory(prefix="triplum-benchmark-") as directory:
        backend = SQLiteBackend(Path(directory) / "cache.sqlite")
        with Cache(backend) as cache:
            for name, (compute, item) in workloads.items():
                wrapped = cached(compute, cache=cache)
                traced_wrapped = (
                    cached(compute, cache=cache, dependency_mode="traced") if traced else None
                )
                expected = compute(item)
                assert wrapped(item) == expected
                if traced_wrapped is not None:
                    assert traced_wrapped(item) == expected
                cache.flush()
                assert wrapped(item) == expected
                assert_cached_hit(compute, wrapped, item)
                if traced_wrapped is not None:
                    assert traced_wrapped(item) == expected
                    assert_cached_hit(compute, traced_wrapped, item)
                codec = PydanticCodec(TextOutput)
                payload = codec.encode(expected)
                # A separate real row supports component timing without relying on private
                # decorator identity implementation. Key calculation is outside get timing.
                key = CacheKey(bytes.fromhex("11" * 32), bytes.fromhex(item.fingerprint()))
                assert cache.put(key, payload)
                cache.flush()
                assert backend.get(key) == payload
                calls: dict[str, Callable[[], object]] = {
                    "uncached": partial(compute, item),
                    "static_hit": partial(wrapped, item),
                }
                if traced_wrapped is not None:
                    calls["traced_hit"] = partial(traced_wrapped, item)
                paths = measure_calls(calls, repeat, warmup, target_ms)
                component_calls: dict[str, Callable[[], object]] = {
                    "input_fingerprint": item.fingerprint,
                    "sqlite_get_precomputed_key": partial(backend.get, key),
                    "cache_get_precomputed_key": partial(cache.get, key),
                    "pydantic_decode": partial(codec.decode, payload),
                }
                if traced:
                    from triplum.utils.fingerprint import _snapshot

                    component_calls["root_definition_snapshot"] = partial(_snapshot, compute)
                components = measure_calls(component_calls, repeat, warmup, target_ms)
                assert wrapped(item) == expected
                misses = {}
                if traced_wrapped is not None:
                    assert_cached_hit(compute, traced_wrapped, item)
                    misses = measure_misses(
                        {
                            "uncached": compute,
                            "static_miss": wrapped,
                            "traced_miss": traced_wrapped,
                        },
                        item,
                        cache,
                        repeat,
                        miss_batch,
                    )
                assert cache.skipped_writes == 0
                results[name] = {
                    "input_utf8_bytes": len(item.text.encode()),
                    "output_payload_bytes": len(payload),
                    "paths": paths,
                    "components": components,
                    "misses": misses,
                }
    return {
        "workloads": results,
        "method": {
            "storage": "real temporary SQLite; admitted writes flushed before timing hits",
            "identity": "default automatic computation identity; no explicit process_id",
            "mode_order": "rotated each repeat; independent calibration per path",
            "gc": "disabled by timeit during each sample",
            "components": "actual production methods measured independently; not additive estimates",
            "exclusions": "decoration, first-use initialization, DB open and writes excluded from hits",
            "misses": "disjoint prebuilt inputs; writer runs concurrently; flush separately timed",
            "hit_verification": "PY_START on original compute must receive zero entries",
        },
    }


def increment(value: int) -> int:
    return value + 1


def call_heavy() -> int:
    value = 0
    for _ in range(1_000):
        value = increment(value)
    return value


def loop_heavy() -> int:
    value = 0
    for index in range(10_000):
        value += index % 13
    return value


TEXT = "Alpha, beta! Gamma delta? document retrieval and caching. " * 100


def normalize_word(word: str) -> str:
    return word.strip(",.!?").casefold()


def text_transform() -> list[str]:
    return [normalize_word(word) for word in TEXT.split()]


def native_heavy() -> bytes:
    return hashlib.pbkdf2_hmac("sha256", b"benchmark", b"fixed-salt", 10_000)


def noop(code: CodeType, offset: int) -> None:
    pass


SEEN: set[CodeType] = set()


def collect(code: CodeType, offset: int) -> None:
    SEEN.add(code)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("primitive", "cache"), default="primitive")
    parser.add_argument(
        "--traced", action="store_true", help="include production traced hits/misses"
    )
    parser.add_argument("--miss-batch", type=int, default=50)
    parser.add_argument("--repeat", type=int, default=9)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--target-ms", type=float, default=50)
    args = parser.parse_args()
    if args.repeat < 3 or args.warmup < 1 or args.target_ms <= 0 or args.miss_batch < 1:
        parser.error("repeat must be >= 3, warmup >= 1, target-ms > 0 and miss-batch >= 1")

    if args.suite == "cache":
        source_paths = [
            Path(__file__),
            *Path("src/triplum/cache").glob("*.py"),
            Path("src/triplum/utils/fingerprint.py"),
            Path("src/triplum/datatype/fingerprint.py"),
        ]
        source_hashes = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths
        }
        report = benchmark_cache(
            args.repeat, args.warmup, args.target_ms, args.traced, args.miss_batch
        )
        assert source_hashes == {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths
        }, "source files changed during measurement; rerun against a stable implementation"
        report.update(
            measured_at_utc=datetime.now(UTC).isoformat(),
            environment={
                "python": sys.version,
                "platform": platform.platform(),
                "logical_cpus": os.cpu_count(),
                "git_head": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
            },
            parameters=vars(args),
            source_sha256=source_hashes,
        )
        print(json.dumps(report, indent=2))
        return

    monitoring = sys.monitoring
    tool_id = next((value for value in range(6) if monitoring.get_tool(value) is None), None)
    if tool_id is None:
        parser.error("no free sys.monitoring tool ID")
    event = monitoring.events.PY_START
    workloads: dict[str, Callable[[], object]] = {
        "call_heavy_1000_calls": call_heavy,
        "loop_heavy_10000_iterations": loop_heavy,
        "text_transform_800_words": text_transform,
        "native_pbkdf2_10000_rounds": native_heavy,
    }
    modes = ("baseline", "noop", "collect")
    results = {}
    monitoring.use_tool_id(tool_id, "triplum-tracing-benchmark")
    try:
        for name, workload in workloads.items():
            timer = timeit.Timer(workload)
            expected = workload()
            for _ in range(args.warmup):
                workload()
            probe_seconds = timer.timeit(number=10) / 10
            number = max(1, int(args.target_ms / 1_000 / probe_seconds))
            samples: dict[str, list[float]] = {mode: [] for mode in modes}
            for repeat in range(args.repeat):
                rotated_modes = modes[repeat % len(modes) :] + modes[: repeat % len(modes)]
                for mode in rotated_modes:
                    SEEN.clear()
                    if mode != "baseline":
                        monitoring.register_callback(
                            tool_id, event, noop if mode == "noop" else collect
                        )
                        monitoring.set_events(tool_id, event)
                    try:
                        for _ in range(args.warmup):
                            assert workload() == expected
                        samples[mode].append(timer.timeit(number=number) * 1e9 / number)
                    finally:
                        monitoring.set_events(tool_id, monitoring.events.NO_EVENTS)
            baseline = statistics.median(samples["baseline"])
            results[name] = {
                "iterations_per_sample": number,
                "modes": {
                    mode: {
                        "median_ns": statistics.median(values),
                        "median_us": statistics.median(values) / 1_000,
                        "ratio_to_baseline": statistics.median(values) / baseline,
                        "samples_ns": values,
                    }
                    for mode, values in samples.items()
                },
            }
    finally:
        monitoring.free_tool_id(tool_id)

    def setup_teardown() -> None:
        monitoring.use_tool_id(tool_id, "triplum-tracing-benchmark")
        monitoring.register_callback(tool_id, event, noop)
        monitoring.set_events(tool_id, event)
        monitoring.set_events(tool_id, monitoring.events.NO_EVENTS)
        monitoring.free_tool_id(tool_id)

    timer = timeit.Timer(setup_teardown)
    for _ in range(args.warmup):
        setup_teardown()
    setup_samples = [
        value * 1e9 / 1_000 for value in timer.repeat(repeat=args.repeat, number=1_000)
    ]
    report = {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "environment": {
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
        "parameters": vars(args),
        "method": {
            "event": "PY_START",
            "gc": "disabled by timeit during each sample",
            "mode_order": "rotated each repeat",
            "collection": "set of code objects, cleared before each mode sample",
            "timing": "setup excluded; timeit loop and workload invocation included",
            "scope": "primitive callbacks only; no hashing, manifest validation or cache IO",
        },
        "workloads": results,
        "setup_teardown": {
            "iterations_per_sample": 1_000,
            "median_ns": statistics.median(setup_samples),
            "median_us": statistics.median(setup_samples) / 1_000,
            "samples_ns": setup_samples,
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
