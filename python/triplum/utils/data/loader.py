"""Lazy batching and customizable collation, independent of domain schemas."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from itertools import islice
from typing import cast, overload

from .dataset import Dataset


class DataLoader[T, B]:
    """Consume a source lazily, yielding lists or batches made by ``collate_fn``.

    ``batch_size=None`` passes through source items unchanged, including native batches.
    The loader neither prefetches nor replays a one-shot iterator. It keeps the final
    partial batch and lets source and collator exceptions propagate.
    """

    @overload
    def __init__(
        self: DataLoader[T, list[T]],
        dataset: Iterable[T],
        *,
        batch_size: int = 1,
        collate_fn: None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: DataLoader[T, T],
        dataset: Iterable[T],
        *,
        batch_size: None,
        collate_fn: None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        dataset: Iterable[T],
        *,
        batch_size: int = 1,
        collate_fn: Callable[[list[T]], B],
    ) -> None: ...

    def __init__(
        self,
        dataset: Iterable[T],
        *,
        batch_size: int | None = 1,
        collate_fn: Callable[[list[T]], B] | None = None,
    ) -> None:
        if batch_size is not None and (isinstance(batch_size, bool) or batch_size < 1):
            raise ValueError("batch_size must be a positive integer or None")
        if batch_size is None and collate_fn is not None:
            raise ValueError("collate_fn requires automatic batching")
        self.dataset = dataset
        self.batch_size = batch_size
        self.collate_fn = collate_fn

    def __iter__(self) -> Iterator[B]:
        # Constructor overloads tie B to T for pass-through and list[T] for default collation.
        if self.batch_size is None:
            for item in self.dataset:
                yield cast(B, item)
            return
        if isinstance(self.dataset, Dataset):
            for start in range(0, len(self.dataset), self.batch_size):
                indices = list(range(start, min(start + self.batch_size, len(self.dataset))))
                items = self.dataset.__getitems__(indices)
                yield self.collate_fn(items) if self.collate_fn is not None else cast(B, items)
        else:
            source = iter(self.dataset)
            while items := list(islice(source, self.batch_size)):
                yield self.collate_fn(items) if self.collate_fn is not None else cast(B, items)
