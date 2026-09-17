# utils.data: datasets and loaders

Snapshot: 2026-09-17. Dataset records are chosen by their author; no task tables are mandatory.
Implement `Dataset` for indexed access or `IterableDataset` for streaming. `DataLoader` also
accepts ordinary iterables, batches lazily, and supports custom collation. Use `batch_size=None`
to preserve native batches. One-shot sources remain one-shot; the loader does not manufacture
replay, snapshot identity or random access.

::: triplum.utils.data.dataset

::: triplum.utils.data.loader
