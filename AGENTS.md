# AGENTS.md

Conventions for anyone (human or agent) working in this repository. Read the README first.

## Current rebuild and review gate

The owner deliberately removed the previous documentation and much of the code on `v2-rewrite`.
The rebuild now continues on `main`. Cleanup removed orphaned source and obsolete tests, retaining
generic data utilities, `FrameDataset` and a disk cache with an explicit directory. The Python
package uses `uv_build`; there is no PyO3 bridge or model extra. The Rust core remains independently
in Cargo.
Do not describe the old pipelines as working, infer approval from surviving code, or restore deleted
subsystems wholesale. Git history is reference material, not the current architecture contract.

- Work in the existing checkout and branch. Do not create worktrees or switch branches for this
  rebuild unless the owner explicitly asks. Preserve concurrent edits.
- Rebuild **one interface at a time**, with the owner tightly involved. The current first review
  is indexing data and transformations: the owner proposes `Source` for identified input text,
  chunking into initial chunks with source references, then independently replaceable preparation
  of embedding text. Names and exact declarations remain open, as does whether generated summaries
  share a chunk type. A chunk may have multiple text representations (original text, description, questions),
  but one vector for the chosen embedding configuration. Do not silently turn these into separately indexed vectors.
- The owner decided to keep `Source` and `Chunk` in separate files under `datatype/` and build
  barebones pipelines that expand/generalize step by step. `datatype/` records stay plain Pydantic
  and backend-agnostic; relational (e.g. SQLModel) and graph persistence each get their own mapping
  behind a storage boundary, not as `datatype` subclasses. Store layout: capability Protocols in
  `store/protocols.py`, implementations grouped by backend technology (`store/sql/` shares its
  tables across SQL stores; backend-specific stores subclass the generic one where faster SQL
  exists). The graph database and the full set of record types remain open; this does not
  approve the whole indexing pipeline.
- Step contracts are `typing.Protocol` classes with an abstract `__call__` in `triplum.steps`
  (`Converter[A]`: item -> list[Source]; `Chunker`: Source -> list[Chunk]; `EmbeddingText`:
  Chunk -> str; `Embedder`: `dimensions` + list[str] -> float32 matrix). Our implementations
  subclass the Protocol explicitly; external ones fit structurally. Configuration and resources
  live in `__init__`. Type aliases only for data shapes (`Vectors`), not for behaviour; no
  `runtime_checkable`. Steps handle one item (embedding: one batch); pipelines map them over loaders.
- Keep upstream ingestion in mind: dataset → document/webpage/etc. loader → optional OCR or
  preprocessing → `Source`. The owner deferred those interfaces; do not design them yet.
- For each interface, draft the exact Python declaration and short, step-by-step documentation:
  purpose, inputs, outputs, guarantees, one usage example, and any unresolved tradeoffs.
  Explain supporting types at first use. Distinguish proposals from approved contracts.
- Have Claude Opus independently review and critique each draft before the owner's detailed
  review. Use `peer-review` on the host, outside the sandbox, as explicitly requested. Report the
  actual serving model, dissent, attempted falsifications and the impact of the review.
- Stop for the owner's review before implementing the contract or proceeding to the next
  interface. Agreement to this process is not blanket approval of future designs. Interface
  declarations and their documentation may be drafted for review; adapters and pipelines wait.
- Prefer simple functions and independent protocols. Add records, classes, inheritance or
  metadata only for concrete needs. Do not rebuild the old object hierarchy by default.
- Keep README's status and this review checkpoint current after approval. Record review outcomes
  with the interface draft until a new design record exists.

The principles below remain project requirements, but references to deleted documents describe
historical contracts or intended documentation locations. They do not authorize restoring their
old schemas or interfaces. Re-establish those contracts explicitly through the review above.
The retained Python tests, Cargo checks/tests, ty, Ruff and strict MkDocs build pass. The pure
Python package builds and installs independently of Rust. README records the verification scope.
Keep the test suite and pre-commit gates working as interfaces return. MkDocs navigation starts
with Home and the indexing/retrieval overview in `docs/flow.md`. Published MkDocs pages must never
link to drafts, specs or plans. Exclude these development records from the built site and search,
not merely from navigation. Verify documentation changes with `uv run mkdocs build --strict`.
Keep the overview honest about intended responsibilities versus implemented interfaces.
Keep the hand-written (non-API) docs in sync with the code actively, in the same change: when a
contract, record field, module path or behavior changes, update the concept and infrastructure
pages that describe it and re-run their examples. Delegate docs writing and sync passes to a
subagent regularly (after each interface change), giving it the changed code and the owner's
decisions; verify its build and spot-check its pages before reporting.

## What this is

triplum: a composable, benchmark-first sandbox for LLM knowledge-graph work (construction, GraphRAG
retrieval, storage backends, evaluation). Python-first, Rust behind a clean Arrow boundary where it
is measurably worth it. Bi-temporal facts and provenance-derived permissions are first-class and
enforced in the store, never post-hoc. Numbers over novelty.

**This is a research project.** It exists to measure techniques against each other on public
benchmarks and the owner's own corpora. Consequences that decide arguments:

- **Licences are recorded, not blocking.** A non-commercial dataset, model or weight is fine to
  use here; the row in `docs/licences.md` says what it would cost to reuse commercially, and
  that is the whole obligation. Never drop a candidate technique because its weights are
  research-only; never claim commercial reuse that the row does not support.
- **The library is the product.** Experiments are Python that recombines the modules; every
  capability is importable and composable without the CLI. The CLI exists for the repetitive
  operator tasks (fetch data, run, sweep, inspect, diff) and is a thin layer over library
  functions, never the only way to do something.
- **Baselines before novelty.** A new technique earns its place with a harness run against the
  cheap comparators (closed-book, BM25, dense, fusion, oracle; a non-LLM extractor), reported
  with the full run identity, or it stays a candidate in `docs/research/papers.md`.

## Documentation and source layout as it is rebuilt

- `docs/research/`: research foundation and the decision record. `design.md` is a living document:
  change a decision there when it changes, do not append contradictions. Use Git history for
  document provenance; current docs describe the current state without editorial timestamps.
- `docs/specs/` and `docs/plans/`: active development contracts. Superseded detail is kept as
  temporary notes with commit references only while its replacement layer is being designed;
  remove those notes when the replacement lands. Keep development records out of the published
  MkDocs site and search. Published pages must never link to drafts, specs or plans.
- `src/triplum/`: `datatype` holds the `Source` and `Chunk` records; `steps` the step Protocols
  with reference implementations; `store` one Protocol per storage capability (`RecordStore` with
  `MemoryStore` and the portable SQLModel-backed `SQLAlchemyStore` so far; SQL tables in
  `store.sql.tables`, backend-specific stores later); `utils.data` generic dataset/loading
  utilities, `utils.cache` the disk cache and `utils.fingerprint` the `Fingerprinted` mixin;
  `datasets` `FrameDataset` and reference datasets. The CLI entry point and Rust extension bridge
  are removed. `crates/` holds the independent Rust workspace. Add modules only as their
  contracts are reviewed.
- `tests/`: covers data loading, caching, fingerprints, steps, stores and pre-commit behavior. Rust tests run
  with `cargo test`, independently of Python.
- The indexing and ingestion prototypes, their example and tests are committed but remain under
  owner review. Do not treat them as approved interfaces or describe them as working APIs in prose
  docs. The generated API reference deliberately shows the live state of `src/`.

## Rules that are easy to get wrong

- **Placing code**: touches an LLM or a dataset loader, it is Python. Touches the graph or an index
  and Python is the measured bottleneck, or a better crate exists, it is Rust. Never port
  speculatively.
- **Data layer**: canonical tables in `design.md` D2 govern store and processing-stage boundaries.
  Generic `utils.data` datasets choose their record types and own a required `fingerprint()`;
  loaders only control consumption. Built-in sources live in `datasets`, not `eval`. Benchmark
  composition separates corpus from optional QA/extraction inputs; no universal task schema.
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
- **Licences**: every third-party dataset, model and code dependency goes into `docs/licences.md`
  with its terms and whether it survives commercial reuse; add the row when you add the
  dependency. Non-commercial terms never block adoption here (see the doctrine above). Code with
  no licence file is read-only. Never route private corpora through a provider that trains on
  traffic.
- **Secrets**: API keys come from the environment; never read, print or commit them.

## Human-facing tools and tests

- Use terminal color where it improves scanning (states, errors, next actions), respecting
  terminal capabilities and `NO_COLOR`. Keep explicit text labels so color is never required.

- Install the pure Python package with `uv sync`. Run `uv run pytest --cov`, `uv run ty check`,
  `uv run ruff check`, `uv run ruff format --check`, `cargo check`, `cargo test` and
  `uv run mkdocs build --strict`. Rust checks are independent of the Python package.
  Fix contracts and narrowing; do not hide errors with broad ignores, `Any`, or excluded modules.
- The pre-commit gate exports the index and runs `cargo check`, `uvx ty check`,
  `ruff check` and `ruff format --check` there.
  Keep checks isolated from unstaged/untracked work; never stash another session's changes.
  While working, run the modifying forms (`ruff format`, `ruff check --fix`) freely; the hook
  and CI are the checks.

- **Forgiving discovery is a priority on every user-facing surface.** Reuse the CLI selection
  policy: exact matches first, unique prefix/substring/typo matches accepted, multiple matches offered as
  choices. Missing required finite selectors should guide the user. Never expose a lookup
  traceback for an unknown name. Keep opaque paths/model IDs and library identities exact.
- Prompt only on a terminal, support `--no-input`, and keep prompts/diagnostics on stderr so
  structured stdout stays usable. New commands must follow `docs/specs/cli-selection.md`.
- Keep matching decisions locally testable and separate from command execution; split modules
  by responsibility rather than adding interfaces or single-use wrappers.
- Measure branch coverage and test durations. Test workflows with real temporary stores and
  deterministic fakes; mark real-model tests `model` so `pytest -m "not model"` stays fast.
  Do not hide missing coverage by excluding CLI modules, or add parallelism without measuring.

## Workflow

- Spec, then plan, then code. Tests for behaviour that crosses a module boundary; the 20-question
  fixture is the integration test for every pipeline.
- Commit coherent, verified changes periodically throughout the work; do not wait for the entire
  rebuild. No `Co-Authored-By` or agent attribution trailers in commits or PRs.
- **Two sources of truth, by kind.** `docs/research/design.md` holds decisions; `docs/flow.md`
  and `docs/api/index.md` hold implementation state. A decision changes in design.md, a status
  changes in flow.md; neither restates the other.
- **Docs track the code.** `docs/flow.md` (what a run does, implemented vs planned) and
  `docs/api/index.md` (module map: status, key symbols, contracts) describe the implementation
  state; a change that adds a module, a stage, a pipeline, a CLI command or moves something from
  planned to done updates them in the same commit. The API reference is generated at build time:
  the MkDocs hook `scripts/api_reference.py` adds one page per module under `src/` and its nav,
  so the reference shows the live code, reviewed or not, and new modules appear automatically.
  Under `mkdocs serve --dirty` it re-renders only pages whose module changed; keep it that way.
  `uv run mkdocs build --strict` must pass.
- **Docs teach one concept at a time.** Keep teaching pages short: state what the reader can do,
  show a small runnable example, then explain only the fields and behavior needed to understand
  it. Give each field context at first use. Put signatures and exhaustive detail in the generated
  API reference instead of repeating them in prose. Prefer local understanding over a tour of
  the whole architecture; link to the next concept when needed.
- New technique: it enters `docs/research/papers.md` as a candidate, gets a note when read, and
  reaches "adopting" only with a harness run showing the delta.
- Cross-model review at design gates via `peer-review --mode design|diff-review`; record the
  outcome (changed / added verification / rejected with reason / no impact) in the design record.
-  We are in the process of going through base steps step-by-step in close
   supervision from absurdly naive versions to upgrade and generalize them over
   time. I'm asking a lot of one-shot (design) questions and want quick
   (researched) feedback. I also probably want your help in writing code, but
   core decisions for everything will remain with me.
