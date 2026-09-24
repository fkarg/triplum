import polars as pl
import pytest

from triplum.data.corpus import Document
from triplum.data.schema import now_us
from triplum.data.viewer import Viewer
from triplum.datasets.collate import corpus_batch
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
    assert (
        s.vector_search(e.spec, e.embed_queries(["alice secret"])[0], 3, Viewer.of("alice")).height
        == 3
    )


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
    expected = pl.DataFrame(pa.Table.from_pylist([], schema=schema.CHUNKS)).schema
    assert s.get_chunks([1], Viewer.of("public")).schema == expected
    assert s.get_chunks([], Viewer.of("public")).schema == expected


def test_ingest_batches_resume_and_publish_only_when_complete(tmp_db):
    s = SqliteStore(tmp_db)
    first = corpus_batch([Document(id="a", source="test", text="first")])
    second = corpus_batch([Document(id="b", source="test", text="second")])

    def interrupted():
        yield first
        raise RuntimeError("source failed")

    with pytest.raises(RuntimeError, match="source failed"):
        s.ingest_corpus("same", "test", interrupted())
    assert s.get_meta("ingest_state") == "in_progress"
    assert s.conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
    with pytest.raises(RuntimeError, match="in progress"):
        s.search_text("first", Viewer.of("public"))
    with pytest.raises(RuntimeError, match="in progress"):
        s.get_chunks([], Viewer.of("public"))
    with pytest.raises(RuntimeError, match="in progress"):
        s.facts(Viewer.of("public"))
    with pytest.raises(RuntimeError, match="in progress"):
        s.identity()

    s.ingest_corpus("same", "test", iter((first, second)))
    assert s.get_meta("ingest_state") == "complete"
    assert s.search_text("second", Viewer.of("public")).height == 1
    s.revoke("a", "public", at=1)
    s.ingest_corpus("same", "test", iter((first, second)))
    assert s.search_text("first", Viewer.of("public")).height == 0


def test_ingest_batch_rolls_back_on_invalid_chunk_and_refuses_mismatch(tmp_db):
    s = SqliteStore(tmp_db)
    good = corpus_batch([Document(id="a", source="test", text="first")])
    bad = corpus_batch([Document(id="b", source="test", text="second")])
    bad = bad._replace(chunks=bad.chunks.with_columns(pl.lit("missing").alias("document_id")))
    with pytest.raises(KeyError, match="missing"):
        s.ingest_corpus("same", "test", iter((good, bad)))
    assert s.conn.execute("SELECT id FROM documents ORDER BY id").fetchall() == [("a",)]
    with pytest.raises(RuntimeError, match="holds corpus"):
        s.ingest_corpus("different", "test", iter(()))


def test_ingest_empty_and_refuse_unbound_existing_rows(tmp_db):
    s = SqliteStore(tmp_db)
    s.ingest_corpus("empty", "test", iter(()))
    assert s.get_meta("ingest_state") == "complete"
    assert s.identity()

    other = SqliteStore(tmp_db.with_name("other.sqlite"))
    batch = corpus_batch([Document(id="a", source="test", text="first")])
    other.put_documents(batch.documents, batch.grants)
    with pytest.raises(RuntimeError, match="unbound corpus rows"):
        other.ingest_corpus("new", "test", iter(()))


def test_ingest_rejects_duplicate_documents(tmp_db):
    s = SqliteStore(tmp_db)
    doc = Document(id="a", source="test", text="first")
    with pytest.raises(ValueError, match="duplicate document ids"):
        s.ingest_corpus("same", "test", iter((corpus_batch([doc, doc]),)))
    assert s.conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0


def test_schema_1_store_is_migrated_to_nullable_confidence(tmp_path):
    import sqlite3
    from importlib.resources import files

    from triplum.store.sqlite.store import SqliteStore

    ddl = files("triplum.store.sqlite").joinpath("migrations.sql").read_text()
    v1 = ddl.replace("confidence             REAL,", "confidence REAL NOT NULL DEFAULT 1.0,")
    v1 = v1.replace("confidence REAL,", "confidence REAL NOT NULL DEFAULT 1.0,")
    v1 = v1.replace("('schema_version', '2')", "('schema_version', '1')")
    assert v1.count("NOT NULL DEFAULT 1.0") == 2
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(v1)
    store = SqliteStore(path)
    assert store.get_meta("schema_version") == "2"
    for table in ("facts", "mentions"):
        notnull = {r[1]: r[3] for r in store.conn.execute(f"PRAGMA table_info({table})")}
        assert notnull["confidence"] == 0
    store.close()
