"""Sources own access and identity; loading is lazy and task agnostic."""

from collections.abc import Iterator
from itertools import count, islice
from pathlib import Path

import polars as pl
import pytest
from triplum.utils.data import DataLoader, Dataset, IterableDataset


class Words(Dataset[str]):
    def fingerprint(self) -> str:
        return "words:alpha-beta-gamma:v1"

    def __len__(self) -> int:
        return 3

    def __getitem__(self, index: int) -> str:
        return ("alpha", "beta", "gamma")[index]


class Numbers(IterableDataset[int]):
    def fingerprint(self) -> str:
        return "natural-numbers:start=0:step=1"

    def __iter__(self) -> Iterator[int]:
        yield from count()


def test_documented_streaming_example():
    page = (Path(__file__).parents[1] / "docs/api/utils-data.md").read_text()
    example = page.split("```python\n", 1)[1].split("```", 1)[0]
    exec(compile(example, "docs/api/utils-data.md", "exec"), {})  # noqa: S102 - repository-owned example


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


def test_dataset_identity_is_required():
    import inspect

    class Unidentified(IterableDataset[int]):
        def __iter__(self) -> Iterator[int]:
            yield 1

    assert inspect.isabstract(Unidentified)


def test_frame_dataset_owns_identity_independent_of_batch_size():
    from triplum.datasets.frames import FrameDataset

    frame = pl.DataFrame({"text": ["A", "B", "C"]})
    small = FrameDataset(frame, batch_size=1)
    large = FrameDataset(frame, batch_size=3)
    assert small.fingerprint() == large.fingerprint()
    assert small.fingerprint() != FrameDataset(frame.reverse()).fingerprint()
    assert (
        small.fingerprint()
        != FrameDataset(frame.with_columns(pl.lit("changed").alias("text"))).fingerprint()
    )
    assert pl.concat(list(small)).equals(frame)


@pytest.mark.parametrize("indexed", [False, True])
def test_falsy_callable_is_still_used_for_collation(indexed):
    # The loader used truthiness to choose collation, silently returning the wrong batch type.
    class Collate:
        def __bool__(self) -> bool:
            return False

        def __call__(self, items: list[str]) -> str:
            return "/".join(items)

    source = Words() if indexed else iter(Words())
    assert list(DataLoader(source, batch_size=2, collate_fn=Collate())) == ["alpha/beta", "gamma"]


def test_frame_fingerprint_preserves_binary_temporal_nested_and_nanosecond_values():
    # Python row conversion is lossy at nanosecond precision and JSON rejects native types.
    from datetime import date, timedelta

    from triplum.datasets.frames import FrameDataset

    frame = pl.DataFrame(
        {
            "bytes": [b"a", b"b"],
            "date": [date(2026, 1, 1), None],
            "duration": [timedelta(seconds=1), timedelta(seconds=2)],
            "nested": [[1, 2], [3]],
        }
    ).with_columns(pl.Series("time", [1, 2], dtype=pl.Datetime("ns")))
    fingerprint = FrameDataset(frame).fingerprint()
    assert fingerprint == FrameDataset(pl.concat([frame.head(1), frame.tail(1)])).fingerprint()
    assert fingerprint == FrameDataset(pl.concat([frame, frame]).slice(2)).fingerprint()
    changed = frame.with_columns(pl.Series("time", [1, 3], dtype=pl.Datetime("ns")))
    assert fingerprint != FrameDataset(changed).fingerprint()


@pytest.mark.parametrize("dtype", [pl.Categorical, pl.Enum(["a", "b", "c", "d"])])
def test_frame_fingerprint_includes_dictionary_values(dtype):
    from triplum.datasets.frames import FrameDataset

    fingerprints = {
        FrameDataset(pl.DataFrame({"x": pl.Series(values, dtype=dtype)})).fingerprint()
        for values in [["a", "b"], ["c", "d"], ["b", "a"]]
    }
    assert len(fingerprints) == 3


@pytest.mark.parametrize(
    "dtype,values,changed",
    [
        (pl.List(pl.Categorical), [["a"], ["b"]], [["c"], ["d"]]),
        (pl.Struct({"c": pl.Categorical}), [{"c": "a"}], [{"c": "b"}]),
    ],
)
def test_frame_fingerprint_handles_nested_dictionaries(dtype, values, changed):
    from triplum.datasets.frames import FrameDataset

    frame = pl.DataFrame({"x": pl.Series(values, dtype=dtype)})
    other = pl.DataFrame({"x": pl.Series(changed, dtype=dtype)})
    assert FrameDataset(frame).fingerprint() != FrameDataset(other).fingerprint()
