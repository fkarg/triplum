from triplum.data.viewer import Viewer
from triplum.embed.fake import FakeEmbedder
from triplum.store.sqlite.store import SqliteStore


def _load(tmp_db, sample_corpus):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    e = FakeEmbedder(dims=32)
    vecs = e.embed_passages(chunks["text"].to_list())
    s.put_embeddings(e.spec, chunks["id"].to_list(), vecs)
    return s, e


def test_vector_search_respects_viewer(tmp_db, sample_corpus):
    s, e = _load(tmp_db, sample_corpus)
    q = e.embed_queries(["alice secret"])[0]
    pub = s.vector_search(e.spec, q, k=3, viewer=Viewer.of("public"))
    assert 3 not in pub["id"].to_list() and pub.height == 2
    alice = s.vector_search(e.spec, q, k=3, viewer=Viewer.of("alice"))
    assert alice["id"].to_list()[0] == 3 and alice.columns == ["id", "score"]


def test_put_embeddings_is_idempotent_and_records_spec(tmp_db, sample_corpus):
    s, e = _load(tmp_db, sample_corpus)
    s.put_embeddings(e.spec, [1], e.embed_passages(["public one"]))
    n = s.conn.execute(f"SELECT COUNT(*) FROM {e.spec.table_name()}").fetchone()[0]
    assert n == 3
    assert s.has_embeddings(e.spec, [1, 2, 3]) == [True, True, True]
    assert s.has_embeddings(e.spec, [99]) == [False]


def test_vector_search_after_revoke_moves_partition(tmp_db, sample_corpus):
    s, e = _load(tmp_db, sample_corpus)
    s.revoke("d2", "alice", at=1)
    q = e.embed_queries(["alice secret"])[0]
    assert 3 not in s.vector_search(e.spec, q, k=3, viewer=Viewer.of("alice"))["id"].to_list()


def test_no_embedding_leaves_store_for_hidden_rows(tmp_db, sample_corpus):
    s, e = _load(tmp_db, sample_corpus)
    q = e.embed_queries(["alice secret"])[0]
    out = s.vector_search(e.spec, q, k=3, viewer=Viewer.of("public"))
    assert "embedding" not in out.columns and "vector" not in out.columns
