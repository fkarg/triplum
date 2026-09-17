# Forgiving CLI selection

Snapshot 2026-09-16.

Human-facing discovery is a priority across the CLI. Exact matches win, followed by case-
insensitive exact matches and unique prefixes. Single substring and plausible typo matches are
accepted too, with a notice on stderr; multiple matches require a choice. Typo plausibility uses
stdlib SequenceMatcher similarity at least 0.6; all qualifying candidates participate, not only
the highest score. Missing required finite selectors offer choices. Optional filters retain
their meaning: no question filter means all questions.

Apply this to commands, run IDs (show/rerun/inspect/diff/tail), question IDs, datasets,
pipelines, reader/judge kinds and embedder/reranker kind prefixes. Preserve opaque model IDs,
paths, URLs, numbers and JSON configuration verbatim. Library/store APIs stay exact. Unknown
option spellings retain parser errors/suggestions; do not rewrite argv or values.

Prompt only with terminal stdin and stderr. `--no-input` at the root, group or prompting command
disables prompts. Missing or ambiguous selectors in scripts exit with usable canonical
candidates; a single fuzzy match resolves automatically, including with --no-input. Prompts and
resolution notices use stderr; JSON stdout remains parseable. Selection has no default, permits
cancellation, and validates the chosen number. Run choices include identity, dataset, pipeline
and status. Empty stores and absent questions are usage errors.

One small selection module owns matching and prompt handling; existing command callbacks resolve
inputs before invoking exact library APIs. No TUI dependency or broad CLI split.

Tests use CliRunner, temporary real SQLite stores and fake pipeline fixtures; cover exact
precedence, unique/ambiguous prefixes, typo selection, omitted selectors, cancellation,
noninteractive behavior, canonical rerun identity and clean JSON. Measure branch coverage
explicitly in CI and on demand locally; always report durations. Mark real-model tests for an
explicit fast offline selection; keep them in normal pytest runs. Follow beancount-importer's
focused helpers and workflow testing, without copying its 100% global gate, five-second timeout
or parallelism unmeasured.

Sources: [CLI Guidelines](https://clig.dev/#interactivity), [Typer
parameters](https://typer.tiangolo.com/reference/parameters/), and [Click
prompts](https://click.palletsprojects.com/en/stable/prompts/).

## Test baseline

Local baseline before the behavior change: 95 passed in 16.08s without coverage; 92 passed in
3.46s with branch coverage when deselecting the three real-model tests. The two slowest real-
model tests took 8.52s and 4.19s. Offline combined coverage was 89% (CLI 87%). These are one-
machine observations, not timing assertions. Coverage surfaced existing unclosed SQLite
connection warnings; they are not suppressed. No whole-repository coverage gate is introduced by
this change.

 ## Design review

2026-09-17, Claude Opus 5, `peer-review --mode design`; verdict challenges, with concrete
falsification attempts. **Changed decision:** coverage is opt-in locally, explicit in CI (the
peer measured 7.05s covered vs 5.21s uncovered); accept --no-input at each prompting level.
**Added verification:** absent-store errors do not create files; missing second diff argument
offers candidates; data fetch resolves dataset/all; distinct diff IDs; adapter suffix preserved;
fixture identities differ so rerun tests discriminate correctly. **Rejected with reason:**
removing menus, fuzzy IDs and command prefixes contradicts the explicit user requirement. Random
IDs make similarity uncertain; the user explicitly chose autoaccept for a single plausible match
(2026-09-17), while multiple matches still prompt; document prefix instability for scripts.
Question IDs already select one question, so ambiguous matches choose one rather than silently
turning the option into a multi-row filter. The peer's claim that the diff test is unsatisfiable
applies to the old required signature; both arguments intentionally become optional so missing
selectors can prompt.