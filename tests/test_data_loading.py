"""Custom sources need only access methods; loading is lazy and task agnostic."""

from collections.abc import Iterator
from itertools import count, islice

import polars as pl
import pytest
from triplum.utils.data import DataLoader, Dataset, IterableDataset


class Words(Dataset[str]):
    def __len__(self) -> int:
        return 3

    def __getitem__(self, index: int) -> str:
        return ("alpha", "beta", "gamma")[index]


class Numbers(IterableDataset[int]):
    def __iter__(self) -> Iterator[int]:
        yield from count()


def test_indexed_dataset_and_partial_last_batch():
    words = Words()
    assert words[1] == "beta"
    assert list(words) == ["alpha", "beta", "gamma"]
    assert list(DataLoader(words, batch_size=2)) == [["alpha", "beta"], ["gamma"]]


def test_infinite_stream_needs_neither_length_nor_indexing():
    loader = DataLoader(Numbers(), batch_size=3)
    assert list(islice(loader, 2)) == [[0, 1, 2], [3, 4, 5]]
    assert next(iter(loader)) == [0, 1, 2]


def test_one_shot_generator_is_consumed_only_when_requested_without_lookahead():
    source = iter(range(7))
    loader = DataLoader(source, batch_size=2)
    assert next(source) == 0  # construction did not pull
    batches = iter(loader)
    assert next(batches) == [1, 2]
    assert next(source) == 3  # no prefetch
    assert list(batches) == [[4, 5], [6]]
    assert list(loader) == []  # loaders do not invent replay


def test_custom_collation_can_make_columnar_batches():
    def collate(items: list[str]) -> pl.DataFrame:
        return pl.DataFrame({"text": items})

    frames = list(DataLoader(Words(), batch_size=2, collate_fn=collate))
    assert [f.to_dicts() for f in frames] == [
        [{"text": "alpha"}, {"text": "beta"}],
        [{"text": "gamma"}],
    ]


def test_native_batches_pass_through_without_copying():
    frame = pl.DataFrame({"text": ["hello"]})
    assert next(iter(DataLoader([frame], batch_size=None))) is frame


def test_empty_source_and_source_errors_are_preserved():
    assert list(DataLoader([], batch_size=2)) == []

    def source():
        yield "first"
        raise RuntimeError("source failed")

    batches = iter(DataLoader(source(), batch_size=1))
    assert next(batches) == ["first"]
    with pytest.raises(RuntimeError, match="source failed"):
        next(batches)


@pytest.mark.parametrize("size", [0, -1])
def test_invalid_batch_size_is_rejected(size):
    with pytest.raises(ValueError, match="batch_size"):
        DataLoader([], batch_size=size)


def test_indexed_bulk_read_can_be_overridden():
    class BulkWords(Words):
        def __getitems__(self, indices: list[int]) -> list[str]:
            return [super(BulkWords, self).__getitem__(i).upper() for i in indices]

    assert list(DataLoader(BulkWords(), batch_size=2)) == [["ALPHA", "BETA"], ["GAMMA"]]
