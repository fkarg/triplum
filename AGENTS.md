# Contributor instructions

Read [README.md](README.md) first. This file governs contribution and review; the
[overview](docs/flow.md) describes implementation state, and [CONTRIBUTING.md](CONTRIBUTING.md)
contains check commands and hook setup.

## Rebuild and review gate

- Work in the existing checkout and branch. Preserve concurrent edits; do not switch branches
  or create worktrees for this rebuild unless the owner asks.
- Rebuild one interface at a time, starting with simple functions and independent Protocols.
  Build barebones pipelines first, then generalize incrementally. Add records, classes,
  inheritance or metadata only for concrete needs. Surviving code and Git history do not
  establish approval. Do not restore deleted subsystems or the old object hierarchy wholesale.
- For each interface, draft the exact Python declaration, purpose, inputs, outputs, guarantees,
  one small example and unresolved tradeoffs. Introduce supporting types at first use and
  distinguish proposals from approved contracts.
- Have Claude Opus critique the draft using host `peer-review`, outside the sandbox. Report
  the serving model, attempted falsifications, dissent and its disposition: changed decision,
  added verification, unique defect, rejected with reason, or no impact.
- Stop for owner review before implementing a contract or advancing to the next interface.
  Declarations and docs may be drafted; adapters and pipelines wait for approval.
  Approval of the process is not blanket design approval. Keep decisions with the relevant
  spec until a dedicated design record exists.
- The owner authorized the first `triplum.cache` implementation and reuse example for review:
  decorators, `CachedStep`, manual access, replaceable storage, default Pydantic serialization,
  fingerprintable inputs/outputs and skip-and-count background writes. This does not authorize
  Source/Chunk ID migration or the remaining ingestion/indexing interfaces.
- Indexing/ingestion prototypes and their tests remain under owner review. Their appearance in
  generated API docs does not make them approved interfaces; do not describe them as working
  APIs in prose docs. The current handoff is
  [session-state.md](docs/plans/session-state.md); follow its linked specs for open decisions.

## Module and interface boundaries

- `datatype/`: separate, plain Pydantic Source and Chunk files; backend-agnostic records.
  Relational and graph mappings belong behind storage boundaries, not in datatype subclasses.
- `steps/`: behaviour uses `typing.Protocol` with abstract `__call__`; our implementations
  subclass explicitly, external implementations may fit structurally. No `runtime_checkable`.
  Configuration/resources live in `__init__`; aliases such as `Vectors` describe data only.
  Steps take one item, except embedding takes a batch; pipelines iterate over loaders.
- A chunk may have original text, descriptions and generated questions, but one indexed vector
  per chosen embedding configuration. Do not silently index each representation separately.
  Generated-summary types, hierarchy and graph records remain open.
- Upstream ingestion is dataset → document/webpage loader → optional OCR/preprocessing → Source.
  Its interfaces are deferred; keep the boundary in mind without designing it now.
- `store/protocols.py`: one Protocol per capability. Implementations are grouped by technology;
  `store/sql/` shares table mappings, with specialized subclasses where faster SQL is justified.
  Graph backend selection and the remaining record types are open. Store and cache are separate.
- `utils.data`: datasets choose their record type and implement `fingerprint()`; loaders control
  consumption. Built-in datasets belong in `datasets/`, not `eval`. Corpus and optional QA or
  extraction inputs compose separately; there is no universal benchmark-task schema.
- `cache/`: optional computation caching. `utils.cache` remains an independent file utility;
  `utils.fingerprint` holds configured-object fingerprinting. Select semantic identity fields
  explicitly; cache resources, policies and bookkeeping times do not enter value fingerprints.
- LLM calls and dataset loading belong in Python. Use Rust for graph/index work only when Python
  is a measured bottleneck or a better crate justifies it, behind a clean Arrow boundary;
  never port speculatively. `crates/`
  remains independent of the pure Python package, with no PyO3 bridge or model extra.

## Research and data requirements

This research project measures techniques on public benchmarks and the owner’s corpora.
These requirements describe the intended architecture, not capabilities of every current prototype. Deleted design/benchmark documents do not authorize restoring their old schemas.
Re-establish missing contracts through the review gate.

- The library is the product: every capability must be importable and composable without the
  CLI. Any CLI is a thin layer for repetitive operator tasks.
- Baselines precede novelty. Compare against closed-book, BM25, dense, fusion, oracle and a
  non-LLM extractor as applicable, with full run identity. Techniques enter the research record
  as candidates, receive a note when read, and become adopted only with a measured harness delta.
- Benchmark tables carry closed-book, BM25-only and oracle-passage baselines; report EM, F1,
  Contain-Acc, Judge-Acc, R@2, R@5 and indexing cost. Hold the embedder fixed across compared
  pipelines. The judge must come from a different model family than any reader under test.
- Every store read must take a Viewer. Filter within the index before ranking; graph kernels
  operate on the viewer's projection. Derived content may never widen input ACLs. Community
  and global summaries must be principal-scoped.
- Bi-temporal facts use UTC integer instants and closed-open intervals, with a maximum sentinel
  for open ends.
  Historical rows are not overwritten/deleted; invalidation closes them and identifies the
  invalidating fact. Current replace-by-ID prototypes do not satisfy this requirement.
- Provider calls belong behind one LLM protocol, with full effective requests as cache keys;
  pipeline code must not call provider SDKs directly. This interface remains to be rebuilt.
- Every expensive stage is content-addressed on its inputs/configuration and must work with an
  empty cache. Everything changing an answer belongs in run identity. An explicit benchmark
  bypass is intended; its interface and the rebuilt benchmark methodology remain deferred.
- Record all third-party dataset/model/code terms in `docs/licences.md`, including commercial
  reuse implications, when introducing or restoring a dependency. Never claim commercial reuse
  the recorded terms do not support. Research-only terms do not disqualify candidates; code without a licence
  is read-only. Never route private corpora through training-on-traffic providers. API keys come
  from the environment; never read, print or commit secrets.

## Documentation

- Keep decisions in specs/design records and implementation status in `docs/flow.md` and concept
  guides. Change the authoritative page and link to it elsewhere; do not maintain duplicate
  status inventories. Historical `docs/research/design.md` and `docs/api/index.md` are absent.
- Update hand-written docs in the same change as contracts, fields, paths or behavior; rerun
  affected examples. Update flow.md in the same commit when modules, stages, pipelines or CLI
  commands are added or move from planned to implemented. Delegate docs sync after interface
  changes, then inspect the edits and strict build yourself.
- Teach one concept per page: purpose, a small runnable example, then the needed fields and
  behavior. Put exhaustive signatures in generated API reference. Link to the next concept.
- `docs/specs/` and `docs/plans/` are development records, excluded from the built site and
  search. Published pages must not link to drafts/specs/plans. Remove superseded detail once
  its replacement lands; use Git history for provenance, not editorial timestamps.
- MkDocs navigation starts with Home and the indexing/retrieval overview. The hook
  `scripts/api_reference.py` generates a page per source module, including unapproved code.
  Preserve its changed-module-only refresh under `mkdocs serve --dirty`.

## Verification and workflow

- Spec, then plan, then code. Test observable behavior across boundaries with real temporary
  stores and deterministic fakes. The 20-question fixture is the integration test for every
  pipeline. Mark real-model tests `model` for fast non-model runs.
- Run the checks in CONTRIBUTING.md, including branch coverage, test durations, Cargo and strict
  MkDocs. Fix contracts/narrowing rather than hiding errors with broad ignores, `Any`, exclusions
  or skipped CLI coverage. Do not add test parallelism without measuring it.
- Pre-commit checks an exported index, never unstaged/untracked work. Never stash concurrent
  edits. Modifying Ruff commands are fine during development; hooks and CI check without edits.
- Commit coherent, verified changes periodically. Never add attribution or `Co-Authored-By`
  trailers. Core decisions remain with the owner; keep feedback focused and researched.

## Human-facing tools

- Forgiving discovery is a priority on every user-facing surface. Finite selectors try exact,
  then unique prefix/substring/typo matches; offer ambiguous choices
  and guidance for missing selectors. Keep opaque paths, model IDs and library identities exact.
  Unknown names must not expose lookup tracebacks. Matching is locally testable and separate
  from command execution. Split modules by responsibility, not single-use wrappers/interfaces.
- Prompt only on a terminal; support `--no-input`. Send diagnostics/prompts to stderr so stdout
  stays structured. Re-establish the historical CLI-selection contract before adding commands.
- Use color where useful, respecting terminal capabilities and `NO_COLOR`; always retain text
  labels so color is optional.
