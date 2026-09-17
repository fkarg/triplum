import pytest
from triplum.bench.runstore import RunStore

META = {
    "dataset": "musique",
    "pipeline": "dense",
    "config_hash": "abc",
    "config_json": "{}",
    "code_version": "deadbeef",
    "dirty": 0,
    "code_hash": "c0de",
    "corpus_hash": "c",
    "questions_hash": "q",
    "n": 1,
    "embedding_spec": "e",
    "reranker_spec": None,
    "reader_model": "m1",
    "judge_model": None,
    "seed": 0,
    "viewer_json": "{}",
    "host": "h",
    "reader_prompt_hash": "rp",
    "judge_prompt_hash": None,
}


def test_runstore_roundtrip(tmp_path):
    rs = RunStore(tmp_path / "runs.db")
    rs.set_price(
        "m1", "openai", usd_in_per_m=1.0, usd_out_per_m=2.0, usd_cached_in_per_m=0.5, source="test"
    )
    run_id = rs.start_run(META)
    rs.snapshot_prices(run_id, ["m1"])
    rec = rs.recorder(run_id)
    with rec.stage("read", question_id="q1", provider="openai", model="m1") as ev:
        ev.usage(1_000_000, 500_000, cached_in=0)
    with rec.stage("read", question_id="q2", provider="openai", model="m1") as ev:
        ev.usage(1_000_000, 500_000, cached_in=0, cached=True)
    rs.add_question(
        run_id,
        {
            "question_id": "q1",
            "retrieved_json": "[]",
            "answer": "x",
            "em": 1.0,
            "f1": 1.0,
            "contain": 1.0,
            "judge": None,
            "r2": 0.5,
            "r5": 1.0,
            "input_tokens": 1_000_000,
            "output_tokens": 500_000,
            "usd": rec.cost("m1", 1_000_000, 500_000, 0),
            "cached": 0,
            "latency_s": 0.1,
            "n_passages": 5,
        },
    )
    rs.finish_run(run_id, status="ok", wall_s=1.0, cache_hits=0, cache_misses=1)
    runs = rs.runs()
    assert runs.height == 1 and runs["status"][0] == "ok"
    ev = rs.events(run_id)
    assert ev.height == 2 and ev["usd"].to_list() == [2.0, 2.0] and ev["cached"].to_list() == [0, 1]
    assert rs.questions(run_id)["usd"][0] == 2.0
    # a later price change must not alter the run's cost
    rs.set_price(
        "m1",
        "openai",
        usd_in_per_m=100.0,
        usd_out_per_m=100.0,
        usd_cached_in_per_m=1.0,
        source="later",
    )
    assert rec.cost("m1", 1_000_000, 500_000, 0) == 2.0


def test_find_existing_run(tmp_path):
    rs = RunStore(tmp_path / "runs.db")
    rid = rs.start_run(META)
    rs.finish_run(rid, status="ok", wall_s=0, cache_hits=0, cache_misses=0)
    assert rs.find_run(identity_hash=rs.identity_hash(META)) == rid
    assert rs.find_run(identity_hash="nope") is None


def test_old_schema_is_migrated(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
    CREATE TABLE runs (run_id TEXT PRIMARY KEY, identity_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
      dataset TEXT NOT NULL, pipeline TEXT NOT NULL, config_hash TEXT NOT NULL, config_json TEXT NOT NULL,
      code_version TEXT NOT NULL, dirty INTEGER NOT NULL, corpus_hash TEXT NOT NULL, questions_hash TEXT NOT NULL,
      n INTEGER NOT NULL, embedding_spec TEXT, reranker_spec TEXT, reader_model TEXT NOT NULL, judge_model TEXT,
      seed INTEGER NOT NULL, viewer_json TEXT NOT NULL, host TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'running', wall_s REAL, cache_hits INTEGER, cache_misses INTEGER) STRICT;
    CREATE TABLE run_questions (run_id TEXT NOT NULL, question_id TEXT NOT NULL, retrieved_json TEXT NOT NULL,
      answer TEXT NOT NULL, em REAL NOT NULL, f1 REAL NOT NULL, contain REAL NOT NULL, judge REAL,
      r2 REAL NOT NULL, r5 REAL NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
      usd REAL, latency_s REAL NOT NULL, n_passages INTEGER NOT NULL, PRIMARY KEY (run_id, question_id)) STRICT;
    """)
    conn.close()
    rs = RunStore(db)
    rid = rs.start_run(META)
    rs.finish_run(rid, status="ok", wall_s=0, cache_hits=0, cache_misses=0)
    row = rs.run(rid)
    assert row is not None
    assert row["code_hash"] == "c0de"
    cols = {r[1] for r in rs.conn.execute("PRAGMA table_info(run_questions)")}
    assert "cached" in cols


def test_old_store_with_not_null_recall_is_rebuilt(tmp_path):
    import sqlite3

    from triplum.bench import runstore

    path = tmp_path / "old.db"
    old_ddl = runstore.DDL.replace("r2 REAL, r5 REAL,", "r2 REAL NOT NULL, r5 REAL NOT NULL,")
    with sqlite3.connect(path) as conn:
        conn.executescript(old_ddl)
        conn.execute(
            "INSERT INTO runs (run_id, identity_hash, created_at, dataset, pipeline, config_hash, config_json,"
            " code_version, dirty, code_hash, corpus_hash, questions_hash, n, reader_model, seed, viewer_json,"
            " host, reader_prompt_hash) VALUES ('r', 'i', 0, 'd', 'p', 'c', '{}', 'v', 0, 'h', 'c', 'q', 1, 'm',"
            " 0, '[]', 'h', 'p')"
        )
        conn.execute(
            "INSERT INTO run_questions (run_id, question_id, retrieved_json, answer, em, f1, contain, r2, r5,"
            " input_tokens, output_tokens, latency_s, n_passages) VALUES ('r', 'q', '[]', 'a', 1, 1, 1, 0.5, 1,"
            " 0, 0, 0.1, 2)"
        )
    rs = RunStore(path)
    notnull = {r[1]: r[3] for r in rs.conn.execute("PRAGMA table_info(run_questions)")}
    assert notnull["r2"] == 0 and notnull["r5"] == 0 and notnull["em"] == 1
    assert rs.questions("r")["r2"].to_list() == [0.5]
    rs.conn.execute(
        "INSERT INTO run_questions (run_id, question_id, retrieved_json, answer, em, f1, contain,"
        " input_tokens, output_tokens, latency_s, n_passages) VALUES ('r', 'q2', '[]', 'a', 0, 0, 0,"
        " 0, 0, 0.1, 0)"
    )
    assert RunStore(path).questions("r").height == 2


def test_runstore_context_manager_closes_its_connection(tmp_path):
    import sqlite3

    with RunStore(tmp_path / "runs.db") as rs:
        assert rs.runs().height == 0
    with pytest.raises(sqlite3.ProgrammingError):
        rs.runs()
