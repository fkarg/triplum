from io import StringIO

import polars as pl
import pytest
from rich.console import Console

from triplum.bench import bench_view


@pytest.mark.parametrize("width", [40, 63, 64, 100])
def test_report_preserves_every_value_at_each_width(width):
    stream = StringIO()
    console = Console(file=stream, width=width, force_terminal=False)
    frame = pl.DataFrame(
        {
            "run_id": ["a12345678901", "b12345678901"],
            "reader_model": ["[literal]/" + "long" * 40] * 2,
            "r5": [0.5216666667, None],
            "usd_total": [None, 0.0],
            "extra_field": ["preserved"] * 2,
        }
    )
    bench_view.print_summary(frame, console=console)
    out = stream.getvalue()
    assert all(len(line) <= width for line in out.splitlines())
    compact = "".join(out.split())
    assert all(rid in compact for rid in frame["run_id"])
    assert compact.count("reader_model=" + frame["reader_model"][0]) == 2
    assert "r5=0.521667" in compact and "r5=n/a" in compact
    assert "usd_total=n/a" in compact and "usd_total=0" in compact
    assert compact.count("extra_field=preserved") == 2
    assert "\x1b" not in out


def test_inspect_handles_missing_recall_and_literal_answer():
    stream = StringIO()
    console = Console(file=stream, width=60, force_terminal=False)
    view = {
        "identity": {
            "run_id": "abc123",
            "dataset": "test",
            "pipeline": "closed_book",
            "status": "ok",
            "n": 1,
            "reader_model": "fake",
            "judge_model": None,
        },
        "store_available": False,
        "questions": [
            {
                "question_id": "q1",
                "answer": "[bold]literal[/bold]",
                "metrics": {"r2": None, "r5": None, "f1": 0.5, "usd": None},
                "retrieved": [{"chunk_id": 7, "text": None}],
                "events": [],
            }
        ],
    }
    bench_view.print_inspect(view, console=console)
    out = stream.getvalue()
    assert "[bold]literal[/bold]" in out
    assert "r2=n/a" in out and "r5=n/a" in out
    assert "#7" in out and "not available" in out


@pytest.mark.parametrize("no_color", [False, True])
def test_tail_status_color_and_no_color(no_color):
    stream = StringIO()
    console = Console(
        file=stream, width=80, force_terminal=True, color_system="standard", no_color=no_color
    )
    bench_view.print_tail(
        {
            "run_id": "abc123",
            "status": "ok",
            "done": 20,
            "total": 20,
            "last_stage": "read",
            "last_question": "[q1]",
        },
        console=console,
    )
    out = stream.getvalue()
    assert "20/20" in out and "[q1]" in out
    assert ("\x1b[32m" in out) == (not no_color)


@pytest.mark.parametrize("width", [40, 80, 120])
def test_diff_keeps_long_values_and_all_changed_questions(width):
    stream = StringIO()
    console = Console(file=stream, width=width, force_terminal=False)
    model = "[literal]/" + "long" * 30
    view = {
        "identity_diff": {"reader_model": (model, "other")},
        "config_diff": {"threshold": (0.12345671, 0.12345672)},
        "means": {"f1": (None, 0.5)},
        "only_in_a": [],
        "only_in_b": [],
    }
    changed = pl.DataFrame(
        {"question_id": [f"question-{i}" for i in range(101)], "d_f1": [0.5] * 101}
    )
    bench_view.print_diff(view, changed, console=console)
    output = stream.getvalue()
    assert all(len(line) <= width for line in output.splitlines())
    # Table columns can interleave wrapped values: reconstruct the A column for long models.
    assert "…" not in output
    lines = output.splitlines()
    header = lines[1]
    start, end = header.index("A"), header.index("B")
    model_lines = lines[2 : lines.index("Configuration")]
    assert "".join(line[start:end].strip() for line in model_lines) == model
    assert "0.12345671" in output and "0.12345672" in output
    assert all(f"question-{i}\n" in output for i in range(101))
    assert "n/a" in output and "0.5" in output
