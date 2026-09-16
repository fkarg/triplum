import polars as pl
import pytest
from triplum.data.schema import now_us
from triplum.data.viewer import Viewer
from triplum.store.sqlite.acl import acl_hash, principal_token
from triplum.store.sqlite.store import SqliteStore


def test_acl_helpers():
    assert principal_token("alice@example.org") == principal_token("alice@example.org")
    assert principal_token("a") != principal_token("b")
    assert acl_hash({"b", "a"}) == acl_hash(["a", "b"]) and len(acl_hash({"a"})) == 16


def test_put_and_get_chunks_respects_viewer(tmp_db, sample_corpus):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    public = s.get_chunks([1, 2, 3], Viewer.of("public"))
    assert sorted(public["id"].to_list()) == [1, 2]
    alice = s.get_chunks([1, 2, 3], Viewer.of("alice"))
    assert sorted(alice["id"].to_list()) == [1, 2, 3]
    nobody = s.get_chunks([1, 2, 3], Viewer.of("carol"))
    assert nobody.height == 0


def test_revoked_grant_hides_document(tmp_db, sample_corpus):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
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
