from triplum.data.viewer import Viewer
from triplum.store.sqlite.store import SqliteStore, fts_query


def test_fts_query_quotes_terms():
    assert fts_query('cat "dog" AND mat') == '"cat" OR "dog" OR "AND" OR "mat"'
    assert fts_query("") == '""'


def test_bm25_filters_by_viewer_inside_match(tmp_db, sample_corpus):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    pub = s.bm25("secret", k=10, viewer=Viewer.of("public"))
    assert pub.height == 0
    alice = s.bm25("secret", k=10, viewer=Viewer.of("alice"))
    assert alice["id"].to_list() == [3] and alice.columns == ["id", "score"]
    both = s.bm25("public", k=10, viewer=Viewer.of("public"))
    assert sorted(both["id"].to_list()) == [1, 2]


def test_bm25_after_revoke(tmp_db, sample_corpus):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    s.revoke("d2", "alice", at=1)
    assert s.bm25("secret", k=10, viewer=Viewer.of("alice")).height == 0
