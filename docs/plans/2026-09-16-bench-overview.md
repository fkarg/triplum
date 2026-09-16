# Benchmark overview implementation plan

Snapshot 2026-09-16. Spec: ../specs/2026-09-16-bench-overview.md.

1. Add CLI coverage for missing/empty databases, newest-ten selection, stored states, generated
   help and explicit help without database access. Use actual SQLite fixtures and the real CLI.
2. Add an invoke-without-command callback in `python/triplum/bench/cli.py`. Use a read-only
   SQLite connection, closed after the query, because `RunStore` initialization writes migrations.
   Render run metadata and concise state/action explanations before `ctx.get_help()`.
3. Update README, flow and API index. Run CLI tests and the strict documentation build.
4. Review and commit on main, as requested for this task.
