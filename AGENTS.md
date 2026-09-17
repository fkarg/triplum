# AGENTS.md

Conventions for anyone (human or agent) working in this repository. Read the README first, then
`docs/research/design.md`; the design record is the source of truth for architecture decisions.

## What this is

triplum: a composable, benchmark-first sandbox for LLM knowledge-graph work (construction, GraphRAG
retrieval, storage backends, evaluation). Python-first, Rust behind a clean Arrow boundary where it
is measurably worth it. Bi-temporal facts and provenance-derived permissions are first-class and
enforced in the store, never post-hoc. Industry-first: numbers over novelty.

## Where things live

- `docs/research/`: research foundation and the decision record. `design.md` is a living document:
  change a decision there when it changes, do not append contradictions. Every doc carries its
  snapshot date; versions and statuses are as-of that date.
- `docs/specs/`: one spec per sub-project, written and reviewed before code. `docs/plans/`: the
  implementation plan derived from a spec.
- `python/triplum/`: the Python package (`data`, `llm`, `ingest`, `extract`, `store`, `retrieve`,
  `generate`, `eval`, `bench`). `crates/`: the Cargo workspace. `notebooks/`: marimo notebooks.
  `research/`: SOTA monitor, digests, per-paper notes (planned).

## Rules that are easy to get wrong

- **Placing code**: touches an LLM or a dataset loader, it is Python. Touches the graph or an index
  and Python is the measured bottleneck, or a better crate exists, it is Rust. Never port
  speculatively.
- **Data layer**: the canonical tables in `design.md` D2 are the interface between modules. A
  module accepts and returns those frames; it does not define its own row model.
- **Visibility**: every store read takes a `Viewer`. Filtering happens inside the index, before
  ranking. Graph kernels run on the viewer's projection. Derived content inherits the ACL of its
  inputs and may never widen it. No community or global summaries until they are principal-scoped.
- **Time**: UTC integer instants; closed-open intervals; open ends are a max sentinel. Rows are
  never overwritten or deleted; invalidation closes and points at the invalidating fact.
- **Benchmarks**: every results table carries the closed-book, BM25-only and oracle-passage
  baselines, reports EM, F1, Contain-Acc, Judge-Acc, R@2, R@5 and indexing cost, holds the embedder
  fixed across pipelines, and records the full run identity (see `design.md` D8). The judge comes
  from a different model family than any reader under test.
- **LLM calls**: through the one `LLM` protocol with the disk cache; cache keys are the full
  effective request. Never call a provider SDK directly from pipeline code.
- **Benchmarks are cached by identity**: an identical configuration returns the stored run; use
  `--force` to recompute. Every expensive stage is content-addressed on its inputs and config and
  must still work with an empty cache. Anything that changes an answer goes into the run identity.
  The contract is `docs/benchmarking.md`.
- **Licences**: this repo is public and research-only, so non-commercial components are allowed
  here, but every third-party dataset, model and code dependency goes into `docs/licences.md` with
  its terms and whether it survives commercial reuse. Add the row when you add the dependency.
  Code with no licence file is read-only. Never route private corpora through a provider that
  trains on traffic.
- **Secrets**: API keys come from the environment; never read, print or commit them.

## Human-facing tools and tests

- Use terminal color where it improves scanning (states, errors, next actions), respecting
  terminal capabilities and `NO_COLOR`. Keep explicit text labels so color is never required.

- `uv run ty check` must pass across source and tests, alongside `cargo check`, lint and tests.
  Fix contracts and narrowing; do not hide errors with broad ignores, `Any`, or excluded modules.
  Keep the Rust extension stub aligned with its exports. Optional adapter imports are allowed
  only where absent in the lean environment; CI also checks with the `local` extra installed.
- The pre-commit gate exports the index and runs `cargo check`, `uvx ty check`,
  `ruff check` and `ruff format --check` there.
  Keep checks isolated from unstaged/untracked work; never stash another session's changes.

- **Forgiving discovery is a priority on every user-facing surface.** Reuse the CLI selection
  policy: exact matches first, unique prefix/substring/typo matches accepted, multiple matches offered as
  choices. Missing required finite selectors should guide the user. Never expose a lookup
  traceback for an unknown name. Keep opaque paths/model IDs and library identities exact.
- Prompt only on a terminal, support `--no-input`, and keep prompts/diagnostics on stderr so
  structured stdout stays usable. New commands must follow `docs/specs/2026-09-16-cli-selection.md`.
- Keep matching decisions locally testable and separate from command execution; split modules
  by responsibility rather than adding interfaces or single-use wrappers.
- Measure branch coverage and test durations. Test workflows with real temporary stores and
  deterministic fakes; mark real-model tests `model` so `pytest -m "not model"` stays fast.
  Do not hide missing coverage by excluding CLI modules, or add parallelism without measuring.

## Workflow

- Spec, then plan, then code. Tests for behaviour that crosses a module boundary; the 20-question
  fixture is the integration test for every pipeline.
- Commit small and often. No `Co-Authored-By` or agent attribution trailers in commits or PRs.
- **Docs track the code.** `docs/flow.md` (what a run does, implemented vs planned) and
  `docs/api/index.md` (module map: status, key symbols, contracts) describe the implementation
  state; a change that adds a module, a stage, a pipeline, a CLI command or moves something from
  planned to done updates them in the same commit. The per-package API pages are generated from
  the source, so a new module only needs a `::: module` line in `docs/api/<package>.md` and the
  nav in `mkdocs.yml`. `uv run mkdocs build --strict` must pass.
- New technique: it enters `docs/research/papers.md` as a candidate, gets a note when read, and
  reaches "adopting" only with a harness run showing the delta.
- Cross-model review at design gates via `peer-review --mode design|diff-review`; record the
  outcome (changed / added verification / rejected with reason / no impact) in the design record.
