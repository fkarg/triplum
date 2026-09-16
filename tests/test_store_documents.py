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


def test_put_documents_twice_keeps_chunks_and_embeddings(tmp_db, sample_corpus):
    from triplum.embed.fake import FakeEmbedder

    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    e = FakeEmbedder(dims=16)
    s.put_embeddings(e.spec, [1, 2, 3], e.embed_passages(chunks["text"].to_list()))
    s.put_documents(docs, grants)
    assert s.get_chunks([1, 2, 3], Viewer.of("alice")).height == 3
    assert s.bm25("public", k=5, viewer=Viewer.of("public")).height == 2
    assert s.vector_search(e.spec, e.embed_queries(["alice secret"])[0], 3, Viewer.of("alice")).height == 3


def test_regrant_after_revoke_restores_all_paths(tmp_db, sample_corpus):
    from triplum.embed.fake import FakeEmbedder

    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    e = FakeEmbedder(dims=16)
    s.put_embeddings(e.spec, [1, 2, 3], e.embed_passages(chunks["text"].to_list()))
    s.revoke("d2", "alice", at=1)
    s.grant("d2", "alice", at=2)
    q = e.embed_queries(["alice secret"])[0]
    assert s.get_chunks([3], Viewer.of("alice")).height == 1
    assert s.bm25("secret", k=5, viewer=Viewer.of("alice"))["id"].to_list() == [3]
    assert 3 in s.vector_search(e.spec, q, 3, Viewer.of("alice"))["id"].to_list()


def test_grant_change_via_put_documents_refreshes_acl(tmp_db, sample_corpus):
    import polars as pl

    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    more = pl.DataFrame(
        {"document_id": ["d2"], "principal": ["public"], "granted_at": [5], "revoked_at": [None]},
        schema=grants.schema,
    )
    s.put_documents(docs.filter(pl.col("id") == "d2"), more)
    assert s.bm25("secret", k=5, viewer=Viewer.of("public"))["id"].to_list() == [3]
    assert s.get_chunks([1, 2, 3], Viewer.of("public")).height == 3


def test_acl_hash_encoding_is_unambiguous():
    assert acl_hash(["a\x00b", "c"]) != acl_hash(["a", "b\x00c"])


def test_get_chunks_schema_matches_canonical(tmp_db, sample_corpus):
    import polars as pl
    import pyarrow as pa
    from triplum.data import schema

    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    expected = pl.from_arrow(pa.Table.from_pylist([], schema=schema.CHUNKS)).schema
    assert s.get_chunks([1], Viewer.of("public")).schema == expected
    assert s.get_chunks([], Viewer.of("public")).schema == expected
