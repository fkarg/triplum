# Required Python type checking

Snapshot: 2026-09-17.

`uv run ty check` must pass for the whole project, including tests, and run in CI.
Keep ty in the locked development dependencies. Fix inaccurate contracts and narrowing rather
than excluding code or disabling diagnostics. The Rust extension needs a stub matching its actual
Arrow schema export. Dataclass copies use `dataclasses.replace`.

The lean environment remains supported: optional model imports may be allowed only in their
adapter files when absent. Check with the `local` extra as well to verify those APIs against
installed dependencies. Do not replace installed dependencies' types with `Any`.

Preserve existing runtime behavior and constructor contracts, including Viewer accepting
iterables and storing immutable principals. Validate model dimensions at the external boundary.
No broad module split is needed to adopt typing. Assess existing module responsibilities separately.

The user also requires pre-commit `cargo check`, `uvx ty check`, `ruff check` and
`ruff format --check`, checking only what is
being committed. Export the Git index to a temporary directory and run all four commands there;
do not mutate or stash the working tree. Reuse the project's installed dependencies and
Cargo build cache. Delete the temporary export on exit. A check failure blocks the commit.
The user explicitly selected this over physically stashing unstaged and untracked work.

Official guidance: [installation](https://docs.astral.sh/ty/installation/),
[discovery](https://docs.astral.sh/ty/modules/),
[optional imports](https://docs.astral.sh/ty/reference/configuration/#allowed-unresolved-imports).
