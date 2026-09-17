# Type checking implementation plan

Snapshot: 2026-09-17.

**Goal:** required, honest `uv run ty check` compliance across source and tests.

**Architecture:** retain current module boundaries; correct their typing contracts. Keep lean
development supported and verify optional adapters with dependencies installed too.

**Tooling:** uv, ty, pytest, ruff, MkDocs.

- [x] Run the baseline checker: 67 diagnostics, largely repeated dataclass-copy errors.
- [x] Add ty to pyproject/lock and CI; document the requirement in AGENTS/README/design.
- [x] Replace dataclass dictionary copies in CLI and workflow tests with `replace(cfg, ...)`.
- [x] Narrow optional values in CLI/runner/tests; preserve missing-model price semantics.
- [x] Add `_core.pyi` matching Rust exports; narrow Arrow conversions to DataFrame.
- [x] Type Viewer's iterable constructor and immutable stored principals accurately.
- [x] Validate missing embedding dimensions; add a boundary test before changing behavior.
- [x] Run ty in lean and local-extra environments, tests, lint and strict docs.
- [x] Review the diff, record modularity findings and commit locally on main.

The user added a staged-snapshot commit gate with Cargo, ty and both Ruff checks.
Workflow tests cover success, checker failures, partial staging, untracked files, alternate
indexes, environment reuse and snapshot cleanup. Ruff formatting is baselined for the full project.
