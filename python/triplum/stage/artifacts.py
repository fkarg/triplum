"""Where stage outputs live: `artifacts/<stage>/<key>/<code>/` under the cache root, one
directory per completed output, published by a single atomic rename and never replaced.

A frame is one parquet file; records are one parquet file with one JSON column; a stream is
numbered parquet batches written as the consumer pulls. Every kind ends with a `complete.json`
naming the content hash, the row count and every file's size; a lookup requires that record
and matching sizes before it fetches.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import polars as pl
from pydantic import BaseModel, ConfigDict

from triplum.cache import content_key
from triplum.utils.data import IterableDataset

Kind = Literal["frame", "records", "stream", "store"]
COMPLETE = "complete.json"


class Artifact(BaseModel):
    """A completed output: which stage, at which data key, by which code, of what kind and
    size, and where. `path` is relative to the cache root; a store effect has none."""

    model_config = ConfigDict(frozen=True)

    stage: str
    key: str
    code: str
    kind: Kind
    path: str | None
    content_hash: str
    rows: int
    bytes: int
    record_type: str | None = None


def directory(root: Path, stage: str, key: str, code: str) -> Path:
    return root / "artifacts" / stage / key / code


def _record_type(model: type[BaseModel]) -> str:
    return f"{model.__module__}:{model.__qualname__}"


def _resolve_type(name: str) -> type[BaseModel]:
    module, _, qual = name.rpartition(":")
    obj: Any = importlib.import_module(module)
    for part in qual.split("."):
        obj = getattr(obj, part)
    return obj


def _sha(paths: Sequence[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()


class Writer:
    """Writes one artifact into a temporary directory beside its final place and publishes it
    with one rename. `frame`, `records` or `add` (for a stream, repeatedly), then `finish`.
    If the final directory exists by then, the temporary one is discarded and the existing
    artifact is returned: a published artifact is never replaced."""

    def __init__(self, root: Path, stage: str, key: str) -> None:
        self.root, self.stage, self.key = root, stage, key
        parent = root / "artifacts" / stage / key
        parent.mkdir(parents=True, exist_ok=True)
        self.tmp = parent / f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.tmp.mkdir()
        self.kind: Kind | None = None
        self.rows = 0
        self.files: list[Path] = []
        self.record_type: str | None = None

    def frame(self, df: pl.DataFrame) -> None:
        self.kind = "frame"
        self.rows = df.height
        self._write_frame(self.tmp / "data.parquet", df)

    def records(self, records: Sequence[BaseModel]) -> None:
        self.kind = "records"
        self.rows = len(records)
        if records:
            self.record_type = _record_type(type(records[0]))
        self._write_frame(
            self.tmp / "data.parquet",
            pl.DataFrame(
                {"json": [r.model_dump_json() for r in records]}, schema={"json": pl.Utf8}
            ),
        )

    def add(self, batch: Sequence[BaseModel] | pl.DataFrame) -> None:
        """One batch of a stream: a list of records (one JSON column) or a frame."""
        self.kind = "stream"
        name = self.tmp / f"batch-{len(self.files):06d}.parquet"
        if isinstance(batch, pl.DataFrame):
            self.rows += batch.height
            self._write_frame(name, batch)
        else:
            if not batch:
                return
            self.record_type = self.record_type or _record_type(type(batch[0]))
            self.rows += len(batch)
            self._write_frame(
                name,
                pl.DataFrame(
                    {"json": [r.model_dump_json() for r in batch]}, schema={"json": pl.Utf8}
                ),
            )

    def _write_frame(self, path: Path, df: pl.DataFrame) -> None:
        df.write_parquet(path)
        self.files.append(path)

    def finish(self, code: str) -> Artifact:
        assert self.kind is not None, "nothing written"
        if self.kind == "stream" and not self.files:
            # an empty stream still publishes: one empty batch keeps the reader uniform
            self._write_frame(
                self.tmp / "batch-000000.parquet",
                pl.DataFrame({"json": []}, schema={"json": pl.Utf8}),
            )
        final = directory(self.root, self.stage, self.key, code)
        record = {
            "kind": self.kind,
            "content_hash": _sha(self.files),
            "rows": self.rows,
            "files": {p.name: p.stat().st_size for p in self.files},
            "record_type": self.record_type,
        }
        (self.tmp / COMPLETE).write_text(json.dumps(record, sort_keys=True))
        try:
            os.rename(self.tmp, final)
        except OSError:
            shutil.rmtree(self.tmp, ignore_errors=True)
            if not final.exists():
                raise
        art = complete(self.root, self.stage, self.key, code)
        assert art is not None
        return art

    def abort(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def complete(root: Path, stage: str, key: str, code: str) -> Artifact | None:
    """The artifact at a place if its completion record exists and every file has the size
    the record names; None otherwise."""
    d = directory(root, stage, key, code)
    rec_path = d / COMPLETE
    if not rec_path.exists():
        return None
    rec = json.loads(rec_path.read_text())
    sizes = rec["files"]
    for name, size in sizes.items():
        p = d / name
        if not p.exists() or p.stat().st_size != size:
            return None
    return Artifact(
        stage=stage,
        key=key,
        code=code,
        kind=rec["kind"],
        path=str(d.relative_to(root)),
        content_hash=rec["content_hash"],
        rows=rec["rows"],
        bytes=sum(sizes.values()),
        record_type=rec.get("record_type"),
    )


class Records[T: BaseModel](list[T]):
    """A list of records a stage produced or fetched; a plain list that can be weakly
    referenced, so the run can recognise it as an artifact when a later stage takes it."""


class Stream[T](IterableDataset[T]):
    """A published stream artifact read batch by batch, identified by its data key."""

    def __init__(self, root: Path, artifact: Artifact) -> None:
        assert artifact.path is not None
        self.artifact = artifact
        self.dir = root / artifact.path

    @property
    def artifact_key(self) -> str:
        return self.artifact.key

    @property
    def artifact_code(self) -> str | None:
        return self.artifact.code

    def __iter__(self) -> Iterator[T]:
        model = _resolve_type(self.artifact.record_type) if self.artifact.record_type else None
        for p in sorted(self.dir.glob("batch-*.parquet")):
            df = pl.read_parquet(p)
            if model is None:
                yield cast("T", df)  # a stream of frames yields frames
            else:
                for s in df["json"]:
                    yield cast("T", model.model_validate_json(s))

    def fingerprint(self) -> str:
        return content_key("artifact", self.artifact.key)


def read(root: Path, artifact: Artifact) -> Any:
    """A frame, a list of records, or a `Stream`, by kind. A store effect reads as None."""
    if artifact.kind == "store":
        return None
    assert artifact.path is not None
    d = root / artifact.path
    if artifact.kind == "frame":
        return pl.read_parquet(d / "data.parquet")
    if artifact.kind == "records":
        df = pl.read_parquet(d / "data.parquet")
        if df.height == 0:
            return Records()
        model = _resolve_type(artifact.record_type or "")
        return Records(model.model_validate_json(s) for s in df["json"])
    return Stream(root, artifact)
