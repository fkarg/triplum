# Embedding models and rerankers (September 2026)

Assembled 2026-09-16 for sub-project 2d, the embedding sweep. Scores were pulled that day; re-check
before pinning. Numbers marked **[LB]** come from the MTEB leaderboard's JSON backend
(`https://mteb-leaderboard-backend.hf.space/v1/...`), **[SR]** are vendor self-reports, **[calc]** are
our own aggregation or arithmetic, and *(unverified)* means no primary source was reached.

The question this file answers: **which locally runnable open embedders in 2026 match or beat
`text-embedding-3-large` on retrieval, and which go into the sweep.** Short answer: a lot of them,
and `text-embedding-3-large` is now a weak multi-hop retriever — it is a *cost* baseline, not a
quality target.

## 1. Leaderboard state

### 1.1 "MTEB retrieval score" no longer denotes one number

Three unrelated things are called MTEB v2: the `mteb` **library** 2.0 (2025-10-20), the
**`MTEB(eng, v2)` benchmark** (41 tasks, MMTEB paper, ICLR 2025), and the **leaderboard rewrite**.
`MTEB(eng, v1)` had 56 tasks / 15 retrieval; v2 has 41 / 10, **drops MSMARCO, NQ, DBPedia, Quora,
NFCorpus, SciFact**, and replaces ClimateFEVER / FEVER / HotpotQA with `*HardNegatives` variants
subsampled to the top-250 pooled documents per query. The maintainers' own description: v2 "resolves
a known scoring bug, uses updated task versions, and removes common fine-tuning datasets such as
MSMARCO for more comparable scores."

The two are **not convertible**. Same models, v1 Ret(15) vs v2 Ret(10) [LB]: gte-Qwen2-1.5B 58.29 →
50.25 (−8.0), SFR-Embedding-2_R 59.77 → 53.75 (−6.0), text-embedding-3-large 55.43 → 57.98 (+2.6),
Qwen3-Embedding-8B 62.76 → **69.44** (+6.7). Always state the version.

And as of today `MTEB(eng, v1)`, `MTEB(eng, v2)` and both Multilingual benchmarks are
**`displayOnLeaderboard=false`** [LB]; the visible retrieval tabs are **RTEB(beta)**, BEIR and ViDoRe.
Anyone saying "top of MTEB retrieval" in late 2026 is probably reading RTEB.

### 1.2 Contamination is inside v2, and the leaderboard publishes the receipts

Nils Reimers (MTEB co-author, Dec 2024): publishing the MTEB training splits "was a big mistake";
the benchmark now largely measures who overfits hardest *(quote from an indexed snippet of
x.com/Nils_Reimers/status/1870812625505849849; x.com returns 402 to fetch)*. Maintainer Kenneth
Enevoldsen's zero-shot definition — "not trained on other splits of the dataset used to derive the
task" — produces a per-model **ZS%** column. v2 dropped MSMARCO and NQ but **kept FEVER and
HotpotQA**, and the leaderboard's own `trainingDatasets` field shows who trained on them [LB]:

| Model | ZS% on `MTEB(eng, v2)` | Declared training on eval-derived retrieval sets |
|---|---|---|
| QZhou-Embedding | **48** | ArguAna, FEVER, FiQA, HotpotQA, MSMARCO, NQ, Quora |
| NV-Embed-v2 | **51** | ArguAna, FEVER, FiQA, HotpotQA, MSMARCO, NQ |
| bge-en-icl | 58 | same minus ArguAna |
| Qwen3-Embedding 0.6/4/8B | 95 | FEVER, HotpotQA, MSMARCO, NQ |
| bge-large-en-v1.5 | **100** | NQ only |
| gte-Qwen2-7B/1.5B, OpenAI, Voyage, Cohere | unknown | undisclosed |

NV-Embed's paper admits it (§4.1: "certain datasets (e.g. MSMARCO) are training splits of the MTEB
Benchmark"); the model card does not. Qwen3-Embedding's SFT list (paper Table 6) includes MS MARCO,
NQ and HotpotQA; the model cards do not say so.

Two artefacts not to cite: **`IEITYuan/Yuan-embedding-2.0-en`** is #1 on `MTEB(eng, v2)` Retrieval
(70.69) — a 0.6B/2048-ctx model scoring **59.86 on SCIDOCS** where every frontier model sits at
22–33, and absent from RTEB; **`jcorners/ingot-8b-r3`** tops Mean(Task) at 75.98 while being
**API-only, closed, solo-built** on Qwen3-Embedding-8B. And leaderboard **rank is a Borda count, not
score order**.

RTEB (beta since 2025-10-01) is the maintainers' fix: half-private datasets they run themselves. It
is currently degraded — the **Private column was withdrawn 2026-01-14** because Voyage AI
co-developed it and had privileged access (issue #3934), and Mean(Task) is nulled for most serious
models. RTEB numbers below are **[calc]**: our re-aggregation over the 20 tasks shared by all
well-covered models.

### 1.3 The table

| Model | Params | Dims (MRL) | Max ctx | `MTEB(eng, v2)` Ret | RTEB(eng) 20-task [calc] | License | Released |
|---|---|---|---|---|---|---|---|
| OpenAI text-embedding-3-large | n/d | 3072 (any) | 8192 | 57.98 | 63.45 | proprietary, $0.13/M | 2024-01-25 |
| OpenAI text-embedding-3-small | n/d | 1536 (any) | 8192 | 53.48 | 56.94 | proprietary, $0.02/M | 2024-01-25 |
| Voyage voyage-4-large | n/d | 1024 (256–2048) | 32000 | — | **78.92** | proprietary, $0.12/M | 2026-01-15 |
| Voyage voyage-4-nano | 180M+160M | 2048 (MRL) | 32000 | — | — | **Apache-2.0, open weights** | 2026-01-15 |
| Cohere embed-v4.0 | n/d | 1536 (256–1536) | 128k | *none published* | 66.91 | proprietary, $0.12/M | 2025-04-15 |
| Gemini gemini-embedding-001 | n/d | 3072 (128–3072) | 2048 | 64.35 | 73.00 | proprietary | 2025-07-14 |
| Gemini gemini-embedding-2 | n/d | 3072 (128–3072) | 8192 | *no text result* | 71.35 *(14/20)* | proprietary | GA 2026-04-22 |
| **Nemotron-3-Embed-8B** | 7.95B | 4096 (MRL) | 32768 | — | **79.95 (#1)** | **OpenMDW-1.1, commercial** | 2026-07-16 |
| Nemotron-3-Embed-1B | 1.14B | 2048 (MRL) | 32768 | — | 73.91 | OpenMDW-1.1 | 2026-07-16 |
| **Qwen3-Embedding-8B** | 7.57B | 4096 (32–4096) | 32K | **69.44** | 73.27 | **Apache-2.0** | 2025-06-05 |
| Qwen3-Embedding-4B | 4.02B | 2560 (MRL) | 32K | 68.46 | — | Apache-2.0 | 2025-06-05 |
| Qwen3-Embedding-0.6B | 0.60B | 1024 (32–1024) | 32K | 61.83 | — | Apache-2.0 | 2025-06-05 |
| harrier-oss-v1-27b | 27.0B | 5376 | 32k | — | — (MMTEB **74.27**, #1) | **MIT** | 2026-03-27 |
| harrier-oss-v1-0.6b | 0.6B | 1024 | 32k | — | — (MMTEB 69.01) | MIT | 2026-03-27 |
| **NV-Embed-v2** | 7.85B | 4096 (no MRL) | 32768 | 62.84 | 63.90 | **CC-BY-NC-4.0** | 2024-08-29 |
| gte-Qwen2-7B-instruct | 7.61B | 3584 | 32768 | 58.09 | — | Apache-2.0 | 2024-06-15 |
| gte-Qwen2-1.5B-instruct | 1.78B | **1536** (LB says 8960 — wrong) | 32768 | 50.25 | — | Apache-2.0 | 2024-06-29 |
| bge-en-icl | 7.11B | 4096 | 32768 | n/a (v1 Ret 62.16) | — | Apache-2.0 | 2024-07-25 |
| bge-m3 | ~0.57B | 1024 + sparse + ColBERT | 8192 | n/a | 54.50 | MIT | 2024-01-27 |
| bge-large-en-v1.5 | 0.34B | 1024 | **512** | 55.44 | 52.65 | MIT | 2023-09-12 |
| Linq-Embed-Mistral | 7.11B | 4096 | 32768 | 60.14 | — | **CC-BY-NC-4.0** | 2024-05-29 |
| SFR-Embedding-Mistral / -2_R | 7.11B | 4096 | **4096** | 59.33 / 53.75 | — | **CC-BY-NC-4.0** | 2024-01 / 2024-06 |
| EmbeddingGemma-300m | 308M | 768 (768/512/256/128) | **2048** | 55.69 | — | **Gemma ToU** | 2025-09-04 |
| jina-embeddings-v3 / v4 | 0.57B / 3.94B | 1024 / 2048 (MRL) | 8192 / 32768 | 54.29 / 56.15 | — / 68.04 | **CC-BY-NC-4.0** | 2024-09 / 2025-05 |
| jina-embeddings-v5-text-small | 677M | 1024 (32–1024) | 32768 | 60.07 | 67.33 *(14/20)* | CC-BY-NC-4.0 | 2026-02-17 |
| nomic-embed-text-v2-moe | 475M / 305M active | 768 (768/256) | **512** | 54.81 | 51.42 | Apache-2.0 | 2025-02-07 |
| snowflake-arctic-embed-l-v2.0 | 568M | 1024 (→256) | 8192 | 58.56 | 56.30 | Apache-2.0 | 2024-11-08 |
| granite-embedding-english-r2 | 149M | 768 | 8192 | 56.43 | 56.35 | Apache-2.0 | 2025-07-17 |
| granite-embedding-311m-multilingual-r2 | 311M | 768 (768–128) | 32768 | 52.55 | 57.84 | Apache-2.0 | 2026-04-20 |
| Octen-Embedding-8B / -4B | 7.57B / 4.02B | 4096 / 2560 | 32k | — | 79.61 / 77.30 | Apache-2.0 | 2025-12 |
| F2LLM-v2 (8 sizes, 80M–14B) | 80M–14B | 5120↓320 | 40960 | 73.08 (14B, meanTask) | — | Apache-2.0 + **open data** | 2026-03-09 |
| bitnet-embedding-0.6b | 0.6B **1.58-bit** | 1024 | 32k | 67.49 meanTask [SR] | — | MIT | 2026-07-15 |

**Successors that do not exist** (verified by HF org enumeration): no Qwen3.5/Qwen4 text embedder —
Qwen3-Embedding is 15 months old and still current; no NV-Embed-v3 (the line became Nemotron); no
gte-Qwen3; no BGE v2 general embedder; no nomic v3, no mxbai-embed-v2, no Arctic 3.0. **OpenAI has
shipped no new embedding model since January 2024** (verified against the full machine-readable
catalogue at `developers.openai.com/api/docs/models/all.md`); neither has Cohere since embed-v4.0.

**Licensing is the sharpest axis.** CC-BY-NC-4.0 — research only: **NV-Embed-v1/v2, Linq-Embed-Mistral,
the entire SFR-Embedding family, all jina-embeddings v3/v4/v5**. `nvidia/llama-embed-nemotron-8b` is
non-commercial under a bespoke licence. EmbeddingGemma is Gemma ToU, not OSI. Apache-2.0/MIT covers
Qwen3-Embedding, gte-Qwen2, Arctic, granite, Octen, F2LLM, harrier, bge-*.

## 2. Multi-hop QA specifically

The HippoRAG 2 baseline table (R@2/R@5 and EM/F1 per retriever) is already reproduced in
[`benchmarks-multihop-qa.md` §3.1](benchmarks-multihop-qa.md) and is not repeated here. What that
table does not tell you is how the *current* embedders rank.

**The only panel that exists.** *The Commercial Tax* (arXiv:2608.16096, Sanchez & Dehnad,
2026-08-17; verified title/abstract, single unreviewed preprint) runs **13 embedders on one identical
MuSiQue harness** under the HippoRAG-2 protocol with bootstrap CIs. MuSiQue **R@5 [95% CI]**:
Nemotron-3-Embed-8B 69.79 [68.13, 71.43] · **NV-Embed-v2 69.55** · gemini-embedding-001 67.24 ·
Nemotron-3-Embed-1B 64.32 · Cohere embed-v4 60.21 · Qwen3-VL-Embedding-8B 59.88 ·
**OpenAI text-embedding-3-large 59.48 [57.68, 61.29]** · mxbai-embed-large-v1 55.71 ·
text-embedding-3-small 55.38 · BGE-M3 54.93 · **voyage-3.5 54.08** (last). Its other finding: three of
four MuSiQue leaders (HippoRAG-2, PropRAG, SAG, KET-RAG) depend on the **non-commercial** NV-Embed-v2
without disclosing it.

Note what that panel does *not* contain: **nobody has published Qwen3-Embedding-0.6B/4B/8B under the
HippoRAG protocol.** Three differently-phrased search passes found only FrugalRAG (different
protocol) and passing mentions. That is a genuine gap, and it is the single most useful thing our
sweep can fill.

**Does leaderboard rank predict multi-hop recall?** No paper computes the correlation. Three
verified pieces of evidence, in descending strength:

1. **A clean rank inversion on the same dataset.** On `HotpotQAHardNegatives` nDCG@10 [LB],
   gte-Qwen2-7B (75.00) beats GritLM-7B (73.96). Under the HippoRAG protocol the order flips on all
   three datasets at once: GritLM 92.4/65.9/76.0 R@5 vs gte-Qwen2 89.1/63.6/74.8.
2. **Dynamic range collapses.** NV-Embed-v2 leads gte-Qwen2 by 12.4 nDCG@10 on BEIR HotpotQA but
   only 5.4 R@5 on the ~10k HippoRAG corpus. Small-corpus R@5 is a low-resolution signal.
3. **Harness noise rivals model differences.** Swapping the embedder inside HippoRAG 2 moves MuSiQue
   R@5 by **9.4 points** (NV-Embed-v2 74.55 → BGE-Large 65.13; SAG, arXiv:2606.15971), while the same
   swap moves SAG by 1.35 — PPR propagation amplifies embedding quality hop by hop. Query formatting
   moves MuSiQue R@5 by **2.65** (NV-Embed-v2 uninstructed 66.90 vs 69.55) to **11.6** points
   (Qwen3-VL-Embedding-8B sweep), and corpus format (`title\ntext` vs text-only) by up to **4.73**.

The honest conclusion is not "MTEB doesn't correlate" but: *the measurement noise from harness
choices is the same size as the between-model differences we are trying to rank.* Hence: hold the
pipeline fixed, pin the template, embed passages as `title\ntext`, and report CIs.

**LinearRAG cannot go in a recall table at all** — it reports Contain-Acc / GPT-Acc only, and both it
and GFM-RAG run their HippoRAG-2 reproductions on `all-mpnet-base-v2`, which scores **39.29** on BEIR
HotpotQA, dead last in our whole [LB] pull. That alone explains their "HippoRAG 2 underperforms" rows.

### 2.1 Prefixes and instructions — where recall silently leaks

Every model below with `"default_prompt_name": null` returns **no prefix and no warning** from a bare
`model.encode(text)`. All strings verified byte-for-byte from repo config files.

| Model | Query prefix (exact) | Passage prefix | Pooling | Trap |
|---|---|---|---|---|
| Qwen3-Embedding 0.6/4/8B | `Instruct: {task}\nQuery:` — **no trailing space** | `""` | last-token + L2 | `padding_side` unset in `tokenizer_config.json` → HF defaults to `right` → **batched last-token pooling is silently wrong**. Must set `left`. EOS auto-appended. |
| NV-Embed-v2 | `Instruct: {task}\nQuery: ` — **with** space | `""` | latent-attention | `trust_remote_code`; ST path needs manual EOS and `padding_side="right"` |
| gte-Qwen2-7B-instruct | `Instruct: {task}\nQuery: ` | none | last-token + L2 | left padding comes free only via its custom tokenizer — does **not** carry to Qwen3 |
| e5-base/large-v2, multilingual-e5-large | `query: ` | `passage: ` | mean + L2 | one of the few with a real document prefix |
| e5-mistral-7b-instruct | `Instruct: {task}\nQuery: ` | none | last-token | origin of the shared task strings |
| multilingual-e5-large-instruct | `Instruct: {task}\nQuery: ` | none | **mean**, not last-token | no `prompts` block → `prompt_name="query"` is a silent no-op |
| bge-large-en-v1.5 | `Represent this sentence for searching relevant passages: ` (optional on v1.5) | **never** | CLS + L2 | — |
| **bge-m3** | **none — symmetric** | none | CLS | — |
| bge-en-icl | `<instruct>{task}\n<query>{q}` + trailing `\n<response>` | none | last-token | card prose says CLS; the **code is last-token**. Code wins. |
| EmbeddingGemma-300m | `task: search result \| query: ` | `title: none \| text: ` | mean → 2 dense → 768 | transformers < 4.57.0 silently falls back to causal attention; **no fp16** |
| Nomic v2-moe / v1.5 | `search_query: ` | `search_document: ` | mean + L2 | v1.5 has no `prompts` dict at all |
| jina-v3 | LoRA `retrieval.query` + `Represent the query for retrieving evidence documents: ` | LoRA `retrieval.passage` + `Represent the document for retrieval: ` | mean | omitting `task` **silently disables LoRA** |
| arctic-embed-l-v2.0 | `query: ` | none | CLS | v1.5 used the long BGE string — do not carry it over |
| granite-embedding (all), all-mpnet-base-v2 | **none — symmetric** | none | CLS / mean | — |

The useful coincidence: **Qwen3-Embedding, NV-Embed-v2 and e5-mistral ship the byte-identical
HotpotQA task string** `Given a multi-hop question, retrieve documents that can help answer the
question`, all inherited from `microsoft/unilm`'s e5 eval code. Only the wrapper template differs. So
the instruction text is a controlled variable and the template is not.

HippoRAG's own generic `Transformers.py` backend has **no model-family prefix logic** — plugging a new
embedder into that path lands squarely in the silent-no-prefix failure mode. Our
`SentenceTransformersEmbedder` has the same shape, which is why the prefixes belong in the spec.

## 3. Running locally

### 3.1 Apple Silicon (dev)

- **sentence-transformers + MPS** works for BERT-class models, but the "fp16 + FlashAttention = 3.87×"
  headline in the ST efficiency docs is a **CUDA** result — FA2 and input unpadding do not exist on
  MPS. Use **bf16, not fp16** (macOS 14+), `sentence-transformers >= 5.6.0`, PyTorch >= 2.13, and
  **measure MPS against CPU**, which often wins for small models. No published MPS throughput table exists.
- **MLX** (`Blaizzy/mlx-embeddings`) is the only path that properly drives the GPU for Qwen3-class
  embedders (BERT / ModernBERT / XLM-R / Qwen3 / Llama-bidirectional). Pre-1.0, **GPL-3.0**, no benchmarks.
- **llama.cpp GGUF is the pooling minefield.** Pooling is `none|mean|cls|last|rank`, and the conversion
  script historically **did not read `1_Pooling/config.json`**, leaving the GGUF default at NONE
  (discussion #12100; gte-Qwen2 emitted one vector per token). Live: Qwen3-Embedding-0.6B Q8_0 returning
  10×1024 for a 10-token input (#14543); EmbeddingGemma Q4_0 at cosine 0.02 against the reference
  (#16538); llama-cpp-python and llama-server disagreeing on the same GGUF (#17203). **Always pass
  `--pooling` explicitly and validate top-k ordering** against an fp32 reference before indexing.
- **Ollama is the worst option for retrieval correctness**: no pooling control, `truncate` defaults to
  **true**, `/api/embed` L2-normalizes while legacy `/api/embeddings` does not, and it applies **no task
  prefix** *(no maintainer statement found — high confidence, not primary-sourced)*.
- **fastembed (ONNX)** sidesteps all of it (25 curated models with correct configs) but is **CPU-only
  on macOS** — CUDA is its only documented execution provider — and has no Qwen3-Embedding.

### 3.2 NVIDIA, 8 GB VRAM (full runs)

Weights at 2 bytes/param [calc], against the verified anchor Qwen3-Embedding-0.6B GGUF F16 = 1.2 GB:

| Tier | fp16 | int8 | 4-bit | 8 GB verdict |
|---|---|---|---|---|
| 300M (EmbeddingGemma) | 0.6 GB | 0.33 | 0.17 | trivial |
| 0.6B (Qwen3, Nemotron-1B ≈1.14B → 2.3 GB) | 1.2 GB | 0.64 | 0.35 | comfortable |
| 1.5B (gte-Qwen2-1.5B) | ~3.6 GB | ~1.9 | ~1.0 | fits |
| **4B (Qwen3-4B)** | **~8.0 GB** | ~4.3 | ~2.4 | **fp16 does not fit** — needs int8/4-bit |
| 7.6–7.9B (Qwen3-8B, NV-Embed-v2) | ~15.2 GB | ~8.1 | ~4.4 | 4-bit only, tight |

Embedding models have no KV cache, so the dominant term is the attention score matrix when
FlashAttention is off: `batch × heads × L² × 2` = **~2.15 GB per sequence per layer** at L=8192 for a
16-head 0.6B model [calc]. With FA2 that term vanishes. **Think in token budget, not batch size.**

- **TEI** supports BERT / XLM-R / Nomic / ModernBERT / Mistral / **Qwen2 / Qwen3** / Gemma3, parses
  `1_Pooling/config.json` correctly (unlike GGUF conversion), and has `--default-prompt-name`. But
  `--dtype` accepts **only float16/float32 — no int8/int4/AWQ**, so TEI **cannot run Qwen3-Embedding-4B
  on 8 GB**, and **NV-Embed is not in its architecture list.** Set `--auto-truncate false` (defaults
  true) and tune `--max-batch-tokens` (default 16384) down.
- **vLLM** uses `--runner pooling` (`--task embed` is deprecated), supports Qwen3-Embedding natively
  (LAST + L2), exposes server-side **MRL via the `dimensions` pooling param**, and accepts quantized
  weights — the only way to reach the 4B tier on this card.
- **No throughput has been published for embedding on an 8 GB consumer GPU.** Our estimate for
  Qwen3-Embedding-0.6B at ~200-token passages is **~100–150 passages/s** [calc, ±2×] — ~80 s for a
  10k-passage corpus. Run `vllm bench serve --backend openai-embeddings --random-input 200` on the
  actual card instead of citing anything; expect tokenization, not matmul, to bind at this length.

### 3.3 Quantization and dimensions

Matryoshka truncation costs far more on **retrieval** than the aggregate mean suggests. EmbeddingGemma
(arXiv:2509.20354, Tables 6–8): `MTEB(eng, v2)` Mean(Task) 69.7 → 66.7 at 128d (−4.3% relative) but
**Retrieval 55.7 → 46.0 (−17.4%)**; 256d is already −7.7%. Granite-r2 shows the same shape more gently.
Qwen publishes no per-dimension table; its VL sibling reports 1024 → 512 costing **1.4%** on text
retrieval. **512d is near-free, 256d a real trade, 128d expensive. Re-normalize after truncating.**

Output-vector quantization (HF `embedding-quantization` blog): **int8 retains 90–100%** (Cohere-v3
100%, mxbai 97%, e5-base 94.7%) at 3.66× speedup — close to free. **Binary retains ~92.5% *without*
rescoring and 96.45% *with*** — the widely quoted 96% is a with-rescoring number. Qwen's VL paper
independently finds binary "significantly impairs effectiveness, with the loss growing as
dimensionality decreases", so **do not stack binary with aggressive MRL truncation**.

**Weight quantization below int8 is unvalidated for retrieval.** The one solid datapoint,
EmbeddingGemma, shows int4 costing only 0.36 points on `MTEB(eng, v2)` — but that is **quantization-aware
training**, evidence that embedders *can* be made 4-bit robust, not that post-training 4-bit is safe.
**No published Q8_0-vs-Q4_K_M MTEB delta exists for any embedding model.** The generative-LLM "Q4_K_M
≈ 3.5% loss" figure has no retrieval basis; do not import it. Damage here is silent — slightly worse
neighbours, no visible error, and an expensive index to rebuild.

## 4. Rerankers

| Model | Params | Ctx | License | Benchmark | Local |
|---|---|---|---|---|---|
| bge-reranker-v2-m3 | 568M | 8192 (trained 512) | Apache-2.0 | BEIR 56.51 (Jina harness) | yes, TEI-native |
| bge-reranker-v2-gemma | 2.51B | 512 | Apache-2.0 | BEIR 55.38 (mxbai harness) | yes |
| Qwen3-Reranker-0.6B / 4B / 8B | 0.6/4/8B | 32k | Apache-2.0 | BEIR 56.28 / **61.16** / — | yes (vLLM; **not TEI**; llama.cpp rerank bug #25447) |
| mxbai-rerank-base-v2 / large-v2 | 0.5B / 1.5B | 8k | **Apache-2.0** | BEIR 58.40 / **61.44** (Jina harness) | yes |
| jina-reranker-v2-base-multilingual | 278M | 1024 | CC-BY-NC | BEIR 57.06 | yes |
| **jina-reranker-v3 / v3.5** | 0.6B | 131k, 64 docs/pass | **CC-BY-NC** | BEIR **61.94 / 63.20** | yes (official MLX port) |
| Cohere rerank-v4.0-pro / -fast, v3.5 | n/d | 32k / 4k | proprietary | none published | no |
| Voyage rerank-2.5 / -3 / -lite | n/d | 32k | proprietary | +7.94% nDCG@10 vs Cohere v3.5 over 93 datasets | no |

**There is no bge-reranker-v3** — BAAI's line stops at v2.5-gemma2-lightweight (July 2024). The
frontier at 0.6B is now **listwise** (all candidates in one context window): jina-reranker-v3 at 0.6B
beats Qwen3-Reranker-4B on BEIR. **BEIR numbers are not comparable across vendor harnesses**
(mxbai-large-v2 is 57.49 in mixedbread's table, 61.44 in Jina's).

**Cost for the protocol (1000 questions × top-50 × ~200 tokens):** Cohere bills per *search unit* = one
query with up to 100 documents → **1000 units = $2.00** (rerank-3.5, verified on AWS Bedrock; the
direct-API rate is unverified). Voyage bills `(query_tokens × n_docs) + Σ doc_tokens` = 11.0M tokens →
**$0.55** (rerank-2.5), **$0.22** (lite), **$0.00** for rerank-3/-lite under their 200M free tokens.
Locally, 50,000 pairs with bge-reranker-v2-m3 is **~2–4 min on an 8 GB card, ~10–15 min on an M-series
Max** [calc — no reranker throughput has been published for consumer GPUs or Apple Silicon].
**Cost is not a decision input at this scale.**

**Whether to rerank at all is the real question, and the evidence is against spending much on it.**
BEIR HotpotQA shows BM25 0.603 → +CE 0.707 (+17% relative) — that number does not transfer. SetR
(ACL 2025) ablates reranker-vs-none on all three: bge-reranker-large buys **+2.41 EM on HotpotQA but
+0.75 on 2Wiki and +0.62 on MuSiQue**. HippoRAG 2's own LLM-filter ablation buys **+0.7 avg R@5 and is
net-negative on 2Wiki**, while changing the linking strategy buys +12.5. NV-Embed-v2 reaches only
**69.7 R@5 on MuSiQue** — ~30% of gold passages sit outside top-5 before any reranker runs — and
iterative retrieval (IRCoT) buys **8–10 EM points**. On BRIGHT an MS-MARCO cross-encoder actively
**hurts**, and hurts more the deeper you rerank (19.5 → 16.0 at depth 10 → **9.4** at depth 100). The
one serious counterweight (arXiv:2606.28367) finds the cross-encoder is the only enhancement
significant on MuSiQue — but reports significance without effect size, and its no-reranker nDCG@10 of
0.034 suggests its reranker is doing first-stage work.

**Conclusion: keep a reranker as a fixed, shallow control (depth ≤ 20), not as a tuning knob.**

## 5. The triplum sweep

`EmbeddingSpec` in `python/triplum/embed/protocol.py` already carries exactly the identity fields this
requires — `model, revision, dims, pooling, normalize, query_prefix, passage_prefix, quantization,
runtime` — and its hash names the vector table, so a prefix change forces a re-index. Two gaps to
close before the sweep: **`max_seq_length` / truncation policy is not in the spec** (silent truncation
changes vectors — TEI defaults `--auto-truncate true`, Ollama defaults `truncate: true`), and the
**instruction text should be recorded separately from the template** so the two can be varied
independently. Add both fields.

**Seven specs, three tiers.** Every passage is embedded as `title\ntext`; batch 32 on MPS / token-budgeted
(`--max-batch-tokens 8192`) on the 8 GB card; `normalize=True` everywhere (cosine); full native dims —
no MRL truncation in the primary sweep.

| # | `model` | Tier | `runtime` / `quantization` | `query_prefix` | `passage_prefix` |
|---|---|---|---|---|---|
| 1 | `openai/text-embedding-3-large` | API anchor | `api` / `none`, 3072d | `""` | `""` |
| 2 | `nvidia/NV-Embed-v2` | **literature anchor** (CC-BY-NC, research only) | `cuda` / 4-bit via vLLM, or offline MPS | `Instruct: Given a multi-hop question, retrieve documents that can help answer the question\nQuery: ` | `""` |
| 3 | `Qwen/Qwen3-Embedding-0.6B` | local default | `mps` bf16 / `cuda` fp16 (TEI) | `Instruct: Given a multi-hop question, retrieve documents that can help answer the question\nQuery:` (**no space**) | `""` |
| 4 | `Qwen/Qwen3-Embedding-4B` | local quality | `cuda` / int8, vLLM `--runner pooling` | same as #3 | `""` |
| 5 | `nvidia/Nemotron-3-Embed-1B` | 2026 commercial | `cuda` fp16 | per model card | `""` |
| 6 | `google/embeddinggemma-300m` | small / Apple | `mps` **bf16 (no fp16)**, or QAT int4 | `task: search result \| query: ` | `title: none \| text: ` |
| 7 | `BAAI/bge-large-en-v1.5` | cheap floor, 100% zero-shot | `mps`/`onnx` | `Represent this sentence for searching relevant passages: ` | `""` |

Rationale: #1 is the comparison target and cost baseline; #2 is required for cross-paper comparability
with [`benchmarks-multihop-qa.md` §3.1](benchmarks-multihop-qa.md), despite being unusable
commercially; #3/#4 are the Apache-2.0 tier that runs on our hardware and on which **no
HippoRAG-protocol numbers have ever been published**; #5 is the strongest commercially licensed open
model that fits 8 GB at fp16; #6/#7 bound the cheap end. Drop #5 or #7 first if trimming.
`Qwen3-Embedding-8B` and `Nemotron-3-Embed-8B` are the "bigger card" additions.

**Fixed reranker: `BAAI/bge-reranker-v2-m3`, fp16, `max_length=256`, depth 20**, served under TEI.
Apache-2.0, TEI-native, runs on both machines, and is the reranker the literature uses — so it is a
control, not a competitor. Record it in the run config and never tune it inside the embedding sweep.
`mixedbread-ai/mxbai-rerank-base-v2` (Apache-2.0, +2 BEIR points) is the upgrade if we ever make the
reranker a variable.

**Record per run, beyond the spec hash:** the resolved HF commit SHA (not a tag); instruction string
*and* template separately; `max_seq_length` plus a count of how often truncation fired; serving stack
and version (`tei` / `vllm` / `sentence-transformers` / `mlx-embeddings`); dtype; `padding_side`; batch
size; corpus format (`title\ntext`); wall-clock and passages/s for index and query; and a
**20-sentence fp32 reference fingerprint** (pairwise cosines + top-k ordering), so a runtime change
that silently alters vectors is caught at spec-creation time rather than in the metrics.

### Open questions

1. **Qwen3-Embedding under the HippoRAG protocol is unpublished.** Our sweep produces the first
   numbers. Report R@2/R@5 with bootstrap CIs — the between-model gaps are comparable to harness noise.
2. **Is NV-Embed-v2 runnable at all on our 8 GB card?** It is not in TEI's architecture list, needs
   `trust_remote_code`, and is 7.85B. Either 4-bit under vLLM (unvalidated for retrieval) or an
   offline MPS/CPU indexing pass. Resolve before the sweep, or the literature anchor is unreachable.
3. **Does post-training int8/4-bit weight quantization move R@5?** No published evidence for any
   embedder outside QAT. Cheapest test we can run: index MuSiQue at fp16 and int8 with the same spec
   and diff R@5, not mean cosine.
4. **Recall@k by hop index.** Nobody has published first-stage recall@{5,10,20,50,100} on MuSiQue or
   2Wiki split by hop. The harness makes it an afternoon's work and it would settle how much headroom
   a reranker can possibly recover.
5. **Prefix ablation.** The published numbers are all with-vs-without-correct-prefix *gains*; the cost
   of the *wrong* prefix is unmeasured. One run of #3 with no prefix would quantify the silent failure.
6. **`text-embedding-3-large` at reduced `dimensions`** — the MRL retrieval-vs-mean gap (§3.3) suggests
   the 256d configuration OpenAI advertises is worse for retrieval than the headline implies.
7. **Is the RTEB re-aggregation [calc] defensible to cite?** The official Mean(Task) column is nulled.
   Either reproduce it in-repo from the `embeddings-benchmark/results` clone with a pinned commit, or
   cite per-task scores only.

## Addendum (2026-09-16, later thread)

- **jina-embeddings-v4 licence correction.** The model card states the initial CC BY-NC 4.0 tag was
  an error; the operative licence is the **Qwen Research License** (derived from Qwen-2.5-VL-3B).
  jina.ai/models still shows CC BY-NC 4.0. Either way, not commercially permissive. jina-v3 and all
  v5 variants remain CC BY-NC 4.0. Source: https://huggingface.co/jinaai/jina-embeddings-v4 §License.
- jina-v5 tops out at "small" (no base/large); released 2026-02-18/19 with Elastic
  (https://arxiv.org/abs/2602.15547); card and release note disagree on MMTEB (67.7 vs 67.0).
- Confirmed negatives by org enumeration: no nomic-embed-text-v3, no Arctic-Embed 3.0, no
  mxbai-embed-v2 open weights, no granite r3, no EmbeddingGemma 2.
- MRL: Arctic-Embed 2.0 is 256 only; no MRL on granite r2 variants, multilingual-e5-large-instruct,
  gte-modernbert-base. EmbeddingGemma safetensors = 302,863,104 params; HF-gated under Gemma ToU.
- Granite papers: multilingual R2 https://arxiv.org/abs/2605.13521; English R2
  https://arxiv.org/abs/2508.21085 (311m-r2 MRL 768→128 costs 2.2 points, self-reported).
- Sub-150M entrants: lightonai/DenseOn (149M ModernBERT, Apache-2.0, BEIR-15 56.20 self-reported,
  512 ctx, https://arxiv.org/abs/2607.27178), lightonai/mDenseOn (307M, 8192 ctx),
  perplexity-ai/pplx-embed-v1-0.6b (596M, MIT, BEIR 56.70 as measured by LightOn).
- gte-modernbert-base and nomic modernbert-embed-base were never run on the four HardNegatives/v3
  tasks; their MTEB(eng,v2) Retrieval cells are not comparable, use BEIR-15 (55.19 / 52.89).

## Sources

**Leaderboards and benchmark design** — MTEB leaderboard API `https://mteb-leaderboard-backend.hf.space/openapi.json` ·
results repo `https://github.com/embeddings-benchmark/results` · MMTEB paper `https://arxiv.org/abs/2502.13595` ·
mteb library v2 `https://huggingface.co/blog/isaacchung/mteb-v2` · leaderboard rewrite `https://huggingface.co/blog/Samoed/mteb-v3-leaderboard` ·
RTEB `https://huggingface.co/blog/rteb` · RTEB fairness withdrawal `https://github.com/embeddings-benchmark/mteb/issues/3934` ·
scoring bug `https://github.com/embeddings-benchmark/mteb/issues/1156` · zero-shot definition `https://github.com/embeddings-benchmark/mteb/discussions/2351`, `.../issues/1760` ·
leakage audit `https://github.com/embeddings-benchmark/mteb/issues/1036` · Reimers `https://x.com/Nils_Reimers/status/1870812625505849849` *(snippet only)*

**Models** — `https://huggingface.co/Qwen/Qwen3-Embedding-{0.6B,4B,8B}` + `https://arxiv.org/html/2506.05176v1` ·
`https://qwenlm.github.io/blog/qwen3-embedding/` · `https://huggingface.co/nvidia/NV-Embed-v2` + `https://arxiv.org/pdf/2405.17428` ·
`https://huggingface.co/nvidia/Nemotron-3-Embed-8B-BF16` · `https://huggingface.co/google/embeddinggemma-300m` + `https://arxiv.org/abs/2509.20354` + `https://ai.google.dev/gemma/docs/embeddinggemma/model_card` ·
`https://huggingface.co/BAAI/bge-{large-en-v1.5,m3,en-icl}` · `https://huggingface.co/Alibaba-NLP/gte-Qwen2-7B-instruct` ·
`https://huggingface.co/intfloat/{e5-base-v2,e5-mistral-7b-instruct,multilingual-e5-large-instruct}` + `https://github.com/microsoft/unilm/blob/9c0f1ff/e5/utils.py` ·
`https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe` · `https://huggingface.co/jinaai/jina-embeddings-v{3,4}` ·
`https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0` · `https://github.com/ibm-granite/granite-embedding-models` + `https://arxiv.org/pdf/2605.13521` ·
`https://openai.com/index/new-embedding-models-and-api-updates/` · `https://developers.openai.com/api/docs/models/all.md` ·
`https://docs.voyageai.com/docs/pricing` · `https://cohere.com/blog/embed-4`

**Multi-hop** — HippoRAG 2 `https://arxiv.org/html/2502.14802v2` · HippoRAG 1 `https://arxiv.org/html/2405.14831v3` ·
GFM-RAG `https://arxiv.org/html/2502.01113v1` · LinearRAG `https://arxiv.org/html/2510.10114v4` ·
SAG `https://arxiv.org/html/2606.15971v2` · *The Commercial Tax* `https://arxiv.org/abs/2608.16096` ·
HippoRAG instruction source `https://github.com/OSU-NLP-Group/HippoRAG/blob/main/src/hipporag/prompts/linking.py` ·
BRIGHT `https://arxiv.org/abs/2407.12883` · IRCoT `https://arxiv.org/abs/2212.10509` · Adaptive-RAG `https://arxiv.org/abs/2403.14403` ·
SetR `https://arxiv.org/abs/2507.06838` · AAR `https://arxiv.org/abs/2604.20850` · `https://arxiv.org/abs/2606.28367`

**Runtimes and quantization** — `https://sbert.net/docs/sentence_transformer/usage/efficiency.html` ·
`https://huggingface.co/docs/transformers/en/perf_train_special` · `https://github.com/Blaizzy/mlx-embeddings` ·
`https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md` · `https://github.com/ggml-org/llama.cpp/discussions/12100` ·
`https://github.com/ggml-org/llama.cpp/issues/{14543,16538,17203}` · `https://docs.ollama.com/capabilities/embeddings` ·
`https://github.com/qdrant/fastembed` · `https://huggingface.co/docs/text-embeddings-inference/en/cli_arguments` + `https://github.com/huggingface/text-embeddings-inference` ·
`https://docs.vllm.ai/en/latest/models/pooling_models/embed/` · `https://huggingface.co/blog/embedding-quantization` · `https://huggingface.co/blog/matryoshka`

**Rerankers** — `https://huggingface.co/BAAI/bge-reranker-v2-m3` · `https://bge-model.com/bge/bge_reranker_v2.html` ·
`https://huggingface.co/Qwen/Qwen3-Reranker-0.6B` · `https://huggingface.co/mixedbread-ai/mxbai-rerank-large-v2` + `https://www.mixedbread.com/blog/mxbai-rerank-v2` ·
`https://jina.ai/news/jina-reranker-v3-0-6b-listwise-reranker-for-sota-multilingual-retrieval/` + `https://arxiv.org/abs/2509.25085`, `https://arxiv.org/abs/2607.18152` ·
`https://cohere.com/blog/rerank-4` · `https://aws.amazon.com/bedrock/pricing/` · `https://blog.voyageai.com/2025/08/11/rerank-2-5/` ·
`https://blog.voyageai.com/2025/10/22/the-case-against-llms-as-rerankers/` · `https://arxiv.org/abs/2510.08985`
