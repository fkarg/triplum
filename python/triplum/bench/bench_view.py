"""Terminal presentation for benchmark projections; no database or execution access."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import polars as pl
from rich.columns import Columns
from rich.console import Console
from rich.table import Table
from rich.text import Text

STATUS_STYLES = {"ok": "green", "failed": "bold red", "running": "yellow"}
QUALITY = {"em", "f1", "contain", "judge", "r2", "r5"}
IDENTITY = {"dataset", "pipeline", "n", "reader_model", "embedding_spec"}


def _value(value: object) -> str:
    return "n/a" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)


def _fields(values: Mapping[str, object], console: Console) -> None:
    fields = []
    for key, value in values.items():
        field = Text(f"{key}=", overflow="fold", no_wrap=False)
        field.stylize("dim")
        field.append(_value(value))
        fields.append(field)
    if fields:
        console.print(Columns(fields, padding=(0, 2)))


def print_overview(
    rows: Sequence[tuple[str, str, str, int, str]],
    path: Path,
    pipelines: Sequence[str],
    *,
    console: Console | None = None,
) -> None:
    """Show at most ten already-selected recent runs and compact command hints."""
    console = console or Console(markup=False, highlight=False)
    console.print(Text("Benchmarks", style="bold"))
    console.print(Text(f"run store: {path}", style="dim"))
    console.print(Text("Pipelines: " + ", ".join(pipelines), style="dim"))
    console.print()
    if rows:
        console.print(Text("Recent local runs · newest first", style="bold"))
        if console.width >= 64:
            table = Table("Run", "Dataset", "Pipeline", "n", "State", box=None, padding=(0, 2))
            for column in table.columns:
                column.overflow = "fold"
            for run_id, dataset, pipeline, n, status in rows:
                table.add_row(
                    Text(run_id, style="cyan"),
                    Text(dataset),
                    Text(pipeline),
                    str(n),
                    Text(status, style=STATUS_STYLES.get(status, "")),
                )
            console.print(table)
        else:
            for run_id, dataset, pipeline, n, status in rows:
                console.print(Text(run_id, style="cyan"))
                _fields(
                    {"dataset": dataset, "pipeline": pipeline, "n": n, "status": status}, console
                )
    else:
        console.print("No local benchmark runs recorded.")
    console.print()
    console.print(Text("ok = completed; failed = ended with an error", style="dim"))
    if any(row[4] == "running" for row in rows):
        console.print(
            Text("running = no completion recorded, possibly interrupted", style="yellow")
        )
    for command, description in (
        ("run", "executes a benchmark or reuses identical completed runs"),
        ("report", "saved metrics"),
        ("inspect / diff", "question details / compare runs"),
        ("rerun", "reuse configuration; --resume continues, --force recomputes"),
        ("show / sweep / tail", "JSON configuration / embedding sweep / progress"),
    ):
        line = Text(command, style="cyan")
        line.append("  " + description, style="")
        console.print(line)
    console.print(Text("Full help: triplum bench --help", style="dim"))


def print_summary(frame: pl.DataFrame, *, console: Console | None = None) -> None:
    """Display every summary field, grouped into identity, quality and cost."""
    console = console or Console(markup=False, highlight=False)
    if frame.is_empty():
        console.print("No benchmark runs recorded.")
    for row in frame.iter_rows(named=True):
        console.print(Text(f"Run {row.pop('run_id')}", style="bold cyan"))
        for keys in (IDENTITY, QUALITY, set(row) - IDENTITY - QUALITY):
            _fields({key: value for key, value in row.items() if key in keys}, console)
        console.print()


def print_inspect(view: Mapping[str, Any], *, console: Console | None = None) -> None:
    """Render answers, all question metrics, chunk previews and model calls."""
    console = console or Console(markup=False, highlight=False)
    identity = view["identity"]
    console.print(Text(f"Run {identity['run_id']}", style="bold cyan"))
    _fields(
        {
            key: identity[key]
            for key in ("dataset", "pipeline", "status", "n", "reader_model", "judge_model")
        },
        console,
    )
    if not view["store_available"]:
        console.print(
            Text("Store artifact not available: chunks shown as ids only", style="yellow")
        )
    for question in view["questions"]:
        console.print()
        console.print(Text(f"Question {question['question_id']}", style="bold cyan"))
        console.print(Text("Answer: " + _value(question["answer"])))
        _fields(question["metrics"], console)
        if question["retrieved"]:
            console.print(Text("Chunks", style="bold"))
            for chunk in question["retrieved"]:
                preview = (chunk["text"] or "").replace("\n", " ")[:160]
                console.print(Text(f"  #{chunk['chunk_id']}: {preview}"))
        if question["events"]:
            console.print(Text("Model calls", style="bold"))
            for event in question["events"]:
                _fields(
                    {
                        key: event[key]
                        for key in ("stage", "model", "input_tokens", "output_tokens", "cached")
                    }
                    | {"duration_s": (event["ended_at"] - event["started_at"]) / 1e6},
                    console,
                )


def print_diff(
    view: Mapping[str, Any], changed: pl.DataFrame, *, console: Console | None = None
) -> None:
    """Compare identity, configuration and metric means; retain every changed row."""
    console = console or Console(markup=False, highlight=False)
    for title, values in (
        ("Identity", view["identity_diff"]),
        ("Configuration", view["config_diff"]),
        ("Metric means", view["means"]),
    ):
        console.print(Text(title, style="bold cyan"))
        if not values:
            console.print(Text("No differences", style="dim"))
            continue
        table = Table("Field", "A", "B", box=None, padding=(0, 1))
        for column in table.columns:
            column.overflow = "fold"
        for key, (a, b) in values.items():
            table.add_row(
                Text(key),
                Text("n/a" if a is None else str(a)),
                Text("n/a" if b is None else str(b)),
            )
        console.print(table)
    console.print(f"Only in A: {len(view['only_in_a'])}  Only in B: {len(view['only_in_b'])}")
    console.print(Text("Changed questions", style="bold cyan"))
    if changed.is_empty():
        console.print("No changed questions")
    for row in changed.iter_rows(named=True):
        console.print(Text(str(row.pop("question_id")), style="cyan"))
        _fields(row, console)


def print_tail(progress: Mapping[str, Any], *, console: Console | None = None) -> None:
    """One progress update; polling remains the caller's responsibility."""
    console = console or Console(markup=False, highlight=False)
    line = Text(str(progress["run_id"]), style="cyan")
    status = progress["status"]
    line.append("  ")
    line.append(status, style=STATUS_STYLES.get(status, ""))
    line.append(f"  {progress['done']}/{progress['total']}", style="bold")
    line.append(
        f"  {_value(progress['last_stage'])} @ {_value(progress['last_question'])}", style="dim"
    )
    console.print(line)


VERDICT_STYLES = {
    "deterministic": "green",
    "adds variance": "bold red",
    "absorbs variance": "cyan",
    "passes variance": "yellow",
}


def print_variance(
    stages: pl.DataFrame, metrics: pl.DataFrame, *, console: Console | None = None
) -> None:
    """The per-stage verdicts of a replicated experiment, then the metric spread."""
    console = console or Console(markup=False, highlight=False)
    if stages.is_empty():
        console.print("No replicates recorded for this experiment.")
        return
    table = Table(title="Stages across replicates", show_lines=False)
    for column in ("stage", "replicates", "executed", "inputs", "outputs"):
        table.add_column(column)
    table.add_column("verdict", no_wrap=True)
    for row in stages.iter_rows(named=True):
        verdict = row["verdict"]
        table.add_row(
            row["stage"],
            str(row["replicates"]),
            str(row["executed"]),
            "agree" if row["inputs_agree"] else "differ",
            "agree" if row["outputs_agree"] else "differ",
            Text(verdict, style=VERDICT_STYLES.get(verdict, "")),
        )
    console.print(table)
    spread = Table(title="Metrics over replicates")
    for column in ("metric", "replicates", "mean", "std", "min", "max"):
        spread.add_column(column)
    for row in metrics.iter_rows(named=True):
        spread.add_row(
            row["metric"],
            str(row["replicates"]),
            _value(row["mean"]),
            _value(row["std"]),
            _value(row["min"]),
            _value(row["max"]),
        )
    console.print(spread)
