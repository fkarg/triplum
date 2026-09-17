import sqlite3

from triplum.bench.cli import app
from triplum.bench.runstore import RunStore
from typer.testing import CliRunner


def test_bench_overview_missing_store_does_not_create_cache(tmp_path, monkeypatch):
    root = tmp_path / "absent"
    monkeypatch.setenv("TRIPLUM_CACHE", str(root))
    result = CliRunner().invoke(app, ["bench"])
    assert result.exit_code == 0, result.output
    assert str(root / "runs.db") in result.output
    assert "No local benchmark runs recorded." in result.output
    assert "closed_book, bm25, dense, hybrid, oracle" in result.output
    assert "Commands" in result.output
    for command in ("run", "sweep", "report", "show", "rerun", "inspect", "diff", "tail"):
        assert command in result.output
    assert not root.exists()


def test_bench_overview_empty_store(tmp_path):
    path = tmp_path / "runs.db"
    store = RunStore(path)
    store.conn.close()
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["bench", "--runstore", str(path)])
    assert result.exit_code == 0, result.output
    assert "No local benchmark runs recorded." in result.output
    assert path.read_bytes() == before


def test_bench_overview_recent_runs_without_migrating(tmp_path):
    # Only the historical columns used by the overview: constructing RunStore here would
    # attempt migrations. Include URI-sensitive characters to exercise read-only path handling.
    path = tmp_path / "runs #1?.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE runs (run_id, created_at, dataset, pipeline, n, status)")
        conn.executemany(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
            [
                (f"run-{i:02}", i, "musique", "dense", 20, ("ok", "failed", "running")[i % 3])
                for i in range(12)
            ],
        )
    conn.close()
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["bench", "--runstore", str(path)])
    assert result.exit_code == 0, result.output
    rows = [line for line in result.output.splitlines() if line.startswith("run-")]
    assert rows == [
        f"run-{i:02}: musique/dense  n=20  status={(('ok', 'failed', 'running')[i % 3])}"
        for i in range(11, 1, -1)
    ]
    assert "possibly interrupted" in result.output
    assert "reuses identical completed runs" in result.output
    assert "report" in result.output and "saved metrics" in result.output
    assert "--resume" in result.output and "--force" in result.output
    assert "Commands" in result.output
    assert path.read_bytes() == before


def test_bench_help_does_not_read_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPLUM_CACHE", str(tmp_path))
    (tmp_path / "runs.db").write_text("not a database")
    for args in (["bench", "--help"], ["bench", "run", "--help"]):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        assert "Usage:" in result.output
        assert "No local benchmark" not in result.output
