# Command-line contract

The command line is the operator interface for repetitive tasks; see [Goals](../goals.md). Each
command is a thin layer over importable library functions. Pipelines are composed in Python, not
configured through command-line options, and no step runs as its own command.

## Scope

Implemented: cache management (below). Owner-agreed but not yet specified or built; each needs
its own contract here before implementation:

- Datasets and models: datasets download automatically on first use; the CLI shows download
  status and offers some management (list, download ahead of use, verify, remove, show recorded
  licence terms including commercial-reuse implications). The same applies to model weights
  (embedders, rerankers, local LLMs). Datasets are currently downloaded through the library only.
- Benchmark runs: launch a Python pipeline factory in benchmark mode (no cache reads or writes,
  seeded replicates, recorded run identity) with operator options only: seed, replicate count,
  dataset, output location. Depends on the unbuilt benchmark runner and run identity.
- Results: list, show and compare recorded runs as a table of EM, F1, Contain-Acc, Judge-Acc,
  R@2, R@5 and cost across runs and baselines, including replicate variance. Read-only over the
  run store; depends on benchmark runs.
- Stores: counts per record type, a source with its chunks, and ad-hoc search for checking an
  index by eye. Depends on the index/retrieval interfaces and on Viewer (search takes a viewer).
- Environment check: required keys set (never printed), dataset/model/cache locations reachable
  and writable, network/TLS working. Motivating case: uv-managed Python on NixOS failed TLS
  verification for the MultiHop-RAG download until `SSL_CERT_FILE` was set.

## Cache utilities

The owner authorized per-computation tables and cache utility commands. This re-establishes command
selection for these utilities, not the historical CLI or benchmark runner.

```text
triplum cache stats [--path PATH] [--computation SHA256 | --name NAME] [--details] [--json] [--no-input]
triplum cache clear [--path PATH] [--computation SHA256 | --name NAME] [--json] [--no-input]
```

- Use the default cache path unless --path is given. Inspection must not create/open a writable
  database, start a writer or create directories. Missing caches report empty/missing.
- Finite command names match exact, then unique prefix, substring or close typo. Ambiguities list
  choices; missing commands show usage/choices. Paths and full SHA-256 identities remain exact.
  A selector resolved by anything but an exact match reports its resolution on stderr
  (for example `cache c → cache clear`), so destructive commands never act on a silent guess.
- stats reports committed computation tables, database/WAL file sizes and reusable SQLite pages.
  --details opts into scans for exact entry counts and serialized payload bytes. Runtime counters
  and other owners' pending writes are not visible to this process.
- clear drops all cache computation tables, or the exact selected computation table. The command
  explicitly authorizes recomputable-data deletion: no prompt, on terminals or otherwise.
  --no-input is accepted. Clear does not unlink an open database or run VACUUM.
- Clearing is transactional and point-in-time. Writers may recreate tables with later commits.
  Freed pages become reusable; the file need not shrink. Unrecognized tables, including the former
  cache_entries table, remain untouched; there is no migration or legacy cleanup.
- Human output is concise; --json produces structured stdout. Errors/diagnostics go to stderr
  without tracebacks. Plain text is the baseline so NO_COLOR requires no special handling.
- --name selects recorded function names across computation fingerprints with the same forgiving
  matching as commands. The resolved names are reported on stderr and included in --json output.
- Commands wrap importable cache_stats(path, ...) and clear_cache(path, ...).
