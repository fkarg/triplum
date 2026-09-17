import polars as pl
from triplum.data.viewer import Viewer
from triplum.embed.fake import FakeEmbedder
from triplum.eval.datasets import registry as hr
from triplum.eval.judge import judge_correct
from triplum.generate.reader import read
from triplum.llm.fake import FakeLLM
from triplum.rerank.fake import FakeReranker
from triplum.retrieve import stages
from triplum.store.sqlite.store import SqliteStore

PUBLIC = Viewer.of("public")


def _store(tmp_db, ds, embedder):
    s = SqliteStore(tmp_db)
    s.put_documents(ds.documents, ds.grants)
    s.put_chunks(ds.chunks)
    s.put_embeddings(
        embedder.spec,
        ds.chunks["id"].to_list(),
        embedder.embed_passages(ds.chunks["text"].to_list()),
    )
    return s


def test_stages_return_ranked_frames(tmp_db):
    ds = hr.load_fixture("hotpotqa", n=3)
    e = FakeEmbedder(dims=64)
    s = _store(tmp_db, ds, e)
    for out in (
        stages.dense(ds.questions, s, e, k=5, viewer=PUBLIC),
        stages.bm25(ds.questions, s, k=5, viewer=PUBLIC),
        stages.hybrid(ds.questions, s, e, FakeReranker(), k=5, candidates=10, viewer=PUBLIC),
        stages.oracle(ds.questions, k=5),
    ):
        assert out.columns == ["question_id", "chunk_id", "rank", "score"]
        assert (out.group_by("question_id").len()["len"] <= 5).all()
        assert out.filter(pl.col("rank") == 1).height == 3
    assert stages.none(ds.questions).height == 0


def test_oracle_contains_all_gold(tmp_db):
    ds = hr.load_fixture("musique", n=5)
    out = stages.oracle(ds.questions, k=5)
    for q in ds.questions.iter_rows(named=True):
        got = out.filter(pl.col("question_id") == q["id"])["chunk_id"].to_list()
        assert set(q["gold_chunk_ids"]) <= set(got)


def test_reader_uses_visible_chunks_only(tmp_db):
    ds = hr.load_fixture("twowiki", n=2)
    e = FakeEmbedder(dims=64)
    s = _store(tmp_db, ds, e)
    seen = []

    def responder(msgs, schema):
        seen.append(msgs[-1].content)
        return '{"answer": "x"}'

    retrieved = stages.oracle(ds.questions, k=5)
    out = read(ds.questions, retrieved, s, FakeLLM(responder=responder), viewer=Viewer.of("nobody"))
    assert out.columns == [
        "question_id",
        "answer",
        "input_tokens",
        "output_tokens",
        "cached",
        "latency_s",
        "n_passages",
    ]
    assert out["n_passages"].to_list() == [0, 0]
    assert all("Passage" not in p for p in seen)


def test_judge_parses_bool():
    llm = FakeLLM(responder=lambda m, s: '{"correct": true}')
    ok, completion = judge_correct(llm, "q", ["gold"], "pred")
    assert ok is True and completion.usage.output_tokens >= 1


def test_fusion_ranks_by_reciprocal_rank(tmp_db):
    from triplum.retrieve import pipelines

    ds = hr.load_fixture("hotpotqa", n=3)
    e = FakeEmbedder(dims=64)
    s = _store(tmp_db, ds, e)
    fused = pipelines.rrf(ds.questions, s, PUBLIC, embedder=e, k=3, candidates=10)
    assert dict(fused.schema) == stages.SCHEMA
    q = ds.questions["id"][0]
    mine = fused.filter(pl.col("question_id") == q).sort("rank")
    assert mine["rank"].to_list() == list(range(1, mine.height + 1))
    assert mine["score"].to_list() == sorted(mine["score"].to_list(), reverse=True)
    bm = stages.bm25(ds.questions, s, 10, PUBLIC).filter(pl.col("question_id") == q)
    de = stages.dense(ds.questions, s, e, 10, PUBLIC).filter(pl.col("question_id") == q)
    assert set(mine["chunk_id"]) <= set(bm["chunk_id"]) | set(de["chunk_id"])
