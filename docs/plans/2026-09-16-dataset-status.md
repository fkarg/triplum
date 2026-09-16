# Dataset Status Implementation Plan

**Goal:** Make `triplum data` list supported datasets and their local artifact state.

**Architecture:** Add a small status value and read-only inspection function beside the existing
HippoRAG artifact registry. Configure the `data` Typer group to call that function only when it
has no subcommand, then render its generated help; `fetch` remains untouched.

**Files:**

- Modify `python/triplum/eval/datasets/hipporag.py` — define dataset states and inspect the two
  registered artifact paths without creating or downloading anything.
- Modify `python/triplum/bench/cli.py` — render status rows for the bare `data` group.
- Modify `tests/test_datasets.py` — test no files, one file, verified files, and corrupt files.
- Modify `tests/test_config.py` — test the bare CLI group renders the list without downloads.
- Modify `README.md` and `docs/flow.md` — document `triplum data`.

## Steps

1. Add failing adapter tests for every state and a failing CLI test for the bare group.
2. Run those tests and confirm that the bare group currently shows help rather than status.
3. Add the minimal read-only availability function and `data` group callback.
4. Run the focused tests, then the full test suite and strict documentation build.
5. Commit the code, tests, spec, plan, and command documentation together.
