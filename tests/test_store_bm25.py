import pytest

from triplum.data.corpus import Document
from triplum.data.viewer import Viewer
from triplum.datasets.collate import corpus_batch
from triplum.store.sqlite.acl import principal_token
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


def test_plain_text_search_filters_before_limit_and_follows_revocation(tmp_db, sample_corpus):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    assert s.search_text("public", Viewer.of("public"), limit=1)["id"].to_list() == [1]
    assert s.search_text("secret", Viewer.of("public"), limit=1).is_empty()
    assert s.search_text("secret", Viewer.of("alice"), limit=1)["id"].to_list() == [3]
    s.revoke("d2", "alice", at=1)
    assert s.search_text("secret", Viewer.of("alice"), limit=1).is_empty()


def test_plain_text_search_applies_visibility_before_limit(tmp_db):
    s = SqliteStore(tmp_db)
    batch = corpus_batch(
        [
            Document(id="a-private", source="t", text="needle", grants=("alice",)),
            Document(id="z-public", source="t", text="needle", grants=("public",)),
        ]
    )
    s.put_documents(batch.documents, batch.grants)
    s.put_chunks(batch.chunks)
    assert s.search_text("needle", Viewer.of("public"), limit=1)["document_id"].to_list() == [
        "z-public"
    ]
    with pytest.raises(ValueError, match="limit"):
        s.search_text("needle", Viewer.of("public"), limit=-1)


def test_text_queries_never_match_acl_tokens(tmp_db, sample_corpus):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = sample_corpus
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    token = principal_token("public")
    assert s.search_text(token, Viewer.of("public")).is_empty()
    assert s.bm25(token, k=10, viewer=Viewer.of("public")).is_empty()
