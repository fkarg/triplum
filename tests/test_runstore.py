from triplum.bench.runstore import RunStore

META = {
    "dataset": "musique", "pipeline": "dense", "config_hash": "abc", "config_json": "{}",
    "code_version": "deadbeef", "dirty": 0, "corpus_hash": "c", "questions_hash": "q", "n": 1,
    "embedding_spec": "e", "reranker_spec": None, "reader_model": "m1", "judge_model": None,
    "seed": 0, "viewer_json": "{}", "host": "h",
}


def test_runstore_roundtrip(tmp_path):
    rs = RunStore(tmp_path / "runs.db")
    rs.set_price("m1", "openai", usd_in_per_m=1.0, usd_out_per_m=2.0, usd_cached_in_per_m=0.5, source="test")
    run_id = rs.start_run(META)
    rec = rs.recorder(run_id)
    with rec.stage("read", question_id="q1", provider="openai", model="m1") as ev:
        ev.usage(1_000_000, 500_000, cached_in=0)
    rs.add_question(run_id, {
        "question_id": "q1", "retrieved_json": "[]", "answer": "x", "em": 1.0, "f1": 1.0,
        "contain": 1.0, "judge": None, "r2": 0.5, "r5": 1.0, "input_tokens": 1_000_000,
        "output_tokens": 500_000, "usd": rec.cost("m1", 1_000_000, 500_000, 0),
        "latency_s": 0.1, "n_passages": 5,
    })
    rs.finish_run(run_id, status="ok", wall_s=1.0, cache_hits=0, cache_misses=1)
    runs = rs.runs()
    assert runs.height == 1 and runs["status"][0] == "ok"
    ev = rs.events(run_id)
    assert ev.height == 1 and ev["usd"][0] == 2.0 and ev["stage"][0] == "read"
    assert rs.questions(run_id)["usd"][0] == 2.0


def test_find_existing_run(tmp_path):
    rs = RunStore(tmp_path / "runs.db")
    rid = rs.start_run(META)
    rs.finish_run(rid, status="ok", wall_s=0, cache_hits=0, cache_misses=0)
    assert rs.find_run(identity_hash=rs.identity_hash(META)) == rid
    assert rs.find_run(identity_hash="nope") is None
