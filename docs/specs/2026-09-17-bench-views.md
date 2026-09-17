# Benchmark terminal views

Snapshot: 2026-09-17.

Extend the dataset overview's visual language to benchmark tooling: a compact recent-runs
table, grouped report fields, inspect sections, side-by-side diffs and readable tail status.
Green indicates completed runs, amber unfinished runs, red failures; labels remain explicit.
Respect terminal support, NO_COLOR and narrow widths. Never truncate identifiers or report
fields. Missing metrics render as n/a. Preserve the existing 160-character passage preview.

Keep the overview read-only, ordered newest first and limited to ten runs. Preserve missing
store behavior without creating a database. Replace its automatic help dump with action hints;
full help remains under --help. `show` and `inspect --json` remain plain, parseable JSON.

Presentation lives in bench/bench_view.py. Summary calculations, run execution, identities,
selection and library format_summary behavior remain unchanged. No live-screen tail redesign.
