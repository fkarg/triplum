# Benchmark overview

Snapshot 2026-09-16.

Bare `triplum bench` shows supported pipelines, the local run-store path, and up to ten
recent runs (newest first), with run id, dataset, pipeline, question count, and recorded state.
An absent or empty database shows `No local benchmark runs recorded.` The overview opens an
existing database read-only and does not create or migrate one. `--runstore` before a subcommand
is for the overview only; existing subcommand options retain their meanings.

Explain `ok` (completed), `failed` (ended with an error), and `running` (no completion recorded;
possibly interrupted). Explain that `run` reuses identical completed runs, `report` reads saved
metrics, and `rerun` can resume or force recomputation. End with generated Typer help.
Explicit help and subcommands do not inspect the overview's database.

Validation: CLI tests for absent/empty stores, recent run ordering and limits, state explanations,
generated commands, and read-only access. Existing CLI workflow tests protect subcommand dispatch.
