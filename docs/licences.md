# Dependency licences

## Build tooling introduced during the rebuild

| Dependency | Purpose | Upstream licence | Commercial reuse |
| --- | --- | --- | --- |
| `uv_build` | Build the pure-Python wheel and source distribution | MIT OR Apache-2.0 | Permitted under the chosen licence's terms; retain required notices |
| `mkdocs-gen-files` | Generate API reference pages from `src/` during the docs build | MIT | Permitted; retain notice |
| `mkdocs-literate-nav` | Build the API reference navigation from a generated summary | MIT | Permitted; retain notice |
| `properdocs` | MkDocs 1.x continuation, required by the two plugins above | BSD-2-Clause | Permitted; retain notice |

Sources: [uv-build package metadata](https://github.com/astral-sh/uv/blob/main/crates/uv-build/pyproject.toml)
and the other packages' PyPI metadata. These entries cover tooling added during the rebuild; the former full dependency ledger remains in Git history.
