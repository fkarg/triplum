import sqlite3

from rich.text import Text
from typer.testing import CliRunner

from triplum.bench.cli import app
from triplum.bench.runstore import RunStore


def test_bench_overview_missing_store_does_not_create_cache(tmp_path, monkeypatch):
    root = tmp_path / "absent"
    monkeypatch.setenv("TRIPLUM_CACHE", str(root))
    result = CliRunner().invoke(app, ["bench"])
    assert result.exit_code == 0, result.output
    assert str(root / "runs.db") in "".join(Text.from_ansi(result.output).plain.split())
    assert "No local benchmark runs recorded." in result.output
    assert "closed_book, bm25, dense, rrf, hybrid, oracle" in result.output
    assert "triplum bench --help" in result.output
    assert "Usage:" not in result.output
    for command in ("run", "sweep", "report", "show", "rerun", "inspect", "diff", "tail"):
        assert command in result.output
    assert not root.exists()


def test_bench_overview_empty_store(tmp_path):
    path = tmp_path / "runs.db"
    store = RunStore(path)
    store.close()
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
    rows = [
        line
        for line in Text.from_ansi(result.output).plain.splitlines()
        if line.lstrip().startswith("run-")
    ]
    assert [row.split()[0] for row in rows] == [f"run-{i:02}" for i in range(11, 1, -1)]
    for row, i in zip(rows, range(11, 1, -1)):
        assert "musique" in row and "dense" in row and "20" in row
        assert ("ok", "failed", "running")[i % 3] in row
    assert "possibly interrupted" in result.output
    assert "reuses identical completed runs" in result.output
    assert "report" in result.output and "saved metrics" in result.output
    assert "--resume" in result.output and "--force" in result.output
    assert "triplum bench --help" in result.output
    assert "Usage:" not in result.output
    assert path.read_bytes() == before


def test_bench_help_does_not_read_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPLUM_CACHE", str(tmp_path))
    (tmp_path / "runs.db").write_text("not a database")
    for args in (["bench", "--help"], ["bench", "run", "--help"]):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        assert "Usage:" in result.output
        assert "No local benchmark" not in result.output
