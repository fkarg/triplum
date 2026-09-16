# Readable reports implementation plan

Snapshot 2026-09-16.

1. Add renderer tests for wrapping, field/run preservation, numeric formatting and empty output.
2. Implement `format_summary(frame, width)` in bench/report.py using standard-library text wrapping.
3. Route the four CLI summary call sites through a terminal-width-aware print helper. Retain
   the existing dataframe helper for per-question diff output.
4. Add a report workflow test, update flow/API docs, run relevant tests and strict docs build,
   obtain a read-only review, and commit on main.
