# configs

`embedders-sweep.json`: the seven embedding specs from `docs/research/embeddings.md` §5, as
`EmbedderConfig` dicts for `triplum bench sweep --embedders configs/embedders-sweep.json`.
Prefix strings are byte-exact per model card (Qwen3 has no space after `Query:` and needs left
padding; NV-Embed-v2 has the space and needs right padding). Nemotron-3-Embed-1B's prefix is
"per model card" in the research doc and must be filled in before that row is run. NV-Embed-v2 is
CC BY-NC 4.0 (see `docs/licences.md`) and may not fit an 8 GB GPU (open question 2 in the doc).
The reranker is fixed at `BAAI/bge-reranker-v2-m3`, depth 20, and is not part of the sweep.

`query_template` may contain `{instruction}`; the adapter renders it into the spec's `query_prefix`,
so the task text and the wrapper are separate variables but only one string is ever sent.

`embedders-sweep-mac.json`: the subset that runs on an Apple Silicon laptop without API keys:
Qwen3-Embedding-0.6B (bf16 on MPS), bge-large-en-v1.5, EmbeddingGemma-300m (HF-gated: accept the
Gemma terms and `huggingface-cli login` first), and MiniLM as the floor. Retrieval metrics need no
reader (`--reader fake`); for QA metrics use `--reader claude-cli`.
