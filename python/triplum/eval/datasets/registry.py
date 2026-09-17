"""Every registered dataset, by name. Add a source module and list its `SPECS` here."""

from __future__ import annotations

from pathlib import Path

from triplum.eval.datasets import (
    base,
    browsecomp_plus,
    ectqa,
    extraction,
    gatemem,
    hipporag,
    long_document,
    longmemeval,
    mquake,
    multihoprag,
    question_only,
    reading,
    tempo,
    wiki_multihop,
)
from triplum.eval.datasets.base import Dataset, DatasetStatus, Spec

SPECS: dict[str, Spec] = {}
for _module in (
    hipporag,
    wiki_multihop,
    multihoprag,
    ectqa,
    reading,
    long_document,
    question_only,
    mquake,
    gatemem,
    longmemeval,
    tempo,
    extraction,
    browsecomp_plus,
):
    for _spec in _module.SPECS:
        if _spec.name in SPECS:
            raise RuntimeError(f"duplicate dataset name {_spec.name}")
        SPECS[_spec.name] = _spec


def names(default_only: bool = False) -> list[str]:
    return [s.name for s in SPECS.values() if s.default or not default_only]


def get(name: str) -> Spec:
    return SPECS[name]


def status(name: str, root: Path | None = None) -> DatasetStatus:
    return base.status(SPECS[name], root)


def fetch(name: str, root: Path | None = None) -> dict[str, Path]:
    return base.fetch(SPECS[name], root)


def load(name: str, n: int | None = None, root: Path | None = None) -> Dataset:
    return base.load(SPECS[name], n, root)


def load_fixture(name: str, n: int | None = None) -> Dataset:
    return base.read_fixture(name, n)
