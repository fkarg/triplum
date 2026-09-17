# Dataset overview

Snapshot: 2026-09-17.

Make bare `triplum data` scannable: a count summary, data-root location and a borderless
table with Dataset, State, Family and Flags columns. Preserve registry order and every
dataset name; never truncate identifiers. Use restrained state colors with text labels,
so redirected and no-color output remains meaningful. Wrap within the terminal width.

Replace the automatic full help dump and long legend with copyable fetch commands,
the large-dataset rule and a help hint. Explain verification briefly and display invalid-file
recovery advice only when relevant. Fetching and state determination remain unchanged.

Rendering belongs in `bench/data_view.py`; the CLI gathers specs/statuses and invokes it.
Use Rich directly as a declared dependency, already supplied transitively by Typer.
Tests cover mixed states, long names, narrow/no-color output and the CLI workflow without downloads.
