"""The context a stage runs in: the run store that records invocations, the cache root that
holds artifacts, and the replicate's seed. Set by the runner around a pipeline; a stage called
with no context runs its function directly and records nothing."""

from __future__ import annotations

import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from triplum.bench.runstore import RunStore


@dataclass(frozen=True)
class Run:
    store: RunStore
    root: Path
    run_id: str
    seed: int
    replicate: int = 0
    # The frames and record lists stages produced or fetched in this run, by object identity,
    # so a downstream stage sees them as the artifacts they are rather than as bare content.
    produced: dict[int, tuple[weakref.ref, str, str]] = field(default_factory=dict)

    def register(self, obj: Any, key: str, code: str) -> None:
        self.produced[id(obj)] = (weakref.ref(obj), key, code)

    def produced_by(self, obj: Any) -> tuple[str, str] | None:
        """(key, code) if the object is an artifact of this run."""
        entry = self.produced.get(id(obj))
        if entry is None or entry[0]() is not obj:
            return None
        return entry[1], entry[2]


_current: ContextVar[Run | None] = ContextVar("triplum_run", default=None)
_seed: ContextVar[int | None] = ContextVar("triplum_stage_seed", default=None)


def current() -> Run | None:
    return _current.get()


def stage_seed() -> int:
    """The derived seed of the stage being executed, for a stage seeded through an adapter
    argument rather than a `seed` parameter; 0 outside a seeded stage."""
    seed = _seed.get()
    return 0 if seed is None else seed


@contextmanager
def seeded(seed: int | None) -> Iterator[None]:
    token = _seed.set(seed)
    try:
        yield
    finally:
        _seed.reset(token)


@contextmanager
def active(run: Run) -> Iterator[Run]:
    token = _current.set(run)
    try:
        yield run
    finally:
        _current.reset(token)
