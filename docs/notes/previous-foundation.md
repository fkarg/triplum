# Previous foundation: temporary reference

This note is for the foundation rewrite. It records where to recover the
previous specs and plans without making their old interfaces into current requirements. Remove
each section when its replacement layer lands; remove this note when the walk is complete.
Use `git show <commit>:<path>` to read the full record. Current decisions live in
[`design.md`](../research/design.md), run semantics in [`benchmarking.md`](../benchmarking.md),
and implementation state in [`flow.md`](../flow.md).

## Sources and loading

The former universal dataset model gave way to indexed/streaming sources with source-owned
fingerprints. The built-in source and local-folder work established lazy iteration, stable
document/chunk ids, and cross-source gold checks. Layer 1 still needs batch-atomic ingestion;
the current runner materializes whole corpus frames. Earlier contracts and reviews:

| Record | Last historical version |
|---|---|
| Dataset registry spec | `git show 3d18d44:docs/specs/2026-09-17-dataset-registry.md` |
| Dataset/loader spec and plan | `git show 3d18d44:docs/specs/2026-09-17-datasets-and-loaders.md`; `git show 2e46773:docs/plans/2026-09-17-datasets-and-loaders.md` |
| Built-in datasets spec and plan | `git show a49585b:docs/specs/2026-09-17-builtin-datasets.md`; `git show 462894c:docs/plans/2026-09-17-builtin-datasets.md` |
| Local files spec | `git show 3d18d44:docs/specs/2026-09-17-local-files.md` |

## Store, extraction, and runner

The original harness built the SQLite store and six retrieval baselines. The extraction baseline
added supported graph facts and intrinsic scores. The later stage work replaced whole-run code
fingerprints with argument keys, artifacts, execution manifests, and store effects. Open store,
adapter, and monitoring questions are in the [stack walk](../plans/stack-walk.md) and
the [caching gap map](../specs/caching-and-monitoring.md).

| Record | Last historical version |
|---|---|
| Harness spec and plan | `git show c08d977:docs/specs/2026-09-16-harness-and-baselines.md`; `git show 7890829:docs/plans/2026-09-16-harness.md` |
| Extraction baseline spec and plan | `git show 7aa3179:docs/specs/2026-09-17-extraction-baseline.md`; `git show 7aa3179:docs/plans/2026-09-17-extraction-baseline.md` |
| Stages spec and plan | `git show f48c900:docs/specs/2026-09-17-stages.md`; `git show 25861fe:docs/plans/2026-09-17-stages.md` |

The fixture-scale rules-extractor measurements and their interpretation were in
`git show 780b173:docs/flow.md` under “Extraction baseline numbers.” They are historical
comparators, not a current full-set result.

## Operator surface and tooling

The overview, terminal views, selection, and type-checking work established current CLI and
development behavior. The [CLI selection contract](../specs/cli-selection.md) remains
live because new commands must follow it.

| Record | Last historical version |
|---|---|
| Bench overview spec and plan | `git show c5b1c3e:docs/specs/2026-09-16-bench-overview.md`; `git show c5b1c3e:docs/plans/2026-09-16-bench-overview.md` |
| Dataset status spec and plan | `git show 04388be:docs/specs/2026-09-16-dataset-status.md`; `git show 04388be:docs/plans/2026-09-16-dataset-status.md` |
| Readable reports spec and plan | `git show c25f7e8:docs/specs/2026-09-16-readable-reports.md`; `git show c25f7e8:docs/plans/2026-09-16-readable-reports.md` |
| Bench views spec and plan | `git show 087b0ef:docs/specs/2026-09-17-bench-views.md`; `git show 087b0ef:docs/plans/2026-09-17-bench-views.md` |
| Data overview spec and plan | `git show 1635a9c:docs/specs/2026-09-17-data-overview.md`; `git show 1635a9c:docs/plans/2026-09-17-data-overview.md` |
| CLI selection plan | `git show 4c61862:docs/plans/2026-09-16-cli-selection.md` |
| Typing spec and plan | `git show a7fb5e7:docs/specs/2026-09-17-type-checking.md`; `git show a7fb5e7:docs/plans/2026-09-17-type-checking.md` |
| Event-log comparison | `git show 780b173:docs/research/tooling-event-logs.md` |

The pre-rewrite peer reviews changed the dataset identity, support/visibility, stage provenance,
and CLI selection decisions, and found implementation defects subsequently fixed with tests.
The specific outcomes remain in the historical specs above; the decisions that still bind the
project are in the live design record.
