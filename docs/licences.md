# Dependency licences

## Datasets

Terms of the datasets triplum downloads, generated from their catalogue entries when the site
is built.

<!-- dataset licences: generated from triplum.datasets.catalogue -->

## Build tooling introduced during the rebuild

| Dependency | Purpose | Upstream licence | Commercial reuse |
| --- | --- | --- | --- |
| `uv_build` | Build the pure-Python wheel and source distribution | MIT OR Apache-2.0 | Permitted under the chosen licence's terms; retain required notices |
| `numpy` | Embedding vectors as float arrays | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Permitted; retain copyright notices and licence texts |
| `sqlmodel` | SQL record stores (`triplum.store.sql`) | MIT | Permitted; retain copyright notice and licence text |
| `sqlalchemy` (via `sqlmodel`) | Database engine and SQL toolkit under SQLModel | MIT | Permitted; retain copyright notice and licence text |
| `bm25s` | BM25 retrieval (`triplum.steps.retrieval`) | MIT | Permitted; retain copyright notice and licence text |
| `griffe-fieldz` (docs group) | Render model fields as attribute tables in the API reference | BSD-3-Clause | Permitted; retain copyright notice and licence text |

Source: [uv-build package metadata](https://github.com/astral-sh/uv/blob/main/crates/uv-build/pyproject.toml).
This entry covers the new build backend; the former full dependency ledger remains in Git history.
