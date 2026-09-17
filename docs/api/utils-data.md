# utils.data: datasets and loaders

Snapshot: 2026-09-17. Dataset records are chosen by their author; no task tables are mandatory.
Implement `Dataset` for indexed access or `IterableDataset` for streaming. `DataLoader` also
accepts ordinary iterables, batches lazily, and supports custom collation. Use `batch_size=None`
to preserve native batches. One-shot sources remain one-shot; the loader does not manufacture
replay, snapshot identity or random access.

Both dataset base classes require `fingerprint() -> str`. Implement it from the logical data
revision and transformations, without consuming the stream. The fingerprint must change when
ordered records change; loader batch size is not part of identity. Plain iterables remain valid
loader inputs without this hook. `triplum.datasets.FrameDataset` hashes an in-memory frame.

```python
from itertools import count
from triplum.utils.data import DataLoader, IterableDataset


class Integers(IterableDataset[int]):
    def __iter__(self):
        return count()

    def fingerprint(self) -> str:
        return "integers:start=0:step=1:v1"


loader = DataLoader(Integers(), batch_size=3)
assert next(iter(loader)) == [0, 1, 2]
```

This is a streaming interface, not an end-to-end streaming benchmark runner. Current benchmark
algorithms explicitly materialize finite inputs through `triplum.bench.inputs.materialize`.

::: triplum.utils.data.dataset

::: triplum.utils.data.loader
