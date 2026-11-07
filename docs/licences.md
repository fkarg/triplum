# Dependency licences

## Build tooling introduced during the rebuild

| Dependency | Purpose | Upstream licence | Commercial reuse |
| --- | --- | --- | --- |
| `uv_build` | Build the pure-Python wheel and source distribution | MIT OR Apache-2.0 | Permitted under the chosen licence's terms; retain required notices |
| MultiHop-RAG corpus (dataset) | News-article corpus for indexing examples (`triplum.datasets.multihoprag`) | ODC-BY 1.0 | Permitted with attribution |
| HotpotQA (dataset) | Multi-hop question-answering benchmark (`triplum.datasets.hotpotqa`) | CC BY-SA 4.0 | Permitted with attribution; adaptations must be shared under the same licence |
| HippoRAG protocol files (`reproduce/dataset/hotpotqa*.json`, commit `191f2811`) | 1,000-question HotpotQA sample and its passage corpus (`triplum.datasets.hotpotqa`) | MIT | Permitted; retain copyright notice and licence text. The HotpotQA content inside stays under CC BY-SA 4.0 |
| `numpy` | Embedding vectors as float arrays | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Permitted; retain copyright notices and licence texts |
| `sqlmodel` | SQL record stores (`triplum.store.sql`) | MIT | Permitted; retain copyright notice and licence text |
| `sqlalchemy` (via `sqlmodel`) | Database engine and SQL toolkit under SQLModel | MIT | Permitted; retain copyright notice and licence text |
| `bm25s` | BM25 retrieval (`triplum.steps.retrieval`) | MIT | Permitted; retain copyright notice and licence text |
| `griffe-fieldz` (docs group) | Render model fields as attribute tables in the API reference | BSD-3-Clause | Permitted; retain copyright notice and licence text |

Source: [uv-build package metadata](https://github.com/astral-sh/uv/blob/main/crates/uv-build/pyproject.toml).
This entry covers the new build backend; the former full dependency ledger remains in Git history.
