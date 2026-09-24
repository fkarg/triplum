"""An in-memory columnar dataset with content identity and source-native batching."""

import hashlib
from collections.abc import Iterator

import polars as pl
import pyarrow as pa
from polars.datatypes import DataTypeClass

from triplum.utils.data import IterableDataset


def _without_dictionaries(dtype: pl.DataType | DataTypeClass) -> pl.DataType | DataTypeClass:
    """Serialize dictionary values, never process-local category codes."""
    if dtype == pl.Categorical or isinstance(dtype, pl.Enum):
        return pl.String()
    if isinstance(dtype, pl.List):
        return pl.List(_without_dictionaries(dtype.inner))
    if isinstance(dtype, pl.Array):
        return pl.Array(_without_dictionaries(dtype.inner), dtype.size)
    if isinstance(dtype, pl.Struct):
        return pl.Struct({field.name: _without_dictionaries(field.dtype) for field in dtype.fields})
    return dtype


class FrameDataset(IterableDataset[pl.DataFrame]):
    """Yield slices of a frame. Identity includes schema and ordered rows, not batch size.

    The frame is already materialized; identity is recomputed so edits to it cannot reuse a
    stale digest. Iterating or hashing never consumes the other operation's state.
    """

    def __init__(self, frame: pl.DataFrame, *, batch_size: int = 1024) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.frame = frame
        self.batch_size = batch_size

    def __iter__(self) -> Iterator[pl.DataFrame]:
        yield from self.frame.iter_slices(self.batch_size)

    def fingerprint(self) -> str:
        digest = hashlib.sha256(b"triplum.frame.ipc.v1\0")
        # Fixed serialization slices are independent of loading and physical chunk boundaries.
        # Include an empty slice to distinguish schemas even when there are no rows.
        digest.update(self.frame.head(0).to_arrow().schema.serialize())
        logical_schema = pl.Schema(
            {name: _without_dictionaries(dtype) for name, dtype in self.frame.schema.items()}
        )
        for batch in self.frame.iter_slices(1024):
            table = batch.cast(logical_schema).to_arrow()
            # Rebuild buffers from Arrow scalars: rechunking alone retains physical
            # offsets/null payloads. Arrow scalars preserve nanoseconds, unlike Python rows.
            canonical = pa.record_batch(
                [pa.array(list(column), type=column.type) for column in table],
                schema=table.schema,
            )
            digest.update(canonical.serialize())
        return digest.hexdigest()
