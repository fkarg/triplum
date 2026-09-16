import polars as pl
import pytest
from triplum.data.schema import now_us


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "store.sqlite"


@pytest.fixture
def sample_corpus():
    """Two documents: d1 readable by public and alice, d2 by alice only; three chunks."""
    t = now_us()
    docs = pl.DataFrame(
        {
            "id": ["d1", "d2"],
            "source": ["t", "t"],
            "uri": [None, None],
            "observed_at": [t, t],
            "metadata": [None, None],
        },
        schema={
            "id": pl.Utf8,
            "source": pl.Utf8,
            "uri": pl.Utf8,
            "observed_at": pl.Int64,
            "metadata": pl.Utf8,
        },
    )
    grants = pl.DataFrame(
        {
            "document_id": ["d1", "d1", "d2"],
            "principal": ["public", "alice", "alice"],
            "granted_at": [t, t, t],
            "revoked_at": [None, None, None],
        },
        schema={
            "document_id": pl.Utf8,
            "principal": pl.Utf8,
            "granted_at": pl.Int64,
            "revoked_at": pl.Int64,
        },
    )
    chunks = pl.DataFrame(
        {
            "id": [1, 2, 3],
            "document_id": ["d1", "d1", "d2"],
            "parent_id": [None, None, None],
            "level": [0, 0, 0],
            "span_start": [0, 10, 0],
            "span_end": [10, 20, 10],
            "text": ["public one", "public two", "alice secret"],
        },
        schema={
            "id": pl.Int64,
            "document_id": pl.Utf8,
            "parent_id": pl.Int64,
            "level": pl.Int64,
            "span_start": pl.Int64,
            "span_end": pl.Int64,
            "text": pl.Utf8,
        },
    )
    return docs, grants, chunks
