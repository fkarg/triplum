# Benchmarks: registered datasets, protocol, reference numbers, candidates

Snapshot 2026-09-17. One note for everything about evaluation data: what is registered and
what each registration decided (§1), the protocol and metrics the harness implements (§2), the
published numbers a run can be compared against (§3), what is not registered and why (§4), and
the loader consequences and open questions (§5, §6). It replaces three earlier notes whose full
text, including the 114-row table of HTTP-verified fetch facts for the standard sets, is in git
history (`git show 13a6fa3^:docs/research/benchmarks-multihop-qa.md`, `benchmarks-catalogue.md`,
`benchmarks-standard.md`). Facts marked **[measured]** were computed over the released files;
everything else was read off the cited page. "Not stated" for a licence means no declaration on
the data page, never an inference.

## 1. Registered

`triplum data` lists these; `python/triplum/datasets/manifest.json` pins every file's URL,
sha256 and size; each has a committed 20-question fixture unless noted. Licences in full in
`docs/licences.md`. "MB" is the pinned download.

### 1.1 Multi-hop QA with a shipped corpus

| name | licence | MB | what it is; what the registration decided |
|---|---|---|---|
| `hotpotqa`, `musique`, `twowiki` (default) | CC BY-SA 4.0, CC BY 4.0, Apache-2.0; HippoRAG files MIT | 0 (GitHub raw) | the HippoRAG 1000-question protocol (§2.1). The corpus is the dedup by (title, text) of the sampled questions' candidate paragraphs: 9,811 / 11,656 / 6,119 passages **[measured]**. 2Wiki keeps its `evidences` triples as gold `triples`. |
| `hotpotqa_full` | CC BY-SA 4.0 | 27 | the official distractor dev set (7,405), corpus the union of inline paragraphs, gold resolved inside each question's own context so a title shared by two paragraphs cannot mis-assign. |
| `twowiki_full` | Apache-2.0 (xanhho mirror) | 30 | official dev (12,576); the parquet mirror keeps `evidences` but drops Wikidata ids; the official zip (259 MB, Dropbox) is not registered. |
| `musique_full` | CC BY 4.0 (bdsaglam mirror, no card tag) | 59 | the full dev file only (train is 477 MB); the 2,417 unanswerable twins load with an `__unanswerable` id suffix and `answerable=false`. |
| `morehopqa` | CC BY 4.0 | 4 | 1,118 verified questions with a gold decomposition; ships two inline paragraphs per question, not ten; corpus is their union (601 passages). |
| `multihoprag` | ODC-BY | 12 | 2,556 questions over 609 news articles; `published_at` becomes `observed_at`; the 301 null-query questions abstain with the dataset's own string. |
| `browsecomp_plus` | MIT | 4,543, large | 830 agentic questions over a 100,195-document frozen corpus with tiered gold; queries and doc ids are canary-obfuscated and decoded by the loader; the query shards may need a Hugging Face token; no fixture. |
| `bamboogle` | MIT | 0 | 125 compositional questions, no corpus. |

### 1.2 Question-only sets (no corpus; closed-book only until a shared Wikipedia corpus exists)

| name | licence | MB | notes |
|---|---|---|---|
| `popqa` | none declared | 5 | 14,267 long-tail questions with subject and object Wikidata ids and popularity in metadata. |
| `entityquestions` | MIT | 5 | test split, 24 Wikidata relations as `qtype`. |
| `nq_open` | CC BY-SA 3.0 | 0 | validation (3,610); answer list into answer plus aliases. |
| `ambigqa` | CC BY-SA 3.0 | 1 | dev (2,002); disambiguated answers unioned into aliases, annotations kept whole in metadata. |
| `freshqa` | Apache-2.0 (repo) | 0 | 600 questions whose answers change; the sheet is live, so the pin tracks the 2026-04-21 export; `fact_type` as `qtype`, false-premise flag in metadata. |
| `arc_easy`, `arc_challenge` | CC BY-SA 4.0 | 1 | science exam test splits; scored on the gold option's text with its letter as an alias. |

PopQA plus EntityQuestions is the standard "dense retrieval fails on tail entities" evidence,
which is exactly the claim a graph pipeline should beat once a shared corpus exists.

### 1.3 Reading comprehension and long documents

| name | licence | MB | notes |
|---|---|---|---|
| `squad`, `squad_v2` | CC BY-SA 4.0 | 3 | validation splits; the question's own passage is the gold chunk among 2,067 / 1,204 siblings; SQuAD 2.0's 5,945 unanswerable keep their passage in `candidate_chunk_ids`. |
| `boolq` | CC BY-SA 3.0 | 1 | validation (3,270); answers `yes` / `no`. |
| `quality` | CC BY 4.0 annotations; per-article licence in document metadata | 18 | htmlstripped dev: 115 articles (230 article sets) of 2,000-8,000 words as single chunks; 2,086 four-option questions scored on the gold option's text. |
| `qasper` | CC BY 4.0 | 4 | test: 416 NLP papers chunked into abstract, paragraphs and captions (the first multi-chunk documents in the registry); gold is the evidence paragraphs; 78 of 1,451 questions whose evidence is table content match no chunk and are not loaded. |

### 1.4 Temporal, memory, access control, knowledge edits

| name | licence | MB | notes |
|---|---|---|---|
| `ectqa` | MIT | 36 | 480 earnings-call transcripts (2020-2023 `old`, 2024 `new`), 1,005 local questions, 261 unanswerable; a quarter is a period, so `observed_at` stays 0 and year, quarter and split live in document metadata for an explicit ingestion protocol; the 100 global questions have no gold and are not loaded. |
| `tempo` | CC BY 4.0 | 2,407, large | 1,730 queries, 3,976 decomposed steps, 13 domains over 1.65 M Stack Exchange documents with `gold_ids` per step; no fixture. |
| `mquake_cf`, `mquake_t` | MIT | 24 | knowledge edits with labelled multi-hop consequences; pre-edit triples kept; **needs** fact invalidation in the runner. |
| `gatemem` | CC BY 4.0 | 7 | 91 episodes, 2,218 checkpoints with an asker, an as-of turn and an expected action (answer, refuse, redact, no memory); one document per turn with the speaker as grant; a quarter of turns lack a timestamp; **needs** a viewer per question. |
| `longmemeval_s` | MIT | 277 | 500 questions, each with its own session haystack, namespaced per question; **needs** a corpus per question. The `_m` variant (2.75 GB) is not registered. |

### 1.5 Text-to-triple gold (extraction-only: no questions, the runner refuses QA over them)

| name | licence | MB | notes |
|---|---|---|---|
| `graphjudge_genwiki`, `graphjudge_scierc`, `graphjudge_rebel` | MIT repo; GenWiki CC0, SciERC none declared, REBEL subset CC BY-NC-SA 4.0 | 57 | line-aligned text and gold triple sets; GenWiki-Hard has a few hundred non-3-tuples, kept in document metadata. |
| `genwiki`, `genwiki_fine` | CC0 1.0 | 279 (shared zip) | DBpedia-aligned triples per paragraph, distant supervision, entity-masked text. |
| `carb` | MIT | 1 | 634 test and 641 dev sentences with crowdsourced open-IE tuples; object is the joined remaining arguments. |
| `conll04`, `scierc` | none declared | 1 | typed spans and relations; entity spans in metadata; SciERC also has coreference clusters. |

### 1.6 A knowledge graph as the source

| name | licence | MB | notes |
|---|---|---|---|
| `metaqa` | CC BY 3.0 | 11 | the 134,741-triple movie KB loaded twice: as `triples` with `document_id`, for direct graph ingestion, and verbalised into one full-sentence chunk per entity (43,234; templates versioned in the parser), for text pipelines; 39,093 vanilla 1-, 2- and 3-hop test questions interleaved so any prefix mixes hops; gold is the topic's and the answers' chunks, which omit the middle entity of a 3-hop chain. Extraction over the verbalisation is a synthetic task. |

Any folder of local PDF, Word, Markdown or text files is also a dataset
(`docs/specs/2026-09-17-local-files.md`).

## 2. Protocol and metrics

### 2.1 The HippoRAG 1000-question protocol

Every GraphRAG paper reports against this and it is not "evaluating on HotpotQA". HippoRAG
([arXiv:2405.14831](https://arxiv.org/abs/2405.14831)) takes 1,000 questions from each
validation set, following IRCoT, and builds the corpus from all candidate passages (supporting
and distractor) of exactly those questions. The evaluation artefacts are
`reproduce/dataset/{2wikimultihopqa,hotpotqa,musique}.json` and `_corpus.json` in
[OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG).

| | questions | corpus passages | candidates before dedup | gold passages per question |
|---|---|---|---|---|
| HotpotQA | 1,000 | **9,811** | 9,942 | 2.00 |
| 2WikiMultiHopQA | 1,000 | **6,119** | 10,000 | 2.47 |
| MuSiQue | 1,000 | **11,656** | 20,000 | 2.65 |

**[measured]** The corpus is exactly `dedup_by((title, text))` over the union of candidate
paragraphs (2Wiki gives 6,120 against a file of 6,119, one whitespace collision). The HotpotQA
corpus changed between HippoRAG 1 (9,221) and HippoRAG 2 (9,811, the current file): a
HippoRAG-1-era recall number is not strictly comparable to a HippoRAG-2-era one; record the file
hash and label the generation. Composition **[measured]**: HotpotQA 811 bridge / 189 comparison,
all `hard`, 63 yes/no; 2Wiki 413 compositional / 244 comparison / 235 bridge-comparison / 108
inference, 110 yes/no; MuSiQue 518 two-hop / 316 three-hop / 166 four-hop, all answerable
(MuSiQue-Ans), 276 with aliases. The sampling rule behind the ids is undocumented: pin the id
lists, never regenerate them.

Prepackaged copies are not sources of truth: `Zly0523/linear-rag` declares no licence and no
derivation recipe; `102202132zbz/rag_test` ships an order of magnitude fewer passages and its
Apache-2.0 declaration cannot relicense CC BY-SA content. Upstream MuSiQue is Google Drive and
upstream 2Wiki is Dropbox, so re-verifying the HippoRAG files against upstream is not
automatable.

### 2.2 Metrics

- **EM and token-F1**: SQuAD normalisation (`white_space_fix(remove_articles(remove_punc(lower)))`),
  token-multiset F1. HotpotQA's official script zeroes F1 when one side is yes/no/noanswer and
  they differ; HippoRAG's `qa_eval.py` takes the max over a list of gold answers and has no
  yes/no rule. The harness uses HippoRAG's convention (max over aliases, no zeroing) so numbers
  compare to the GraphRAG literature, not the HotpotQA leaderboard; `eval/metrics.py` says so.
  EM and F1 penalise verbose answers (gold is 2.4-2.8 tokens **[measured]**), which is why the
  reader prompt is part of the run identity.
- **Recall@k**: HippoRAG's definition, `|top_k ∩ gold| / |set(gold)|`, macro over questions,
  papers report R@2 and R@5. The denominator is the gold count, not a fixed 2; HippoRAG matches
  by passage string, the harness by chunk id.
- **Contain-Acc**: gold string anywhere in the answer; cheap, deterministic, gamed by long
  answers. **Judge-Acc**: an LLM judge for semantic equivalence (FRAMES: Gemini-Pro-1.5, κ 0.889
  against humans; LongMemEval: GPT-4o; GraphRAG-Bench: GPT-4o-mini). The harness reports all
  four on every run because every paper picked a different one.
- **Pairwise judging without gold** follows BenchmarkQED AutoE
  ([microsoft/benchmark-qed](https://github.com/microsoft/benchmark-qed)): criteria
  comprehensiveness, diversity, empowerment, relevance (directness replaced by relevance from
  Edge et al.); tie mapped to 0.5; an even number of trials with position swap enforced;
  paired test with multiple-comparison correction; default judge `gpt-4.1`; a random `score_id`
  per call defeats caching, so a cached judge keys on `trial_index` instead. Not implemented
  yet; it is the scoring path for corpora without gold answers (§4.4 of the original note:
  AutoQ-synthesised questions, a designated `base` run, `base_run_id` on the comparison record).
- **Cost and latency**: per phase (index, retrieve, generate, judge): prompt, completion and
  cached tokens, wall-clock, LLM, retriever and embedding call counts. Indexing cost is a
  reported metric, since it is the axis on which GraphRAG loses and no QA table shows it.

### 2.3 Known problems to state in every results table

1. EM and F1 partly measure prompt terseness across papers with different reader prompts.
2. Judge bias is systematic: position bias flips direction across datasets
   ([IJCNLP 2025](https://aclanthology.org/2025.ijcnlp-long.18.pdf)); self-preference ranges
   −38% to +90% ([arXiv:2410.21819](https://arxiv.org/abs/2410.21819)); reversing summary order
   changed some RAG-vs-GraphRAG verdicts outright
   ([arXiv:2502.11371](https://arxiv.org/abs/2502.11371) §5.3). Counterbalance, use a judge
   from a different model family than any reader, report κ.
3. Contamination: CofCA's knowledge-edited passages drop GPT-4 2-hop EM from 69.9 to 53.1
   ([arXiv:2402.11924](https://arxiv.org/abs/2402.11924)); LastingBench reports leakage in
   HotpotQA specifically. Hence the mandatory closed-book baseline: it is the only cheap
   measurement of how much of a score the retrieval is responsible for.
4. N=20 is a smoke test, not a comparison: the standard error on EM at N=20 is about 0.11,
   wider than nearly every gap in §3. The corpus stays the full protocol corpus even at N=20,
   so the retrieval task is the real one.

## 3. Reference numbers

Two incompatible generations of the protocol exist, and most 2025-2026 GraphRAG papers abandoned
EM/F1 entirely. *Gen 1* (HippoRAG 1, 2024): GPT-3.5-turbo-1106 reader, ColBERTv2, HotpotQA
corpus 9,221, EM/F1 and R@2/R@5. *Gen 2* (HippoRAG 2, 2025): Llama-3.3-70B-Instruct reader,
NV-Embed-v2, corpus 9,811, F1 with MuSiQue's script in the main table. LinearRAG and EA-GraphRAG
use the same questions and corpora but report Contain-Acc / GPT-Acc with all-mpnet-base-v2 and
GPT-4o-mini; those never share a column with EM/F1.

### 3.1 Generation 2 (Llama-3.3-70B-Instruct, NV-Embed-v2, top-5), EM / F1 / R@5

From HippoRAG 2 ([arXiv:2502.14802v2](https://arxiv.org/html/2502.14802v2), Tables 2, 3, 8, 9)
unless noted.

| System | HotpotQA | MuSiQue | 2Wiki |
|---|---|---|---|
| No retrieval | 37.0 / 47.3 / — | 17.6 / 26.1 / — | 36.5 / 42.8 / — |
| BM25 | 52.0 / 63.4 / 74.8 | 20.3 / 28.8 / 43.5 | 47.9 / 51.2 / 65.3 |
| Contriever | 51.3 / 62.3 / 75.3 | 24.0 / 31.3 / 46.6 | 38.1 / 41.9 / 57.5 |
| GTE-Qwen2-7B-Instruct | 58.6 / 71.0 / 89.1 | 30.6 / 40.9 / 63.6 | 55.1 / 60.0 / 74.8 |
| GritLM-7B | 60.7 / 73.3 / 92.4 | 33.6 / 44.8 / 65.9 | 55.8 / 60.6 / 76.0 |
| **NV-Embed-v2, naive dense** | **62.8 / 75.3 / 94.5** | **34.7 / 45.7 / 69.7** | **57.5 / 61.5 / 76.5** |
| RAPTOR (reproduced) | 56.8 / 69.5 / 86.9 | 20.7 / 28.9 / 57.8 | 47.3 / 52.1 / 66.2 |
| MS GraphRAG (reproduced) | 55.2 / 68.6 / n.r. | 27.3 / 38.5 / n.r. | 51.4 / 58.6 / n.r. |
| LightRAG (reproduced) | 2.0 / 2.4 / n.r. | 0.5 / 1.6 / n.r. | 9.4 / 11.6 / n.r. |
| HippoRAG 1 (reproduced) | 52.6 / 63.5 / 77.3 | 26.2 / 35.1 / 53.2 | 65.0 / **71.8** / 90.4 |
| **HippoRAG 2** | **62.7 / 75.5 / 96.3** | **37.2 / 48.6 / 74.7** | **65.0 / 71.0 / 90.4** |
| PropRAG (L_max=3) [2504.18070v2] | — / 76.1 / 97.4 | — / 53.9 / 78.3 | — / 75.3 / 94.1 |
| BridgeRAG cond. C [2604.03384v1] | — / — / 98.75 | — / — / 81.46 | — / — / 95.27 |

Takeaways: the naive dense baseline beats every structure-augmented system except HippoRAG 2 on
HotpotQA, where HippoRAG 2's F1 advantage is +0.2; the real gap is MuSiQue (+2.9 F1, +5.0 R@5).
Swapping BM25 for NV-Embed-v2 moves HotpotQA F1 by about 12 points, every graph method by at
most 1: **hold the embedder fixed across pipelines or you are measuring the embedder**.
PropRAG's baseline rows are copied from HippoRAG 2, not replicated. The LightRAG reproduction
is contested (F1 2.4 here, 48.3 in GFM-RAG, mid-pack in LinearRAG): an order-of-magnitude
spread on the same system is a harness artefact, which is why the prompt is stored.

### 3.2 Generation 1 (GPT-3.5-turbo-1106 or GPT-4o-mini †, ColBERTv2), EM / F1 / R@5

HippoRAG 1 ([arXiv:2405.14831v3](https://arxiv.org/html/2405.14831v3)) and GFM-RAG († GPT-4o-mini,
all-mpnet-base-v2, [arXiv:2502.01113v2](https://arxiv.org/html/2502.01113v2)).

| System | HotpotQA | MuSiQue | 2Wiki |
|---|---|---|---|
| No retrieval | 30.4 / 42.8 / — | 12.5 / 24.1 / — | 31.0 / 39.6 / — |
| BM25 | n.r. / n.r. / 72.2 | n.r. / n.r. / 41.2 | n.r. / n.r. / 61.9 |
| **ColBERTv2, naive dense** | **43.4 / 57.7 / 79.3** | **15.5 / 26.4 / 49.2** | **33.4 / 43.3 / 68.2** |
| RAPTOR (ColBERTv2) | n.r. / n.r. / 75.6 | n.r. / n.r. / 46.5 | n.r. / n.r. / 64.7 |
| HippoRAG 1 (ColBERTv2) | 41.8 / 55.0 / 77.7 | 19.2 / 29.8 / 51.9 | 46.6 / 59.5 / 89.1 |
| IRCoT + ColBERTv2 | 45.5 / 58.4 / 82.0 | 19.1 / 30.5 / 53.7 | 35.4 / 45.1 / 74.4 |
| IRCoT + HippoRAG 1 | 45.7 / 59.2 / 83.0 | 21.9 / 33.3 / 57.6 | 47.7 / 62.7 / 93.9 |
| MS GraphRAG † | 35.3 / 54.6 / 76.6 | 13.4 / 29.5 / 49.3 | 28.3 / 46.9 / 77.3 |
| LightRAG † | 36.8 / 48.3 / 54.7 | 18.1 / 27.5 / 34.7 | 45.1 / 49.5 / 59.1 |
| GFM-RAG † | 51.6 / 66.9 / 87.1 | 30.2 / 40.4 / 58.2 | 69.8 / 77.7 / 95.6 |

### 3.3 Same protocol, Contain-Acc / GPT-Acc (all-mpnet-base-v2, GPT-4o-mini, top-5)

LinearRAG ([arXiv:2510.10114v4](https://arxiv.org/html/2510.10114v4), ICLR 2026).

| System | HotpotQA | MuSiQue | 2Wiki |
|---|---|---|---|
| No retrieval | 38.90 / 40.20 | — | — |
| **Vanilla RAG top-5** | **55.70 / 58.60** | **26.10 / 29.60** | **48.60 / 43.00** |
| RAPTOR | 55.90 / 58.30 | 23.30 / 27.40 | 50.10 / 42.10 |
| LightRAG | 60.30 / 59.50 | 27.40 / 28.60 | 55.20 / 39.00 |
| HippoRAG 1 | 57.00 / 59.30 | 29.30 / 24.10 | 66.10 / 59.90 |
| GFM-RAG | 62.70 / 65.60 | 29.90 / 34.60 | 66.80 / 59.60 |
| HippoRAG 2 | 62.90 / 64.30 | 31.00 / 35.00 | 62.70 / 55.00 |
| **LinearRAG** | **64.30 / 66.50** | **33.90 / 37.00** | **70.20 / 63.70** |

EA-GraphRAG ([arXiv:2602.03578v1](https://arxiv.org/html/2602.03578v1)) uses HippoRAG 2's exact
corpora, skips MuSiQue, does not state its embedder: HotpotQA Acc/GPT-Acc ColBERTv2 63.4/75.9,
HippoRAG 2 65.5/79.5, EA-GraphRAG 65.9/80.2; 2Wiki HippoRAG 2 67.7/72.5, EA-GraphRAG 76.3/81.5.

### 3.4 Rows that must not be merged with the above

LightRAG, MS GraphRAG and RAPTOR papers report none of the three datasets (their numbers above
are third-party reproductions). RAG vs. GraphRAG ([arXiv:2502.11371](https://arxiv.org/abs/2502.11371))
uses 1,000 hard-bridging HotpotQA questions on its own 256-token corpus. "Do We Still Need
GraphRAG?" ([arXiv:2604.09666](https://arxiv.org/abs/2604.09666), RAGSearch) uses full dev
splits over the 2018 Wikipedia dump with Qwen2.5 agents and Contain-EM; its headline, that the
agent loop moves scores far more than the index structure, is the closest published analogue to
this harness (HippoRAG 2 with the GraphSearch agent: 58.64 / 79.88 / 55.10 Contain-EM on
HotpotQA / 2Wiki / MuSiQue versus dense 38.22 / 47.43 / 13.33).

MuSiQue is the discriminating dataset and the worst covered: if only one runs at full scale,
run MuSiQue.

## 4. Candidates: what is not registered, and why

Sizes and licences were read from the primary page; rows from the standard-sets pass carry
HTTP-verified URLs in the git history noted above. Reasons fall into a few kinds: *no corpus*
(needs a pinned Wikipedia snapshot, a shared-corpus registration that does not exist yet),
*not a question set* (retrieval qrels, alignment pairs, schema induction: the canonical frames
do not represent them), *format* (own KB, PDFs, Drive or Dropbox hosting, gated, live web),
*licence settle first* (allowed here, but the row needs a declaration), and *size*.

### 4.1 Multi-hop and open-domain QA

- **WildGraphBench** (Apache-2.0, 1,197 questions, 3,932 files): reference pages joined by a
  slugified title, a 3,930-entry manifest; sentence answers need a judge. Deferred on effort.
- **FRAMES** (Apache-2.0, 824), **FanOutQA**, **NQ full** (56.8 GB, CC BY-SA 3.0),
  **TriviaQA** (11.7-17.3 GB, upstream Apache-2.0, card `unknown`), **ASQA** (14.6 MB),
  **QAMPARI** (108 MB, CC0), **IIRC** (5.7 MB, licence conflict in the archive), **HoVer**
  (12 MB, MIT), **FEVER** (39 MB), **WikiHop / MedHop** (202 / 58 MB, CC BY-SA 3.0),
  **StrategyQA** (3.4 MB, MIT), **WebQuestions** (0.4 MB, licence unknown): no shipped corpus or
  a corpus that is a Wikipedia dump. Register once a shared corpus (DPR `psgs_w100`, 4.7 GB,
  repo CC BY-NC 4.0; KILT Wikipedia, 37 GB; HotpotQA fullwiki abstracts, 1.6 GB, CC BY-SA 4.0;
  FEVER wiki, 1.7 GB) exists as its own registry entry with pinned id mappings.
- **DROP** (20 MB, CC BY-SA 4.0), **NarrativeQA** (193 MB), **CoQA** (12 MB, per-domain
  licences), **QuAC** (77 MB, CC BY-SA 4.0), **OpenBookQA** (0.8 MB), **TyDi QA** (29 MB
  secondary; 2.9 GB primary): inline passages, cheap; not yet registered for lack of a reason
  beyond coverage.
- **MS MARCO** (1-2 GB): custom non-commercial research terms; fine here, but the passage
  ranking set has no answer strings and the QA set is large. Held.
- **Loong** ([arXiv:2406.17419](https://arxiv.org/abs/2406.17419)): earlier notes called it
  ModelScope-only; on 2026-09-17 the authors' GitHub `data/loong.jsonl` (1,600 records) and the
  Alibaba OSS `loong/doc.zip` (33.9 MB) both answered anonymously, so it is fetchable and
  becomes a long-context multi-document candidate.
- **StratRAG** (Apache-2.0, 35 MB): a HotpotQA re-cut with gold at fixed pool indices; a
  deterministic retrieval-scoring fixture, not a result. **SealQA**, **BRIGHT** (CC BY 4.0,
  1.3 GB), **UltraDomain** (2.2 GB): reader robustness, reasoning-intensive retrieval, LightRAG
  win-rate reproduction; out of the multi-hop lane. **CRAG** (CC BY-NC 4.0, 8 GB, per-question
  HTML, mock KG API): adopt its label taxonomy (false premise, dynamism, popularity), not the
  data.
- Excluded for hosting or gating: LegalBench-RAG, RAG-QA Arena, Wiki-ZSL, EvolvingQA, MemBench
  (Drive or Dropbox), NovelQA (gated), InfoDeepSeek, CRAG
  task 3, RealTimeQA (live web), MINTQA, FinanceBench (PDFs).

### 4.2 Temporal, memory, abstention, access control

- **MenatQA** (2,853; scope, order, counterfactual over inline paragraphs; licence not stated),
  **HoH** (Apache-2.0; outdated pages injected into a corpus), **TimeQA** (~41k, BSD-3),
  **ChroKnowBench** (~65k, CC BY 4.0, per-year answer sets, no corpus). TempReason,
  ComplexTempQA, Test of Time, TRAM, DyKnow, TemporalWiki, StreamingQA, SituatedQA: no corpus
  or perplexity probes. TempRAGEval, TimeR4, T-GRAG, LiveSearchBench, EvoWiki, Chronos: no
  verifiable release. Knowledge-edit sets beyond MQuAKE: MQuAKE-Remastered (CC BY 4.0),
  RippleEdits (MIT), KnowEdit (MIT); none labels the invalidating fact, only old/new pairs.
- **BEAM** (CC BY-SA 4.0, 344 MB, 10 conversations to 10 M tokens, contradiction resolution
  scored separately), **MemoryAgentBench** (MIT, 77 MB), **LoCoMo** (CC BY-NC 4.0, 10
  conversations): memory sets after LongMemEval; MSC, PerLTQA, MemBench, Zep DMR excluded
  (ParlAI, Chinese, Drive, no corpus).
- **KUQ** (MIT, 6,884 unknowable or false-premise questions, no corpus), FalseQA, CREPE,
  SelfAware (no corpus), **AbstentionBench** (CC BY-NC 4.0, 20 datasets, `trust_remote_code`).
  ECT-QA's 19 false-premise items remain the only false-premise family on a shipped corpus.
- **RBAC-Text2SQL** (CC BY 4.0, 21,502; SQL, not retrieval): adopt its metric quartet (AC-F1,
  Safe-EX, violation rate, over-refusal rate). `respai-lab/RBAC` (280, no corpus). ARBITER: no
  release. GateMem arrived independently at four of the planned synthetic ACL benchmark's design
  points (principal-scoped questions, canary leak targets, refuse versus redact versus no
  memory, an as-of cut over an append-only log); cite it, do not claim them as novel. Nothing
  released has per-document ACLs with a retrieval-level leakage metric, or valid time,
  transaction time and a viewer together: the synthetic benchmark is still justified.

### 4.3 KG construction, KGQA over a KG, entity linking and alignment

- **BenchIE** (300 sentences per language, NEC academic non-commercial): strictest open-IE
  precision signal; optional. **LLMs4OL Challenge** (MIT; the 2025 edition's four tasks were Text2Onto, term typing,
  taxonomy discovery and non-taxonomic RE, the 2026 edition has Flagship, Reuse and Taxonomy
  with test sets on GitHub and submission by form): scores the induced schema, which the
  canonical frames do not represent. WikiEvents, SREDFM,
  FewRel, ADE: weak fit. NYT10/11, Wiki-ZSL, WiRe57, LSOIE, OIE2016, SAC-KG, OntoURL: withdrawn,
  unlicensed, Drive, or no release. EDC, Docs2KG, iText2KG are systems, not gold sets.
- **KQA Pro** (182 MB, author CC BY-SA 4.0; own Wikidata-derived `kb.json` with qualifiers,
  KoPL programs and SPARQL) is the next KG-as-source set after MetaQA; **WebQSP** (4.4 MB),
  **ComplexWebQuestions** (52 MB), **GrailQA** (18 MB, CC BY-SA 4.0), **FreebaseQA** (33 MB,
  CC BY 4.0), **SimpleQuestions** (Freebase 423 MB CC BY 3.0; Wikidata 4.8 MB) need Freebase
  (raw dump 403; the GrailQA Virtuoso setup is 56 GB); **LC-QuAD 1.0 / 2.0** (2.6 / 33 MB,
  GPL-3.0 / none), **QALD-9 / 10** (4 / 26 MB, MIT; QALD-10's frozen Wikidata is 57 GB),
  **Mintaka** (48 MB, CC BY 4.0), **CronQuestions** (84 MB, MIT), **TimeQuestions** (1.3 MB,
  none declared), **CFQ** (9 MB per split, CC BY 4.0) need DBpedia or Wikidata snapshots
  (DBpedia 2016-04 selected files 834 MB CC BY-SA 3.0; Wikidata5M 1.6 GB, no licence declared,
  not a drop-in graph for these sets).
- Entity linking: **AIDA-CoNLL** (52 MB, CC BY-NC-SA 4.0 mirror), **ZESHEL** (321 MB, CC BY-SA
  version unspecified), **Mewsli-9** (10 MB), **WikiDiverse** (0.7 MB, CC BY-SA 4.0; needs
  images), **TAC-KBP** (LDC agreement), MSNBC / AQUAINT / ACE2004 (CC BY-NC-SA 4.0 mirrors),
  **ZELDA** (477 MB, none declared). Alignment: **DBP15K** (84 MB, MIT), **OpenEA v2.0**
  (249 MB, CC BY-4.0). None are question sets; they need their own frames and metrics.
- **KILT** (11 tasks, MIT packaging, 4-547 MB each; provenance as Wikipedia ids and spans over
  the 37 GB KILT Wikipedia) and **BEIR** (19 sets, mostly CC BY-SA 4.0 cards; qrels with no
  answer strings; BioASQ, Signal-1M, TREC-NEWS, Robust04 behind agreements): retrieval
  benchmarks; register once the questions frame tolerates "no answer, graded relevance".

## 5. Fetch mechanics and loader consequences

- `https://huggingface.co/datasets/<id>/resolve/main/<file>` is anonymous for everything
  registered; pre-flight with `/api/datasets/<id>?blobs=true` (sizes, `gated`, licence) and the
  datasets-server `/info` endpoint. GitHub raw works anonymously including LFS; the GitHub JSON
  API is limited to 60 requests per hour and is not used. Google Drive needs `export=download`
  and, for legacy links, the public `resourcekey`. Live sheets (FreshQA) pin one dated export.
- Gold comes in four shapes: doc ids, titles or title-plus-text, URLs joined to files, and
  sentence strings. The loader maps the first two onto `gold_chunk_ids`; QASPER added exact
  text match of evidence strings; the last two are unsupported.
- A corpus can be absent (question-only sets), a second repository (BrowseComp-Plus), shared
  across sets (not yet), or a KG (MetaQA). The corpus and question hashes are separate
  identities; the questions hash now also covers gold triples.
- Supported since the registry landed: `answerable` with an abstain answer, `observed_at` from
  the data (MultiHop-RAG), per-document metadata for ingestion protocols (ECT-QA), gold
  `triples`, `needs` flags for runner capabilities still missing (a viewer per question, a
  corpus per question, fact invalidation), multi-chunk documents (QASPER, local files).
  Missing: an over-refusal counter on the answerable rest, per-hop gold scoring (MoreHopQA,
  TEMPO steps), per-document grants that are not `public` except GateMem's speaker grants.

## 6. Open questions

- The Liao et al. (SEMANTiCS 2026) best-practice GraphRAG pipeline is specified by the
  programme abstract only; get the PDF or ask the authors before implementing its exact
  variants.
- Why the HotpotQA corpus grew from 9,221 to 9,811 between HippoRAG 1 and 2 is unexplained;
  GFM-RAG's statistics table swaps the MuSiQue and 2Wiki sizes (reads as a typo).
- The LightRAG spread (F1 2.4 versus 48.3 on HotpotQA across reproductions) is undiagnosed; a
  small, citable result if the harness reimplements LightRAG.
- No paper scores extracted triples against 2Wiki `evidences`; the extraction baseline spec
  does, as evidence coverage. Decoding on Graphs
  ([arXiv:2410.18415](https://arxiv.org/abs/2410.18415)) and the imperfect-KG error taxonomy
  ([arXiv:2603.14828](https://arxiv.org/abs/2603.14828)) may overlap; unread.
- MuSiQue-Full paragraph coverage against the HippoRAG protocol corpus is unmeasured; a Full
  run is off-protocol either way and is labelled as `musique_full`.
- TEMPO per-domain sizes and whether `gold_answers` score without a judge: not inspected.
- Entity resolution on tables (Magellan, WDC) and open-IE canonicalisation (ReVerb45K, OPIEC):
  not researched.
- No 2026 consensus judge model; BenchmarkQED has no accompanying paper, cite the source.

## Sources

Datasets: HotpotQA [arXiv:1809.09600](https://arxiv.org/abs/1809.09600), MuSiQue
[arXiv:2108.00573](https://arxiv.org/abs/2108.00573), 2WikiMultiHopQA
[Alab-NII/2wikimultihop](https://github.com/Alab-NII/2wikimultihop), HippoRAG
[OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) (`reproduce/dataset/`,
`src/hipporag/evaluation/`), MoreHopQA [arXiv:2406.13397](https://arxiv.org/abs/2406.13397),
MultiHop-RAG [arXiv:2401.15391](https://arxiv.org/abs/2401.15391), BrowseComp-Plus
[arXiv:2508.06600](https://arxiv.org/abs/2508.06600), TEMPO
[arXiv:2601.09523](https://arxiv.org/abs/2601.09523), ECT-QA
[arXiv:2510.13590](https://arxiv.org/abs/2510.13590), LongMemEval
[arXiv:2410.10813](https://arxiv.org/abs/2410.10813), GateMem
[arXiv:2606.18829](https://arxiv.org/abs/2606.18829), MQuAKE
[princeton-nlp/MQuAKE](https://github.com/princeton-nlp/MQuAKE), GraphJudge
[arXiv:2411.17388](https://arxiv.org/abs/2411.17388), GenWiki (Edmond DOI 10.17617/3.YGO7EW),
CaRB [dair-iitd/CaRB](https://github.com/dair-iitd/CaRB), MetaQA
[yuyuz/MetaQA](https://github.com/yuyuz/MetaQA), QuALITY [nyu-mll/quality](https://github.com/nyu-mll/quality),
QASPER [allenai/qasper](https://huggingface.co/datasets/allenai/qasper), FreshQA
[freshllms/freshqa](https://github.com/freshllms/freshqa), Bamboogle
[ofirpress/self-ask](https://github.com/ofirpress/self-ask), and the Hugging Face cards of every
`<org>/<name>` id named in §1 and §4.

Protocol and systems: HippoRAG 2 [arXiv:2502.14802](https://arxiv.org/abs/2502.14802), LinearRAG
[arXiv:2510.10114](https://arxiv.org/abs/2510.10114), MS GraphRAG
[arXiv:2404.16130](https://arxiv.org/abs/2404.16130), RAPTOR
[arXiv:2401.18059](https://arxiv.org/abs/2401.18059), LightRAG
[arXiv:2410.05779](https://arxiv.org/abs/2410.05779), GFM-RAG
[arXiv:2502.01113](https://arxiv.org/abs/2502.01113), PropRAG
[arXiv:2504.18070](https://arxiv.org/abs/2504.18070), BridgeRAG
[arXiv:2604.03384](https://arxiv.org/abs/2604.03384), RAG vs. GraphRAG
[arXiv:2502.11371](https://arxiv.org/abs/2502.11371), RAGSearch
[arXiv:2604.09666](https://arxiv.org/abs/2604.09666), EA-GraphRAG
[arXiv:2602.03578](https://arxiv.org/abs/2602.03578), unified graph-RAG analysis
[arXiv:2503.04338](https://arxiv.org/abs/2503.04338).

Metrics: HotpotQA `hotpot_evaluate_v1.py`, BenchmarkQED
[microsoft/benchmark-qed](https://github.com/microsoft/benchmark-qed), CofCA
[arXiv:2402.11924](https://arxiv.org/abs/2402.11924), LastingBench
[EMNLP 2025 Findings](https://aclanthology.org/2025.findings-emnlp.993/), position bias
[IJCNLP 2025](https://aclanthology.org/2025.ijcnlp-long.18.pdf), self-preference bias
[arXiv:2410.21819](https://arxiv.org/abs/2410.21819).
