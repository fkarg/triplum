# CLI selection implementation plan

Goal: forgiving human input with exact benchmark identities and fast, measured tests.
Architecture: one shared CLI selection module, invoked at command/parameter boundaries;
existing store and benchmark APIs retain their contracts. Python/Typer, stdlib matching,
pytest/CliRunner and SQLite. Work on local main as explicitly requested; no code delegation.

- [x] Add CLI regression tests in tests/test_cli_selection.py using real stored fixture
  runs: omitted IDs, prefix inspect, both diff IDs, rerun canonical identity, missing
  questions, fuzzy commands/choices, cancellation, noninteractive errors, JSON streams.
  Run `uv run pytest tests/test_cli_selection.py -q` and confirm failures.
- [x] Implement python/triplum/bench/selection.py: exact/prefix lookup then ranked
  substring/typo candidates (single candidates autoaccept), terminal-only numbered selection, stderr diagnostics;
  TyperGroup command resolution and --no-input context. Wire cli.py finite selectors
  and run/question lookup through it; preserve opaque suffixes and library APIs.
- [x] Re-run targeted tests, add uncovered boundary cases and fix defects.
- [x] Add pytest-cov branch measurement and duration reporting, mark real-model tests;
  measure `uv run pytest -m 'not model'` and the full suite before choosing any gate.
- [x] Update AGENTS.md, README, docs/flow.md, docs/api and design record with policy,
  implemented behavior, test commands and peer outcomes; record added dependency licence.
- [x] Attempt cross-model diff review (Claude OAuth expired); complete fresh-context
  fallback review and fix confirmed findings. Run pytest, ruff and strict
  mkdocs build. Commit on main; do not push or merge absent explicit authorization.
