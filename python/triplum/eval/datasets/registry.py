"""Every registered dataset, by name; a directory path names a local-files corpus (see
`triplum.ingest.files`). Add a source module and list its `SPECS` here."""

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
    metaqa,
    mquake,
    multihoprag,
    question_only,
    reading,
    tempo,
    wiki_multihop,
)
from triplum.eval.datasets.base import Dataset, DatasetStatus, Spec
from triplum.ingest import files

SPECS: dict[str, Spec] = {}
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
    for _spec in _module.SPECS:
        if _spec.name in SPECS:
            raise RuntimeError(f"duplicate dataset name {_spec.name}")
        SPECS[_spec.name] = _spec


def names(default_only: bool = False) -> list[str]:
    return [s.name for s in SPECS.values() if s.default or not default_only]


def is_folder(name: str) -> bool:
    return name not in SPECS and Path(name).expanduser().is_dir()


def get(name: str) -> Spec:
    if is_folder(name):
        return files.spec(Path(name))
    return SPECS[name]


def status(name: str, root: Path | None = None) -> DatasetStatus:
    return base.status(get(name), root)


def fetch(name: str, root: Path | None = None) -> dict[str, Path]:
    return base.fetch(get(name), root)


def load(name: str, n: int | None = None, root: Path | None = None) -> Dataset:
    return base.load(get(name), n, root)


def load_fixture(name: str, n: int | None = None) -> Dataset:
    return base.read_fixture(name, n)
