# Dependency-familiar junior developer

Coordinator: use the [workflow README](README.md) and
[shared reader prompt](reader-prompt.md). Reader: start at the coordinator-supplied
entry page; these workflow links do not extend your permitted corpus.

## Prior-knowledge hypotheses

Assume working knowledge of Python, Pydantic validation, NumPy arrays and basic
SQLAlchemy usage, but little experience designing reusable libraries or retrieval
systems. Treat this as a knowledge boundary, not a personality or a prediction
of junior developers' behavior.

## Goal

Understand triplum's particular behavior where familiar dependency names might
otherwise tempt you to assume the contract.

## Starter tasks

1. Find the documented source and chunk examples. Construct a small pair of
   related records and determine which fields express their identity and
   relationship; distinguish documented guarantees from Pydantic assumptions.
2. Choose a documented indexing-step Protocol and attempt a tiny deterministic
   replacement. Find the required input, output and configuration conventions,
   then exercise it on one small input using the documented integration route.
3. Find how to write and read those records through a documented store. Try the
   same small round trip with a second backend if the docs expose one, recording
   any difference in setup or promised behavior.

## Completion evidence

Show the minimal snippets, commands and results, with citations for the contracts
you relied on. List any familiar dependency behavior that the docs do not establish
for triplum. If replacement or storage cannot be completed from the documented
surface, identify the exact missing instruction without filling it in silently.

## Optional variations

- **Experience:** familiar with Pydantic and NumPy, but new to SQLAlchemy.
- **Debugging:** diagnose a supplied validation or vector-shape error, following
  the documented contract before guessing from dependency experience.
- **Compute:** deterministic local inputs and outputs; no hosted model required.
