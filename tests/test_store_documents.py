import polars as pl
import pytest

from triplum.data.schema import now_us
from triplum.data.viewer import Viewer
from triplum.store.sqlite.acl import acl_hash, principal_token
from triplum.store.sqlite.store import SqliteStore


def _docs():
    t = now_us()
    docs = pl.DataFrame(
        {
            "id": ["d1", "d2"],
            "source": ["t", "t"],
            "uri": [None, None],
            "observed_at": [t, t],
            "metadata": [None, None],
        },
        schema={"id": pl.Utf8, "source": pl.Utf8, "uri": pl.Utf8, "observed_at": pl.Int64, "metadata": pl.Utf8},
    )
    grants = pl.DataFrame(
        {
            "document_id": ["d1", "d1", "d2"],
            "principal": ["public", "alice", "alice"],
            "granted_at": [t, t, t],
            "revoked_at": [None, None, None],
        },
        schema={"document_id": pl.Utf8, "principal": pl.Utf8, "granted_at": pl.Int64, "revoked_at": pl.Int64},
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


def test_acl_helpers():
    assert principal_token("alice@example.org") == principal_token("alice@example.org")
    assert principal_token("a") != principal_token("b")
    assert acl_hash({"b", "a"}) == acl_hash(["a", "b"]) and len(acl_hash({"a"})) == 16


def test_put_and_get_chunks_respects_viewer(tmp_db):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = _docs()
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    public = s.get_chunks([1, 2, 3], Viewer.of("public"))
    assert sorted(public["id"].to_list()) == [1, 2]
    alice = s.get_chunks([1, 2, 3], Viewer.of("alice"))
    assert sorted(alice["id"].to_list()) == [1, 2, 3]
    nobody = s.get_chunks([1, 2, 3], Viewer.of("carol"))
    assert nobody.height == 0


def test_revoked_grant_hides_document(tmp_db):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = _docs()
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    s.revoke("d2", "alice", at=now_us())
    assert s.get_chunks([3], Viewer.of("alice")).height == 0
    assert s.document_acl_hash("d2") == acl_hash([])


def test_put_documents_rejects_wrong_columns(tmp_db):
    s = SqliteStore(tmp_db)
    with pytest.raises(ValueError):
        s.put_documents(
            pl.DataFrame({"id": ["x"]}), pl.DataFrame({"document_id": [], "principal": []})
        )
