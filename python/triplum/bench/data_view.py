"""Width-aware terminal presentation of dataset availability; no fetching or verification."""

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.table import Table
from rich.text import Text

from triplum.datasets.base import Entry

STATE_STYLES = {
    "verified": "green",
    "partial": "yellow",
    "invalid": "bold red",
    "not downloaded": "dim",
}


def print_overview(
    rows: Sequence[tuple[Entry, bool, str]], root: Path, *, console: Console | None = None
) -> None:
    """Print counts, complete dataset identifiers and next actions, respecting terminal color.
    Rows are `(entry, large, state)`."""
    console = console or Console(markup=False, highlight=False)
    counts = Counter(state for _, _, state in rows)
    console.print(Text(f"{len(rows)} dataset{'s' if len(rows) != 1 else ''}", style="bold"))
    console.print(
        Columns(
            [
                Text(f"{counts[state]} {state}", style=style)
                for state, style in STATE_STYLES.items()
                if counts[state]
            ],
            padding=(0, 2),
        )
    )
    console.print(Text(f"Data: {root}", style="dim"))
    console.print()

    table = Table(box=None, pad_edge=False, padding=(0, 2), header_style="bold")
    for column in ("Dataset", "State", "Family", "Flags"):
        table.add_column(column, overflow="fold")
    for spec, large, state in rows:
        flags = Text()
        if spec.default:
            flags.append("default", style="cyan")
        if large:
            if flags:
                flags.append(", ")
            flags.append("large", style="yellow")
        status = Text(state, style=STATE_STYLES.get(state, ""))
        if console.width < 64:
            console.print(Text.assemble((spec.name, "bold"), "  ", status))
            console.print(Text.assemble((f"  {spec.family}", "dim"), "  ", flags))
        else:
            table.add_row(Text(spec.name), status, Text(spec.family, style="dim"), flags)
    if console.width >= 64:
        console.print(table)
    console.print()
    console.print(Text("Verified = files match pinned SHA-256.", style="dim"))
    if counts["invalid"]:
        console.print(Text("Remove invalid files before fetching again.", style="yellow"))
    console.print()
    console.print(Text.assemble(("Fetch defaults  ", "dim"), ("triplum data fetch", "cyan")))
    console.print(
        Text.assemble(("Fetch one       ", "dim"), ("triplum data fetch --dataset <name>", "cyan"))
    )
    console.print(
        Text.assemble(("Fetch all small ", "dim"), ("triplum data fetch --dataset all", "cyan"))
    )
    console.print(Text("Large datasets must be fetched by name.", style="dim"))
    console.print(Text.assemble(("Help            ", "dim"), ("triplum data --help", "cyan")))
