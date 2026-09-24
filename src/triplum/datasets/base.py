"""Shared machinery for built-in sources.

A built-in benchmark module defines one class per source part (corpus, questions, gold
triples), each a `Dataset` or `IterableDataset` over pinned files that fetches and verifies
them on first use and identifies itself without reading them (`Pinned`). `ListSource` is the
common shape for a file that decodes to a list of records; `InlineCorpus` is the common shape
for a corpus that is the union of paragraphs shipped inside question records. An `Entry` is the
catalog metadata plus a builder from settings to a `Benchmark`.
"""

from __future__ import annotations

import json
from abc import abstractmethod
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, ClassVar

import pyarrow.parquet as pq
from pydantic import BaseModel

from triplum.bench.inputs import Benchmark
from triplum.cache import content_key
from triplum.data.corpus import RECORD_VERSION, Document
from triplum.datasets.files import File, Files
from triplum.settings import Settings
from triplum.utils.data import Dataset, IterableDataset


class Pinned:
    """Mixin for a source over pinned files: fetch and verify on first `paths()`, identity as a
    versioned recipe (class, `version`, the record contract, the pinned digests, the resolved
    parameters that change the output) with no file read. Bump `version` when what the source
    yields changes."""

    version: ClassVar[int] = 1

    def __init__(
        self,
        files: tuple[File, ...],
        settings: Settings | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.files = Files(files, settings)
        self.params = params or {}

    def paths(self) -> dict[str, Path]:
        return self.files.fetch()

    def path(self, suffix: str) -> Path:
        """The one pinned file whose name ends with `suffix`."""
        return next(p for name, p in self.paths().items() if name.endswith(suffix))

    def fingerprint(self) -> str:
        cls = type(self)
        return content_key(
            "dataset",
            {
                "class": f"{cls.__module__}.{cls.__qualname__}",
                "version": self.version,
                "contract": RECORD_VERSION,
                "files": self.files.fingerprint(),
                "params": self.params,
            },
        )


class ListSource[R, T](Pinned, Dataset[T]):
    """A pinned source whose raw records are a list decoded once on first use; `read` decodes
    the files, `record` turns one raw record into the yielded type."""

    def __init__(
        self,
        files: tuple[File, ...],
        settings: Settings | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(files, settings, params)
        self._rows: list[R] | None = None

    @abstractmethod
    def read(self, paths: dict[str, Path]) -> list[R]: ...

    @abstractmethod
    def record(self, raw: R, index: int) -> T: ...

    def rows(self) -> list[R]:
        if self._rows is None:
            self._rows = self.read(self.paths())
        return self._rows

    def __len__(self) -> int:
        return len(self.rows())

    def __getitem__(self, index: int) -> T:
        return self.record(self.rows()[index], index)


class InlineCorpus[R](Pinned, IterableDataset[Document]):
    """A corpus that is the union of passages shipped inside question records: iterate the
    records, yield each document once. The only state is the set of ids seen."""

    @abstractmethod
    def records(self, paths: dict[str, Path]) -> Iterable[R]: ...

    @abstractmethod
    def documents(self, raw: R) -> Iterable[Document]: ...

    def __iter__(self) -> Iterator[Document]:
        seen: set[str] = set()
        for raw in self.records(self.paths()):
            for d in self.documents(raw):
                if d.id not in seen:
                    seen.add(d.id)
                    yield d


class Entry(BaseModel, frozen=True):
    """Catalog metadata for one built-in benchmark and its builder; files and loading live in
    the source classes the builder composes."""

    name: str
    family: str
    licence: str
    default: bool = False
    fixture: bool = True
    needs: str | None = None  # a runner capability this dataset needs and the runner lacks
    build: Callable[[Settings], Benchmark]


# ---- helpers for sources -------------------------------------------------------------------


def titled(title: str, text: str) -> str:
    """The text of a passage document: the title on its own first line, when there is one."""
    return f"{title}\n{text}" if title else text


def passage(document_id: str, source: str, title: str, text: str, **fields: Any) -> Document:
    """A one-segment document for a titled passage; metadata defaults to the title."""
    fields.setdefault("metadata", {"title": title})
    return Document(id=document_id, source=source, text=titled(title, text), **fields)


def parquet_rows(path: Path, columns: list[str] | None = None) -> Iterator[dict]:
    """Rows of a parquet file, one row group at a time; nested columns become lists and dicts."""
    with pq.ParquetFile(path) as f:
        for batch in f.iter_batches(columns=columns):
            yield from batch.to_pylist()


def jsonl_rows(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_us(text: str, fmt: str | None = None) -> int:
    """Microseconds since the epoch for an ISO-8601 string with offset, or a naive string in `fmt`
    read as UTC."""
    from datetime import UTC, datetime

    if fmt:
        dt = datetime.strptime(text, fmt).replace(tzinfo=UTC)
    else:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)
