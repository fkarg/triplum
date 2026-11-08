# Dependency licences

triplum itself is licensed under the Apache License 2.0 (`Apache-2.0`), as stated in the
repository's `LICENSE` file and `pyproject.toml`.

## Datasets

Terms of the datasets triplum downloads, generated from their catalogue entries when the site
is built.

<!-- dataset licences: generated from triplum.datasets.catalogue -->

## Code dependencies

| Dependency | Purpose | Upstream licence | Commercial reuse |
| --- | --- | --- | --- |
| `uv_build` | Build the pure-Python wheel and source distribution | MIT OR Apache-2.0 | Permitted under the chosen licence's terms; retain required notices |
| `numpy` | Embedding vectors as float arrays | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Permitted; retain copyright notices and licence texts |
| `sqlmodel` | SQL record stores (`triplum.store.sql`) | MIT | Permitted; retain copyright notice and licence text |
| `sqlalchemy` (via `sqlmodel`) | Database engine and SQL toolkit under SQLModel | MIT | Permitted; retain copyright notice and licence text |
| `bm25s` | BM25 retrieval (`triplum.steps.retrieval`) | MIT | Permitted; retain copyright notice and licence text |
| `polars` | In-memory columnar datasets (`triplum.datasets.frames`) | MIT | Permitted; retain copyright notice and licence text |
| `pyarrow` | Arrow tables under the columnar datasets (`triplum.datasets.frames`) | Apache-2.0 | Permitted; retain licence text and any NOTICE file, state changes |
| `pydantic` | Record and settings models (`triplum.datatype`) | MIT | Permitted; retain copyright notice and licence text |
| `pydantic-ai` | Declared runtime dependency for LLM calls; not imported by triplum yet | MIT | Permitted; retain copyright notice and licence text |
| `pydantic-ai-slim` (via `pydantic-ai`) | The library `pydantic-ai` installs with its default extras | MIT | Permitted; retain copyright notice and licence text |
| `anthropic` (via `pydantic-ai`) | Anthropic provider SDK | MIT | Permitted; retain copyright notice and licence text |
| `openai` (via `pydantic-ai`) | OpenAI provider SDK | Apache-2.0 | Permitted; retain licence text and any NOTICE file, state changes |
| `google-genai` (via `pydantic-ai`) | Google Gemini provider SDK | Apache-2.0 | Permitted; retain licence text and any NOTICE file, state changes |
| `griffe-fieldz` (docs group) | Render model fields as attribute tables in the API reference | BSD-3-Clause | Permitted; retain copyright notice and licence text |

The `pydantic-ai` rows were checked against installed package metadata. `pydantic-ai`'s default
extras install further packages (among them `logfire`, `fastmcp-slim`, `tiktoken`, `starlette`,
`uvicorn` and the CLI helpers) whose terms are not recorded here. These rows cover the SDK code
only; each provider's API terms, including whether it trains on request data, are separate and
not recorded. Apart from the rows marked "via", transitive dependencies are not recorded either.

The `uv_build` row follows the [uv-build package metadata](https://github.com/astral-sh/uv/blob/main/crates/uv-build/pyproject.toml);
the former full dependency ledger remains in Git history.
