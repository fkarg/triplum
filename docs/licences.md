# Dependency licences

## Build tooling introduced during the rebuild

| Dependency | Purpose | Upstream licence | Commercial reuse |
| --- | --- | --- | --- |
| `uv_build` | Build the pure-Python wheel and source distribution | MIT OR Apache-2.0 | Permitted under the chosen licence's terms; retain required notices |
| MultiHop-RAG corpus (dataset) | News-article corpus for indexing examples (`triplum.datasets.multihoprag`) | ODC-BY 1.0 | Permitted with attribution |
| `numpy` | Embedding vectors as float arrays | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Permitted; retain copyright notices and licence texts |
| `griffe-fieldz` (docs group) | Render model fields as attribute tables in the API reference | BSD-3-Clause | Permitted; retain copyright notice and licence text |

Source: [uv-build package metadata](https://github.com/astral-sh/uv/blob/main/crates/uv-build/pyproject.toml).
This entry covers the new build backend; the former full dependency ledger remains in Git history.
