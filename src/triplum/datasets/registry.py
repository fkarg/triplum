"""Every built-in benchmark, by name; a directory path names a local-files corpus (see
`triplum.ingest.files`). Add a source module and list its `ENTRIES` here. An entry is metadata
plus a builder; the source classes it composes own their files, loading and identity."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from triplum.bench.inputs import Benchmark, PreparedBenchmark, materialize
from triplum.datasets import (
    browsecomp_plus,
    ectqa,
    extraction,
    fixtures,
    gatemem,
    hipporag,
    long_document,
    longmemeval,
    metaqa,
    mquake,
    multihoprag,
    question_only,
    reading,
    tempo,
    wiki_multihop,
)
from triplum.datasets.base import Entry, Pinned
from triplum.datasets.files import File, Files, State
from triplum.ingest import files
from triplum.settings import Settings
from triplum.utils.data import Take

ENTRIES: dict[str, Entry] = {}
for _module in (
    hipporag,
    wiki_multihop,
    multihoprag,
    ectqa,
    reading,
    long_document,
    question_only,
    metaqa,
    mquake,
    gatemem,
    longmemeval,
    tempo,
    extraction,
    browsecomp_plus,
):
    for _entry in _module.ENTRIES:
        if _entry.name in ENTRIES:
            raise RuntimeError(f"duplicate dataset name {_entry.name}")
        ENTRIES[_entry.name] = _entry


def names(default_only: bool = False) -> list[str]:
    return [e.name for e in ENTRIES.values() if e.default or not default_only]


def is_folder(name: str) -> bool:
    return name not in ENTRIES and Path(name).expanduser().is_dir()


def get(name: str) -> Entry:
    if is_folder(name):
        return files.entry(Path(name))
    return ENTRIES[name]


def build(name: str, settings: Settings | None = None) -> Benchmark:
    """The benchmark composition, unread: every part is lazy."""
    entry = get(name)
    return replace(entry.build(settings or Settings()), name=entry.name, needs=entry.needs)


def pinned(name: str, settings: Settings | None = None) -> Files:
    """The union of the pinned files behind a benchmark's parts (a folder has none)."""
    seen: dict[str, File] = {}
    for part in (b := build(name, settings)).corpus, b.qa, b.extraction:
        if isinstance(part, Pinned):
            for f in part.files.files:
                seen.setdefault(f.name, f)
    return Files(tuple(seen.values()), settings)


def status(name: str, settings: Settings | None = None) -> State:
    return pinned(name, settings).status()


def fetch(name: str, settings: Settings | None = None) -> dict[str, Path]:
    return pinned(name, settings).fetch()


def load(name: str, n: int | None = None, settings: Settings | None = None) -> Benchmark:
    """The benchmark with the first `n` questions selected; the corpus is never truncated."""
    benchmark = build(name, settings)
    if n is not None and benchmark.qa is not None:
        benchmark = replace(benchmark, qa=Take(benchmark.qa, n))
    return benchmark


def load_fixture(name: str, n: int | None = None) -> Benchmark:
    return replace(fixtures.read(name, n), needs=get(name).needs)


def verify(name: str, settings: Settings | None = None) -> PreparedBenchmark:
    """Read the whole dataset and run every integrity check (`bench.inputs.check`); raises
    `GoldMappingError` on the first failure."""
    return materialize(load(name, settings=settings))
