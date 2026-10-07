# Cache utility command contract

The owner authorized per-computation tables and cache utility commands. This re-establishes command
selection for these utilities, not the historical CLI or benchmark runner.

```text
triplum cache stats [--path PATH] [--computation SHA256] [--details] [--json] [--no-input]
triplum cache clear [--path PATH] [--computation SHA256] [--json] [--no-input]
```

- Use the default cache path unless --path is given. Inspection must not create/open a writable
  database, start a writer or create directories. Missing caches report empty/missing.
- Finite command names match exact, then unique prefix, substring or close typo. Ambiguities list
  choices; missing commands show usage/choices. Paths and full SHA-256 identities remain exact.
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
- Commands wrap importable cache_stats(path, ...) and clear_cache(path, ...).
