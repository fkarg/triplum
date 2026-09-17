import polars as pl
import pytest
from rich.text import Text
from triplum.bench import report
from triplum.bench.cli import app
from triplum.bench.runstore import RunStore
from typer.testing import CliRunner


@pytest.mark.parametrize("width", [40, 80, 120])
def test_summary_wraps_without_losing_fields_or_runs(width):
    frame = pl.DataFrame(
        {
            "run_id": [f"run-{i:012}" for i in range(101)],
            "reader_model": ["long-model-" + "x" * 150] * 101,
            "em": [0.0] * 101,
            "r5": [0.5216666667] * 101,
            "usd_total": [None] * 101,
        }
    )
    rendered = report.format_summary(frame, width=width)
    assert all(len(line) <= width for line in rendered.splitlines())
    compact = "".join(rendered.split())
    for row in frame.iter_rows(named=True):
        assert row["run_id"] in compact
    assert compact.count("reader_model=" + frame["reader_model"][0]) == 101
    assert compact.count("em=0") == 101
    assert compact.count("r5=0.521667") == 101
    assert compact.count("usd_total=n/a") == 101
    assert "shape:" not in rendered and "f64" not in rendered


def test_empty_summary_has_readable_message():
    assert report.format_summary(pl.DataFrame(), width=80) == "No benchmark runs recorded."


def test_report_cli_uses_terminal_width(tmp_path, monkeypatch):
    from triplum.bench.cli import main

    path = tmp_path / "runs.db"
    assert (
        main(
            [
                "bench",
                "run",
                "--pipeline",
                "bm25",
                "--dataset",
                "musique",
                "--n",
                "1",
                "--fixture",
                "--reader",
                "fake",
                "--cache-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    store = RunStore(path)
    frame = report.summary(store)
    store.close()
    monkeypatch.setenv("COLUMNS", "40")
    result = CliRunner().invoke(app, ["bench", "report", "--runstore", str(path)])
    assert result.exit_code == 0, result.output
    assert all(len(line) <= 40 for line in Text.from_ansi(result.output).plain.splitlines())
    compact = "".join(Text.from_ansi(result.output).plain.split())
    assert frame["run_id"][0] in compact
    for key, value in frame.row(0, named=True).items():
        if key != "run_id":
            rendered = (
                "n/a"
                if value is None
                else f"{value:.6g}"
                if isinstance(value, float)
                else str(value)
            )
            assert f"{key}={rendered}" in compact
