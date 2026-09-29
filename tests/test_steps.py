from pathlib import Path

import numpy as np
import pytest

from triplum.datatype import Chunk, Source
from triplum.steps.chunk_preprocessing import OriginalText
from triplum.steps.chunking import FixedSize
from triplum.steps.conversion import Utf8File
from triplum.steps.embedding import ZeroEmbedder


def test_utf8_file_keeps_newlines(tmp_path: Path):
    path = tmp_path / "a.md"
    path.write_bytes("é\r\nx".encode())
    [source] = Utf8File()(path)
    assert (source.origin, source.text) == (str(path), "é\r\nx")


def test_fixed_size_slices_by_character():
    source = Source(origin="s", text="é\r\nxyz!")
    chunks = FixedSize(3)(source)
    assert [(c.source_id, c.origin, c.start, c.text) for c in chunks] == [
        (source.id, "s", 0, "é\r\n"),
        (source.id, "s", 3, "xyz"),
        (source.id, "s", 6, "!"),
    ]
    assert FixedSize(3)(Source(origin="s", text="")) == []


@pytest.mark.parametrize("size", [0, -1, True])
def test_fixed_size_must_be_positive(size: int):
    with pytest.raises(ValueError, match="size"):
        FixedSize(size)


def test_original_text():
    chunk = Chunk(source_id=Source(origin="s", text="abc").id, origin="s", start=0, text="abc")
    assert OriginalText()(chunk) == "abc"


def test_zero_embedder_returns_one_row_per_text():
    vectors = ZeroEmbedder(dimensions=4)(["a", "b"])
    assert vectors.shape == (2, 4)
    assert vectors.dtype == np.float32
    assert not vectors.any()
