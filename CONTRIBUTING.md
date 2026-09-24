# Contributing

Conventions for humans and agents are in [`AGENTS.md`](AGENTS.md); this page is the mechanics.

## Checks

```
uv sync --all-extras                       # builds the Rust extension via maturin
uv run pytest -m "not model"               # fast: fixtures and fakes, no model weights
uv run pytest                              # also the installed optional model adapters
uv run ty check                            # required on source and tests
uv run --extra local ty check              # the optional adapters against their real types
uv run cargo check                         # the Rust workspace, using the project's Python
uv run ruff check && uv run ruff format --check
uv run mkdocs build --strict               # docs must build clean
```

CI runs all of these on every push and pull request. Branch coverage is measured with
`uv run pytest -m "not model" --cov --cov-report=term-missing:skip-covered`; it stays opt-in
locally so single-test feedback is quick. Tests report their ten slowest cases.

Type errors are fixed at their contracts, never hidden behind broad ignores, `Any` or excluded
modules. Optional adapter imports may only be unresolved in the lean environment, and each such
module is listed under `[tool.ty.overrides]` in `pyproject.toml`.

## Pre-commit

`.githooks/pre-commit` exports the Git index to a temporary directory and runs `cargo check`,
`uvx ty check`, `ruff check` and `ruff format --check` there, so unstaged and untracked work
never enters the check and is never stashed. Install it once from the primary checkout:

```
ln -s ../../.githooks/pre-commit "$(git rev-parse --git-common-dir)/hooks/pre-commit"
```

Machines with a global hook dispatcher pick it up automatically. The hook reuses `.venv` and
the Cargo build cache; run `uv sync` first. `uvx` uses uv's tool version of ty and ruff, CI
uses the versions locked in `uv.lock`.

## Tests

Behaviour that crosses a module boundary gets a test; the 20-question fixture is the
integration test for every pipeline (`tests/integration/test_pipelines_fixture.py`). Workflows
are tested over real temporary SQLite stores with deterministic fakes. Tests that load real
model weights are marked `model`.

## Datasets and fixtures

Built-in sources live in `src/triplum/datasets/`. To add one, pin the upstream files in its
source, implement `fingerprint()` and lazy record iteration, register the source, and add its
licence and parser tests. Then build the fixture:

```
uv run python scripts/make_fixture.py <name>
```

Fixtures hold the first 20 questions with every chunk they need plus a deterministic fill of
distractors. Every fixture runs under the BM25 and oracle pipelines in the integration tests.

## Docs track the code

`docs/flow.md` describes implementation state; `docs/api/index.md` is the module map. Update
them with the code they describe. `docs/research/design.md` holds live decisions: change a
decision in place, do not append a contradiction. Temporary notes for layers being rewritten
point to the relevant commits and are removed when their replacement contracts land.

## Commits and releases

Small commits, imperative subject, no attribution trailers. Releases are tag-driven; see
[`docs/releasing.md`](docs/releasing.md).
