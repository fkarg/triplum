from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from triplum.datatype import Chunk, Source
from triplum.steps.chunk_preprocessing import OriginalText
from triplum.steps.chunking import FixedSize
from triplum.steps.conversion import Utf8File
from triplum.steps.embedding import ZeroEmbedder

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")


def test_utf8_file_keeps_newlines(tmp_path: Path):
    path = tmp_path / "a.md"
    path.write_bytes("é\r\nx".encode())
    [source] = Utf8File(collection_id=COLLECTION)(path)
    assert (source.collection_id, source.origin, source.text) == (COLLECTION, str(path), "é\r\nx")


def test_utf8_file_fingerprint_covers_the_collection():
    other = UUID("01900000-0000-7000-8000-000000000002")
    fingerprint = Utf8File(collection_id=COLLECTION).fingerprint()
    assert Utf8File(collection_id=COLLECTION).fingerprint() == fingerprint
    assert Utf8File(collection_id=other).fingerprint() != fingerprint


def test_fixed_size_slices_by_character():
    source = Source(collection_id=COLLECTION, origin="s", text="é\r\nxyz!")
    chunks = FixedSize(3)(source)
    assert [(c.source_id, c.origin, c.ordinal, c.start, c.text) for c in chunks] == [
        (source.id, "s", 0, 0, "é\r\n"),
        (source.id, "s", 1, 3, "xyz"),
        (source.id, "s", 2, 6, "!"),
    ]
    assert {c.collection_id for c in chunks} == {COLLECTION}
    assert FixedSize(3)(source) == chunks
    assert FixedSize(3)(Source(collection_id=COLLECTION, origin="s", text="")) == []


@pytest.mark.parametrize("size", [0, -1, True])
def test_fixed_size_must_be_positive(size: int):
    with pytest.raises(ValueError, match="size"):
        FixedSize(size)


def test_original_text():
    source = Source(collection_id=COLLECTION, origin="s", text="abc")
    chunk = Chunk(
        collection_id=COLLECTION, source_id=source.id, origin="s", ordinal=0, start=0, text="abc"
    )
    assert OriginalText()(chunk) == "abc"


def test_zero_embedder_returns_one_row_per_text():
    vectors = ZeroEmbedder(dimensions=4)(["a", "b"])
    assert vectors.shape == (2, 4)
    assert vectors.dtype == np.float32
    assert not vectors.any()
