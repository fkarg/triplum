# Contributing

Conventions for humans and agents are in [AGENTS.md](AGENTS.md). The project is rebuilding one
interface at a time; surviving code and review prototypes are not automatically approved APIs.

## Checks

Install the pure Python package and development tools:

```sh
uv sync
```

The package uses `uv_build`. It has no PyO3 bridge or optional model extras. Rust remains an
independent Cargo workspace and is checked separately:

```sh
uv run pytest --cov --cov-report=term-missing:skip-covered
uv run ty check
uv run ruff check
uv run ruff format --check
cargo check
cargo test
uv run mkdocs build --strict
```

Measure branch coverage and test durations. Fix type errors at their contracts; do not hide them
behind broad ignores, `Any` or excluded modules. New behavior should have focused coverage of its
observable contract. Review prototypes remain separate from cleanup commits until approved.

## Pre-commit

`.githooks/pre-commit` exports the Git index to a temporary directory and runs `cargo check`,
`uvx ty check`, `ruff check` and `ruff format --check` there. Unstaged and untracked work stays out
of the check and is never stashed. Install the hook once:

```sh
ln -s ../../.githooks/pre-commit "$(git rev-parse --git-common-dir)/hooks/pre-commit"
```

Machines with a global hook dispatcher pick it up automatically. The hook reuses `.venv` and
the Cargo build cache; run `uv sync` first. Its `uvx` tools may differ from the versions locked
for `uv run`, so verify the actual hook before claiming it passes.

## Documentation

[The indexing and retrieval overview](docs/flow.md) describes the intended flow and rebuild state.
Keep its status accurate. Public MkDocs pages must not link to drafts, specs or plans; development
records are excluded from both the built site and search. Run the strict build after docs changes.

Follow the interface review process in AGENTS.md before adding implementations. Do not restore
historical dataset adapters, pipelines or release instructions merely because they existed before.

## Commits

Commit coherent, verified changes periodically. Use an imperative subject and no attribution
trailers. Preserve concurrent work and leave unapproved prototype files out of cleanup commits.
