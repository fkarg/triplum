# Benchmark protocol: agentic multi-hop QA for `triplum`

Status: research note, 2026-09-16. Scope: the first `triplum` sub-project — a harness that runs four
pipelines (Naive dense RAG; Hybrid dense+BM25+cross-encoder; Liao-style best-practice GraphRAG;
PPR-over-KG / HippoRAG 2 style) over public multi-hop QA datasets and produces numbers that are
comparable to published ones.

Everything below that carries a citation was read off the cited page or file. Facts I derived by
running code over the actual released data files are marked **[measured]** and the command is
reproducible from the file paths given. Claims I could not verify are in
[Open questions](#open-questions).

---

## 1. Datasets

### 1.1 The three core datasets

| | HotpotQA | MuSiQue | 2WikiMultiHopQA |
|---|---|---|---|
| Paper | Yang et al., EMNLP 2018, [arXiv:1809.09600](https://arxiv.org/abs/1809.09600) | Trivedi et al., TACL 2022, [arXiv:2108.00573](https://arxiv.org/abs/2108.00573) | Ho et al., COLING 2020 |
| Official repo | [hotpotqa/hotpot](https://github.com/hotpotqa/hotpot) | [StonyBrookNLP/musique](https://github.com/StonyBrookNLP/musique) | [Alab-NII/2wikimultihop](https://github.com/Alab-NII/2wikimultihop) |
| License | CC BY-SA 4.0 | CC BY 4.0 | Apache-2.0 |
| HF id | `hotpotqa/hotpot_qa` (configs `distractor`, `fullwiki`) | no canonical org mirror; `dgslibisey/MuSiQue` (Ans), `bdsaglam/musique` (both configs) | no canonical mirror; `framolfese/2WikiMultihopQA` |
| Splits | train 90,447 / dev 7,405 (both configs); `fullwiki` adds test 7,405 | Ans: train 19,938 / dev 2,417; Full: train 39,876 / dev 4,834 | train 167,454 / dev 12,576 / test 12,576 |
| Answer type | short span, plus `yes`/`no` | short span + `answer_aliases` | short span, plus `yes`/`no` |
| Supporting facts | `supporting_facts: [title, sent_id]` — **sentence-level** | `paragraphs[].is_supporting` — **paragraph-level**; plus `question_decomposition` | `supporting_facts: [title, sent_id]` **and** `evidences` as (subject, relation, object) triples |

Notes that matter for the harness:

- **HotpotQA `distractor` vs `fullwiki`.** Same questions, different retrieval setting. `distractor`
  gives 10 paragraphs per question (2 gold + 8 TF-IDF-retrieved distractors); `fullwiki` gives the
  question against all of Wikipedia. The 1000-question protocol below is built from the
  `distractor` context, *not* from a full Wikipedia dump. Split sizes and license per the
  [HF card](https://huggingface.co/datasets/hotpotqa/hotpot_qa).
- **MuSiQue-Ans vs MuSiQue-Full.** `Ans` is answerable-only; `Full` pairs each answerable question
  with a near-identical unanswerable one, so it is roughly 2× the size and additionally tests
  abstention. Split sizes confirmed against the HF datasets-server size endpoint for
  `dgslibisey/MuSiQue` (19,938 / 2,417) and `bdsaglam/musique` (`default` 39,876 / 4,834;
  `answerable` 19,938 / 2,417). The multi-hop RAG literature uses **Ans**.
- **MuSiQue leakage caveat, from the authors.** MuSiQue was composed from single-hop questions taken
  from SQuAD, Natural Questions, T-REx, MLQA and ZeroRE. Single-hop questions in MuSiQue dev/test may
  appear in the *training* sets of those seed datasets; the repo ships the seed ids so you can
  exclude them.
- **2Wiki has no public test labels.** The dev split is the de-facto test set.
- **2Wiki `evidences`** are literal KG triples. For a knowledge-graph library this is the single most
  interesting annotation in the three datasets: it gives a gold reference graph to score extracted
  triplets against, not just gold passages.

### 1.2 The de-facto protocol: IRCoT / HippoRAG 1000 questions

This is the protocol essentially every GraphRAG paper reports against, and it is not the same thing
as "evaluating on HotpotQA".

**Definition** (HippoRAG, [arXiv:2405.14831](https://arxiv.org/abs/2405.14831), §Experimental setup):
"we extract 1,000 questions from each validation set as done in previous work", following
IRCoT (Trivedi et al., 2023); the retrieval corpus is then built by "collecting all candidate
passages (including supporting and distractor passages)" from exactly those 1,000 questions. The
paper reports corpus sizes of 11,656 (MuSiQue), 6,119 (2Wiki), 9,221 (HotpotQA).

**Exact construction, from the released files.** The evaluation artefacts live in the HippoRAG repo
at `reproduce/dataset/{2wikimultihopqa,hotpotqa,musique}.json` and
`reproduce/dataset/{...}_corpus.json` ([OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG)).
I downloaded them and measured:

| | questions | corpus passages | candidate paragraphs before dedup | gold passages / question |
|---|---|---|---|---|
| HotpotQA | 1,000 | **9,811** | 9,942 | 2.00 |
| 2WikiMultiHopQA | 1,000 | **6,119** | 10,000 | 2.47 |
| MuSiQue | 1,000 | **11,656** | 20,000 | 2.65 |

**[measured]** The corpus is exactly `dedup_by((title, text))` over the union of all candidate
paragraphs of the 1,000 questions — for MuSiQue this reproduces 11,656 exactly; for HotpotQA it
gives 9,811 against a file of 9,811; for 2Wiki it gives 6,120 against a file of 6,119 (one
off-by-one, presumably a whitespace-normalisation collision). Corpus records are
`{"title", "text"}` (HotpotQA additionally carries `idx`). For HotpotQA/2Wiki, `text` is the
concatenation of the per-paragraph sentence list.

**The HotpotQA corpus changed between HippoRAG 1 and 2.** HippoRAG 1 states 9,221 passages;
HippoRAG 2 ([arXiv:2502.14802](https://arxiv.org/abs/2502.14802)) states **9,811**, which is what the
current `reproduce/dataset/` file contains **[measured]**. So "same corpus as HippoRAG" is ambiguous
and a HippoRAG-1-era HotpotQA recall number is not strictly comparable to a HippoRAG-2-era one.
Recommend: use the current file, record its content hash, and label the generation.

**[measured] Composition of the 1,000-question sets** (useful for smoke-test stratification):

- HotpotQA: 811 bridge / 189 comparison; **all 1,000 are `level == "hard"`**; 63 yes/no answers;
  mean answer length 2.42 tokens.
- 2Wiki: 413 compositional / 244 comparison / 235 bridge_comparison / 108 inference; 110 yes/no;
  mean answer 2.39 tokens.
- MuSiQue: 518 two-hop / 316 three-hop / 166 four-hop; all answerable (so it is MuSiQue-**Ans**);
  276 questions carry `answer_aliases`; mean answer 2.80 tokens.

The *sampling rule* that produced these particular 1,000 ids is not documented anywhere I could
find. Treat the id lists as the specification and pin them.

### 1.3 Prepackaged copies

- **[`Zly0523/linear-rag`](https://huggingface.co/datasets/Zly0523/linear-rag)** — the data release for
  LinearRAG ([DEEP-PolyU/LinearRAG](https://github.com/DEEP-PolyU/LinearRAG), ICLR'26). Per-benchmark
  folders with `questions.json` (`id`, `question`, `answer`, `source`, `question_type`, `evidence`,
  `evidence_relations`) and `chunks.json`. **No license is declared on the card, and there is no
  provenance or citation statement.** The viewer is broken (schema mismatch between the two file
  types). Treat as: usable as a convenience mirror under the upstream datasets' own licenses
  (CC BY-SA 4.0 / CC BY 4.0 / Apache-2.0), but you cannot rely on the repo itself for redistribution
  terms, and the absence of a stated derivation recipe means you cannot verify it matches HippoRAG's
  files. **Recommend: do not use as the source of truth.**
- **[`102202132zbz/rag_test`](https://huggingface.co/datasets/102202132zbz/rag_test)** — declares
  **apache-2.0**, and explicitly states the datasets "are **not** originally created by us",
  reformatted from `Zly0523/linear-rag` (MuSiQue/HotpotQA/2Wiki) and GraphRAG-Bench (Medical/Novel).
  It reports 1,000 questions each for the three multi-hop sets but only 1,354 / 1,311 / 658 chunks —
  **an order of magnitude fewer passages than the HippoRAG corpora**. That is a different, much
  easier retrieval task. Also note the apache-2.0 declaration cannot actually relicense
  HotpotQA (CC BY-SA 4.0, which is copyleft) — the declared license is not authoritative for the
  underlying content.

**Recommendation: build from upstream.** Take the HippoRAG `reproduce/dataset/*.json` files as the
canonical 1,000-question id lists + corpora, verify the dedup reconstruction from the upstream
HotpotQA/MuSiQue/2Wiki releases, and check content hashes into the repo rather than the data.

### 1.4 2025–2026 benchmarks the harness should accept

Everything below was verified on the linked page.

| Benchmark | Size | Corpus | Ground truth | License | Agentic? |
|---|---|---|---|---|---|
| **FRAMES** [2409.12941](https://arxiv.org/abs/2409.12941), NAACL'25, HF `google/frames-benchmark` | 824 (test) | **none shipped** | short answer + gold Wikipedia URLs | Apache-2.0 | optional |
| **MultiHop-RAG** [2401.15391](https://arxiv.org/abs/2401.15391), HF `yixuantt/MultiHopRAG` | 2,556 (HF shows 2,560) | 609 news articles | short answer + `evidence_list` chunks | ODC-BY | no |
| **BrowseComp-Plus** [2508.06600](https://arxiv.org/abs/2508.06600), ACL'26, HF `Tevatron/browsecomp-plus` | 830 | **100,195 docs** | short answer + 2 tiers of gold doc ids | MIT | **required** |
| **LongMemEval** [2410.10813](https://arxiv.org/abs/2410.10813), ICLR'25, HF `xiaowu0162/longmemeval` | 500 | chat history (`_S` ~115k tok, `_M` ~500 sessions) | answer + evidence session ids | MIT | no |
| **Loong** [2406.17419](https://arxiv.org/abs/2406.17419), EMNLP'24, ModelScope `iic/Loong` | 1,600 | ~11 docs/instance, 10–250K tok | golden answer + 0–100 judge rubric | Apache-2.0 (repo badge) | no |
| **GraphRAG-Bench (a)** [2506.02404](https://arxiv.org/abs/2506.02404), HF `jeremycp3/GraphRAG-Bench` | 1,018 | ~7M words, 20 CS textbooks | mixed + gold expert rationales | **academic-only, no redistribution** | no |
| **GraphRAG-Bench (b)** [2506.05690](https://arxiv.org/abs/2506.05690) "When to use Graphs in RAG", HF `GraphRAG-Bench/GraphRAG-Bench` | 4,072 (medical 2,060 + novel 2,012) | domain corpora | answer + `evidence` + `evidence_relations` | MIT | no |
| **WildGraphBench** [2602.02053](https://arxiv.org/abs/2602.02053), Findings ACL'26, HF `Bstwpy/WildGraphBench` | 1,197 (abstract says 1,100) | raw web pages cited by Wikipedia | short answer / multi-fact / statement rubric | Apache-2.0 | no |
| **InfoDeepSeek** [2505.15872](https://arxiv.org/abs/2505.15872) | 245 | **live web** | short answer, no gold docs | CC BY-NC 4.0 | **required** |

**FRAMES** tests end-to-end RAG factuality on questions needing 2–15 Wikipedia articles (~36% need
2, ~35% need 3), tagged by reasoning type (numerical, tabular, multiple constraints, temporal,
post-processing). The title is "Fact, Fetch, and Reason". Retrieval is *not* separately scored;
accuracy is LLM-judged by Gemini-Pro-1.5 (0.96 human agreement, κ=0.889). Reported: no-retrieval
0.408, BM25 n=2 0.452, oracle gold articles 0.729, multi-step retrieval with planning 0.66. Because
no corpus ships, FRAMES retrieval numbers are incomparable across papers unless the Wikipedia
snapshot is pinned — treat it as a reader benchmark, not a retrieval one.

**MultiHop-RAG** spreads evidence over 2–4 news documents (inference 816, comparison 856, temporal
583, **null 301**). It is single-shot retrieve-then-read, but it does score retrieval — MAP@K,
MRR@K, Hit@K — and the null class makes it one of the few multi-hop sets that tests abstention.

**BrowseComp-Plus** is the strongest fit for an agentic harness and the only benchmark surveyed that
simultaneously offers a frozen corpus, tiered gold labels, a published retrieval protocol and a
permissive license. Per query: 6.1 evidence docs, 2.9 gold docs, 76.3 hard negatives. All fields
except `query_id` are obfuscated behind a canary to resist training leakage. The agent calls a local
retriever tool returning top-5 docs of ≤512 tokens; **search-call count is a first-class reported
quantity**. Retrieval is scored in TREC run format with Recall@5/100/1000 and nDCG@10, computed
twice — once against `evidence_docs`, once against `gold_docs`.

**LongMemEval** tests long-term interactive memory: information extraction, multi-session reasoning,
temporal reasoning, knowledge updates, abstention. QA correctness via GPT-4o auto-eval, plus turn-
and session-level recall. Relevance to `triplum`: **it is the only benchmark here whose corpus grows
over time**, which is exactly what a persistent KG is for. Low priority now; shape the ingestion API
so it can be added. (`xiaowu0162/longmemeval` is marked deprecated in favour of
`longmemeval-cleaned`, whose license I did not verify.)

**Loong** is constructed so that *every* document is load-bearing — Spotlight Locating 250,
Comparison 300, Clustering 641, Chain of Reasoning 409, across finance/legal/academic, EN+ZH. GPT-4
Turbo scores 0–100 on accuracy / hallucination / completeness, reported as Avg Score and Perfect
Rate. Its own finding is that RAG does *badly* here because evidence is evenly distributed, which
makes it a useful negative control for a GraphRAG claim and a poor primary target.

**GraphRAG-Bench is two distinct datasets with the same name.** (a) 2506.02404 is domain reasoning
over CS textbooks with gold expert rationales, scored on accuracy plus R/AR reasoning scores — but
its license is academic-research-only with redistribution and modification prohibited, which is a
hard blocker. (b) 2506.05690 has four difficulty levels (L1 fact retrieval → L4 creative
generation), is scored on Accuracy / ROUGE-L / Coverage / Factual Score, and is MIT. Take (b): the
license works and `evidence_relations` gives a gold-triplet signal alongside 2Wiki's. The repo
asserts ICLR'26; the arXiv page carries no venue string.

**WildGraphBench** (the arXiv id in the brief is real and the title matches) harvests the *external
reference URLs* of high-citation-density Wikipedia pages with full raw text — boilerplate, nav, ads,
PDFs, scans — across 12 top-level topics, using citation-linked Wikipedia statements as ground
truth. Its baselines are Fast-GraphRAG, MS GraphRAG local/global, LightRAG hybrid, LinearRAG and
HippoRAG 2, all on gpt-4o-mini; its headline is that GraphRAG helps on multi-fact cross-document QA
and adds little on single-fact. That is the same comparison `triplum` is running, on a deliberately
noisy corpus — the best complement to the clean-Wikipedia three.

**InfoDeepSeek** is mandatorily agentic (multi-round plan+search over live DuckDuckGo/Google/Bing),
with each question combining ≥2 of six difficulty attributes. Its metrics are the interesting part:
ACC, IA@k (information accuracy of top-k evidence), EEU (effective evidence utilization), IC
(information compactness). But the non-commercial license and live-web corpus make it
non-reproducible — cite it for metric design, do not adopt it.

Also tracked, not adopted: **DeepResearch Bench** ([2506.11763](https://arxiv.org/abs/2506.11763),
100 PhD-level report tasks, RACE reference-based criteria + FACT citation metrics) and **ResearchQA**
([2509.00496](https://arxiv.org/abs/2509.00496), ~21k queries / ~160k rubric items from survey
articles across 75 fields, license unstated). Both score long-form output against rubrics — the same
machinery §4.4 needs. **Three name collisions to guard against: GraphRAG-Bench ×2 (above),
"DeepResearch Bench" vs FutureSearch's "Deep Research Bench"
([2506.06287](https://arxiv.org/abs/2506.06287)), and ResearchQA 2509.00496 vs 2607.11074. Cite
arXiv ids, not names.**

Finally, [arXiv:2506.06331](https://arxiv.org/abs/2506.06331) ships no dataset but argues reported
GraphRAG gains are "much more moderate than reported previously" once unrelated questions and
evaluation biases are controlled. Cite as a threat-to-validity reference.

---

## 2. Metrics

### 2.1 EM and token-F1

The reference implementation is
[`hotpot_evaluate_v1.py`](https://github.com/hotpotqa/hotpot/blob/master/hotpot_evaluate_v1.py).
Normalisation is the SQuAD rule, composed as
`white_space_fix(remove_articles(remove_punc(lower(s))))`: lowercase → strip `string.punctuation` →
`re.sub(r'\b(a|an|the)\b', ' ', text)` → `' '.join(text.split())`. EM is string equality on the
normalised forms. F1 is token-multiset overlap: `common = Counter(pred) & Counter(gold)`,
`precision = num_same/len(pred)`, `recall = num_same/len(gold)`, harmonic mean; returns 0 when
`num_same == 0`. HotpotQA adds a rule SQuAD does not have: if either side normalises to
`yes`/`no`/`noanswer` and the two differ, F1 is forced to 0 — no partial credit on comparison
questions.

**HippoRAG uses a near-identical but not identical implementation.** In
`src/hipporag/utils/eval_utils.py` the `normalize_answer` is character-for-character the same four
transformations in the same order. But `src/hipporag/evaluation/qa_eval.py` differs in two ways:
it takes `np.max` over a *list* of gold answers (MRQA-style alias handling, which matters for
MuSiQue's 276 alias-carrying questions), and it has **no yes/no special case**. Pick one and state
it; mixing them silently shifts HotpotQA F1.

Known problem: **EM and token-F1 penalise verbose LLM answers.** With mean gold answers of
2.4–2.8 tokens **[measured]**, a correct-but-conversational response ("The director was Christopher
Nolan.") scores F1 ≈ 0.5 against gold "Christopher Nolan" and EM 0. This is why the GraphRAG
literature drifted to inclusion-based and judged metrics. It is also why the reader prompt is part
of the protocol, not an implementation detail — see §4.1.

### 2.2 Retrieval recall@k

HippoRAG's definition, from `src/hipporag/evaluation/retrieval_eval.py`:

```python
top_k_docs = example_retrieved_docs[:k]
relevant_retrieved = set(top_k_docs) & set(example_gold_docs)
example_eval_result[f"Recall@{k}"] = len(relevant_retrieved) / len(set(example_gold_docs))
```

then averaged over examples (macro over queries, micro within a query), rounded to 4 dp. Defaults
are `k_list = (1, 5, 10, 20)`; the papers report **R@2 and R@5**. Two things to copy exactly:
the denominator is `len(set(gold))`, not a fixed 2; and documents are matched **by string**, not by
id — so passage text normalisation is load-bearing for cross-system comparability. R@2 is meaningful
because gold-passage counts are 2.00 / 2.47 / 2.65 **[measured]**; R@2 on MuSiQue is bounded well
below 1 for 3- and 4-hop questions.

### 2.3 Answer-inclusion and LLM-judged correctness

Two distinct things that are often conflated:

- **Contain-Acc / "answer inclusion"**: gold answer string appears anywhere in the generated output.
  Used widely in GraphRAG work precisely because "the uncontrollable nature of LLM outputs often
  makes exact matches difficult" — see the unified graph-RAG analysis
  ([arXiv:2503.04338](https://arxiv.org/abs/2503.04338)) and HyperSU
  ([arXiv:2606.28351](https://arxiv.org/abs/2606.28351)), which reports Contain-Acc. alongside
  GPT-Acc., answer F1 and Recall@5. It is cheap and deterministic but trivially gamed by long
  answers that enumerate candidates.
- **LLM-judged correctness ("GPT-Acc")**: a judge decides semantic equivalence. FRAMES uses
  Gemini-Pro-1.5 with reported 0.96 human agreement / κ 0.889; LongMemEval uses GPT-4o;
  GraphRAG-Bench uses binary accuracy for closed-form and GPT-4o-mini for fill-in-blank and
  open-ended. The typical prompt marks CORRECT when the answer conveys the same core information as
  any gold answer, is more specific, is a valid alternative form, or contains a gold answer plus
  extra information — i.e. it *operationalises* inclusion semantics with a semantic escape hatch.

**Recommend reporting all four** (EM, F1, Contain-Acc, Judge-Acc) on every run. They cost almost
nothing extra once answers exist, and each paper you compare against picked a different one.

### 2.4 The pairwise judge protocol (Edge et al. + BenchmarkQED AutoE)

Edge et al. ([arXiv:2404.16130](https://arxiv.org/abs/2404.16130)) established the head-to-head
protocol: give the judge the question and two answers, ask which is preferred on one criterion at a
time. Criteria as written in the paper: **comprehensiveness** ("How much detail does the answer
provide to cover all aspects and details of the question?"), **diversity** ("How varied and rich is
the answer in providing different perspectives and insights on the question?"), **empowerment**
("How well does the answer help the reader understand and make informed judgments about the
topic?"), and **directness** as a control criterion ("How specifically and clearly does the answer
address the question?"). Ties are allowed when answers "are fundamentally similar". Reported results
are "across two datasets, four metrics, and 125 questions per comparison (each repeated five times
and averaged)". The paper does not state the judge model or an explicit position-swap procedure.

**BenchmarkQED** ([microsoft/benchmark-qed](https://github.com/microsoft/benchmark-qed)) is the
productionised version and fills in exactly the gaps. From the source:

- **Criteria** (`benchmark_qed/config/model/score.py`, `pairwise_scores_criteria()`): the default
  set is **comprehensiveness, diversity, empowerment, relevance** — *directness has been replaced by
  relevance*. Each carries a multi-sentence description with a worked example. Reference-based
  scoring uses a separate pair, **correctness** and **completeness**.
- **Tie handling is explicit and numeric.** The judge returns `winner ∈ {1, 2, 0}` and
  `benchmark_qed/autoe/pairwise/scores.py` maps `SCORE_MAPPING = {0: 0.5, 1: 1.0, 2: 0.0}` — a tie
  is half a win, not a discard.
- **Position swap is enforced by construction.** `trials` defaults to **4** and
  `BaseAutoEConfig.check_trials_even` *raises* if it is odd: "The number of trials must be even to
  allow for counterbalancing of conditions." In `get_pairwise_score`, answer order is reversed when
  `trial % 2 == 1`.
- **Judge model default is `gpt-4.1`** (`benchmark_qed/config/llm_config.py`, `LLMConfig.model`),
  provider `openai.chat`, `concurrent_requests: 20`. The docs stress that "selecting an appropriate
  LLM judge is crucial" and recommend validating a judge by A/A testing.
- **Significance testing is built in**: `scores.py` imports `shapiro`, `ttest_rel`, `wilcoxon` and
  `statsmodels.stats.multitest.multipletests` — i.e. normality check, paired test, multiple-
  comparison correction across criteria. Copy this; pairwise win rates without a paired test over
  4 × N judgments are not evidence.
- The system prompt explicitly instructs the judge to ignore position, length and formatting, and a
  random `score_id` is injected per call to defeat response caching.

### 2.5 Cost, latency and token accounting

No published protocol standardises this, which is precisely why it is worth pinning. HippoRAG 1
frames its efficiency claim as "10–20× cheaper and 6–13× faster" than IRCoT, i.e. relative to a
named baseline rather than in absolute units. BrowseComp-Plus makes **search-call count** a
first-class reported quantity (GPT-5 + Qwen3-Embedding-8B reaches 70.1% "with fewer search calls").
GraphRAG-Bench (2506.02404) reports graph-construction cost and time and retrieval time separately.

Recommend recording, per run and split by phase (index / retrieve / generate / judge):
prompt tokens, completion tokens, cached-prompt tokens, wall-clock, number of LLM calls, number of
retriever calls, number of embedding calls. Indexing cost must be amortised and reported separately
— a GraphRAG pipeline that spends 500× the indexing tokens of dense RAG to win 2 F1 points is a
different result from one that does not, and none of the QA tables capture that.

### 2.6 Known problems to state in every results table

1. **EM/F1 penalise verbose answers** (§2.1). Any comparison across papers using different reader
   prompts is partly measuring prompt terseness.
2. **Judge bias.** Position bias in capable judges is systematic, not noise, and its *direction
   flips across datasets* ([A Systematic Study of Position Bias in LLM-as-a-Judge](https://aclanthology.org/2025.ijcnlp-long.18.pdf)).
   Verbosity bias is entangled with it — output length is a statistically significant predictor of
   preference fairness. Self-preference bias is large and heterogeneous in sign (reported range
   −38% to +90% on ArenaHard, [arXiv:2410.21819](https://arxiv.org/abs/2410.21819)). Specific to
   this literature: the RAG-vs-GraphRAG study found that "reversing the order of presented summaries
   leads to substantially different, and in some cases opposite, judgments"
   ([arXiv:2502.11371](https://arxiv.org/abs/2502.11371) §5.3). Mitigations: counterbalance (AutoE
   does), use a judge from a different family than any system under test, report κ not raw
   agreement. Ensembling reduces variance but not *shared* bias.
3. **Contamination.** All three core datasets are Wikipedia-derived and heavily mirrored. CofCA
   ([arXiv:2402.11924](https://arxiv.org/abs/2402.11924), CC BY 4.0) knowledge-edits the passages to
   break memorisation and measures the drop directly: GPT-4 on 2-hop falls **EM 69.9 → 53.1, F1 82.3
   → 62.8**; 3-hop 59.7 → 44.5 EM; 4-hop 57.3 → 42.3 EM. Similar declines for GPT-3.5 and
   Gemini-Pro. Read that as: roughly a third of headline HotpotQA-style accuracy on a frontier model
   is not multi-hop reasoning over the retrieved context. LastingBench
   ([EMNLP 2025 Findings](https://aclanthology.org/2025.findings-emnlp.993/)) reports substantial
   leakage in HotpotQA specifically.
   **Implication for `triplum`: a no-retrieval closed-book baseline is mandatory**, not optional. It
   is the only cheap measurement of how much of each pipeline's score the retrieval is responsible
   for.

---

## 3. Reference numbers

Only numbers read off a paper page are listed. The single most important finding of this section:

> **There are two incompatible generations of "the 1000-question protocol", and most 2025–2026
> GraphRAG papers have abandoned EM/F1 entirely.**
>
> - *Gen 1* (HippoRAG 1, 2024): reader **GPT-3.5-turbo-1106**, retriever **ColBERTv2**/Contriever,
>   HotpotQA corpus 9,221. Metrics EM/F1 + R@2/R@5.
> - *Gen 2* (HippoRAG 2, 2025): reader **Llama-3.3-70B-Instruct** (GPT-4o-mini secondary), retriever
>   **NV-Embed-v2 (7B)**, HotpotQA corpus 9,811. Main-table QA metric is **token-F1 computed with
>   MuSiQue's script**; EM is appendix-only (Table 8), R@2 is appendix-only (Table 9).
> - *Gen 2, different metric*: LinearRAG and EA-GraphRAG use the same 1,000 questions and corpora but
>   report **Contain-Acc / GPT-Acc** with **all-mpnet-base-v2** + **GPT-4o-mini**. These do not
>   convert to EM/F1 and must never share a column with them.

### 3.1 Generation 2 — Llama-3.3-70B-Instruct reader, NV-Embed-v2, top-5

All rows from HippoRAG 2 ([arXiv:2502.14802v2](https://arxiv.org/html/2502.14802v2), Tables 2/3 +
Appendix 8/9) unless noted. EM / F1 / R@5.

| System | HotpotQA | MuSiQue | 2Wiki |
|---|---|---|---|
| No retrieval (closed book) | 37.0 / 47.3 / — | 17.6 / 26.1 / — | 36.5 / 42.8 / — |
| BM25 | 52.0 / 63.4 / 74.8 | 20.3 / 28.8 / 43.5 | 47.9 / 51.2 / 65.3 |
| Contriever | 51.3 / 62.3 / 75.3 | 24.0 / 31.3 / 46.6 | 38.1 / 41.9 / 57.5 |
| GTE-Qwen2-7B-Instruct | 58.6 / 71.0 / 89.1 | 30.6 / 40.9 / 63.6 | 55.1 / 60.0 / 74.8 |
| GritLM-7B | 60.7 / 73.3 / 92.4 | 33.6 / 44.8 / 65.9 | 55.8 / 60.6 / 76.0 |
| **NV-Embed-v2 — naive dense baseline** | **62.8 / 75.3 / 94.5** | **34.7 / 45.7 / 69.7** | **57.5 / 61.5 / 76.5** |
| RAPTOR (reproduced) | 56.8 / 69.5 / 86.9 | 20.7 / 28.9 / 57.8 | 47.3 / 52.1 / 66.2 |
| MS GraphRAG (reproduced) | 55.2 / 68.6 / n.r. | 27.3 / 38.5 / n.r. | 51.4 / 58.6 / n.r. |
| LightRAG (reproduced) | 2.0 / 2.4 / n.r. | 0.5 / 1.6 / n.r. | 9.4 / 11.6 / n.r. |
| HippoRAG 1 (reproduced) | 52.6 / 63.5 / 77.3 | 26.2 / 35.1 / 53.2 | 65.0 / **71.8** / 90.4 |
| **HippoRAG 2** | **62.7 / 75.5 / 96.3** | **37.2 / 48.6 / 74.7** | **65.0 / 71.0 / 90.4** |
| PropRAG (L_max=3) [2504.18070v2] | — / 76.1 / 97.4 | — / 53.9 / 78.3 | — / 75.3 / 94.1 |
| BridgeRAG cond. C [2604.03384v1] | — / — / 98.75 | — / — / 81.46 | — / — / 95.27 |

Three things to take from this table.

1. **The naive dense baseline is extremely strong.** NV-Embed-v2 alone beats *every* structure-
   augmented system except HippoRAG 2 on HotpotQA, and beats HippoRAG 1 on HotpotQA and MuSiQue. On
   HotpotQA, HippoRAG 2's F1 advantage over plain dense retrieval is **+0.2** (75.5 vs 75.3). The
   real gap is on MuSiQue (+2.9 F1, +5.0 R@5), which is the genuinely multi-hop dataset.
2. **Retriever quality dominates architecture.** Swapping BM25 → NV-Embed-v2 moves HotpotQA F1 by
   ~12 points; every graph method moves it by ≤1. Any `triplum` comparison that does not hold the
   embedder fixed across pipelines is measuring the embedder.
3. **PropRAG's baseline rows are copied verbatim from HippoRAG 2** — not an independent replication.
   Do not count it as corroboration.

**The LightRAG reproduction is contested and this matters.** HippoRAG 2 reports LightRAG at F1
2.4 / 1.6 / 11.6 (HotpotQA/MuSiQue/2Wiki) — near-total failure. GFM-RAG
([arXiv:2502.01113v2](https://arxiv.org/html/2502.01113v2)) reports the same system at F1
48.3 / 27.5 / 49.5. LinearRAG puts it mid-pack (Contain-Acc 60.3 / 27.4 / 55.2). An order-of-
magnitude spread on the same system and same datasets is an answer-format/harness artefact, not a
measurement. **Do not cite any single LightRAG number as ground truth**, and treat this as the
cautionary case for why §4.1 demands the prompt be stored.

### 3.2 Generation 1 — GPT-3.5-turbo-1106 / GPT-4o-mini readers

HippoRAG 1 ([arXiv:2405.14831v3](https://arxiv.org/html/2405.14831v3)) and GFM-RAG
(GPT-4o-mini reader, all-mpnet-base-v2, marked †). EM / F1 / R@5.

| System | HotpotQA | MuSiQue | 2Wiki |
|---|---|---|---|
| No retrieval | 30.4 / 42.8 / — | 12.5 / 24.1 / — | 31.0 / 39.6 / — |
| BM25 | n.r. / n.r. / 72.2 | n.r. / n.r. / 41.2 | n.r. / n.r. / 61.9 |
| **ColBERTv2 — naive dense baseline** | **43.4 / 57.7 / 79.3** | **15.5 / 26.4 / 49.2** | **33.4 / 43.3 / 68.2** |
| RAPTOR (ColBERTv2) | n.r. / n.r. / 75.6 | n.r. / n.r. / 46.5 | n.r. / n.r. / 64.7 |
| HippoRAG 1 (ColBERTv2) | 41.8 / 55.0 / 77.7 | 19.2 / 29.8 / 51.9 | 46.6 / 59.5 / 89.1 |
| IRCoT + ColBERTv2 | 45.5 / 58.4 / 82.0 | 19.1 / 30.5 / 53.7 | 35.4 / 45.1 / 74.4 |
| IRCoT + HippoRAG 1 | 45.7 / 59.2 / 83.0 | 21.9 / 33.3 / 57.6 | 47.7 / 62.7 / 93.9 |
| MS GraphRAG † | 35.3 / 54.6 / 76.6 | 13.4 / 29.5 / 49.3 | 28.3 / 46.9 / 77.3 |
| LightRAG † | 36.8 / 48.3 / 54.7 | 18.1 / 27.5 / 34.7 | 45.1 / 49.5 / 59.1 |
| GFM-RAG † | 51.6 / 66.9 / 87.1 | 30.2 / 40.4 / 58.2 | 69.8 / 77.7 / 95.6 |

### 3.3 Same protocol, Contain-Acc / GPT-Acc metric

LinearRAG ([arXiv:2510.10114v4](https://arxiv.org/html/2510.10114v4), ICLR 2026,
[DEEP-PolyU/LinearRAG](https://github.com/DEEP-PolyU/LinearRAG)) — explicitly "the same evaluation
method as HippoRAG, using the same corpus… choosing 1,000 questions from each validation set", all
methods sharing **all-mpnet-base-v2** + **GPT-4o-mini**, top-k=5. Contain-Acc / GPT-Acc:

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

EA-GraphRAG, "Use Graph When It Needs" ([arXiv:2602.03578v1](https://arxiv.org/html/2602.03578v1) —
**the id verifies**; v1 dated 2026-02-03) uses the same 1,000-query protocol and HippoRAG 2's exact
corpora (2Wiki 6,119, HotpotQA 9,811) but **skips MuSiQue** and reports Acc / GPT-Acc + R@3/R@5.
Reader and graph-construction LLM both GPT-4o-mini, top-k=5; **the embedder is not stated**.
HotpotQA: ColBERTv2 63.4/75.9 (R@5 77.8), HippoRAG 2 65.5/79.5 (R@5 89.6), EA-GraphRAG 65.9/80.2
(R@5 87.2). 2Wiki: HippoRAG 1 68.6/73.8 (R@5 86.0), HippoRAG 2 67.7/72.5 (R@5 85.2), EA-GraphRAG
76.3/81.5 (R@5 88.1).

### 3.4 Papers that do *not* use this protocol (do not merge these rows)

- **LightRAG** ([arXiv:2410.05779](https://arxiv.org/abs/2410.05779)) **reports none of the three
  datasets.** Zero occurrences of "hotpot", "musique" or "2wiki" in the paper. It evaluates on four
  UltraDomain corpora with LLM-judged pairwise win rates. All numbers above are third-party
  reproductions.
- **MS GraphRAG** ([arXiv:2404.16130](https://arxiv.org/abs/2404.16130)) **reports none of the
  three.** HotpotQA appears only in related work and as a sample corpus for an entity-extraction
  chunk-size study in Appendix C. HippoRAG 2 additionally notes that GraphRAG and LightRAG "do not
  directly produce passage retrieval results", which is why their recall cells are empty.
- **RAPTOR** ([arXiv:2401.18059](https://arxiv.org/abs/2401.18059)) **reports none of the three** —
  its datasets are NarrativeQA, QASPER, QuALITY.
- **RAG vs. GraphRAG** ([arXiv:2502.11371](https://arxiv.org/abs/2502.11371)): HotpotQA only, 1,000
  randomly selected **hard bridging** dev questions, own 256-token-chunk corpus,
  text-embedding-ada-002, top-10, readers Llama-3.1-8B/70B, token P/R/F1 only. HotpotQA F1 (8B/70B):
  RAG 60.04/63.88; KG-GraphRAG triplets-only 25.02/30.73; Community-GraphRAG local 61.66/64.60,
  global 45.16/46.99; HippoRAG 2 63.01/64.93.
- **"Do We Still Need GraphRAG?"** ([arXiv:2604.09666](https://arxiv.org/abs/2604.09666) —
  **the id verifies**; benchmark named RAGSearch, subtitle "Benchmarking RAG and GraphRAG for Agentic
  Search Systems"). Uses **full dev splits** via FlashRAG (HotpotQA 7,405 / MuSiQue 2,417 / 2Wiki
  12,576) over the 2018 Wikipedia dump as a single shared corpus; Qwen2.5-7B/32B-Instruct agents;
  Contain-EM and F1. Contain-EM with the Search-o1 agent (HotpotQA / 2Wiki / MuSiQue): Dense
  33.76 / 29.64 / 12.62; MS GraphRAG 32.73 / 54.25 / 26.48; RAPTOR 29.51 / 29.87 / 29.50; LinearRAG
  35.76 / 58.94 / 29.46; **HippoRAG 2 42.75 / 65.56 / 32.44**. With the GraphSearch agent: Dense
  38.22 / 47.43 / 13.33; HippoRAG 2 58.64 / 79.88 / 55.10. This is the closest published analogue to
  what `triplum` is building — an *agentic* harness over these datasets — and its headline is that
  the agent loop moves scores far more than the index structure does.

### 3.5 What this section implies

MuSiQue is the discriminating dataset and also the worst-covered one: EA-GraphRAG and RAG-vs-GraphRAG
skip it, 2604.09666 uses the full dev set. Comparable MuSiQue sources reduce to HippoRAG 1/2,
GFM-RAG, PropRAG, BridgeRAG and LinearRAG. If only one dataset can be run at full scale, run MuSiQue.

---

## 4. Harness design implications

### 4.1 What a run record must store

A run record that cannot be compared to a published table is wasted compute. One JSON document per
(pipeline × dataset × config):

- **Provenance** — `run_id`, UTC timestamp, `triplum` git SHA + dirty flag, dependency lockfile hash.
- **Data** — `dataset`/`variant` (`hotpotqa/distractor`), `protocol` (`hipporag-1000-gen2`), SHA-256
  of both the question and corpus file, `n_questions`, and the explicit question-id list (or its
  hash) so a 20-question smoke run is *provably* a subset of the 1000-question run.
- **Retrieval** — retriever type; embedding model **id and revision** (`nvidia/NV-Embed-v2` at a
  pinned commit, not "NV-Embed-v2"); BM25 implementation + k1/b/tokenizer; cross-encoder id; `k` at
  *every* stage (candidate, rerank, final-to-reader); chunk size/overlap and the tokenizer used to
  count. GraphRAG adds: extraction schema, extraction LLM, graph serialisation format, PPR damping
  factor, restart-node selection.
- **Generation** — reader LLM id with dated snapshot, temperature, top_p, max_tokens, seed, **the
  full prompt template text** (not a pointer to a mutable file), few-shot exemplar count.
- **Judging** — judge model id + snapshot, judge prompt text, trials, counterbalancing, tie mapping.
- **Results** — per-question rows (ranked retrieved doc ids, generated answer, gold answers, EM, F1,
  Contain-Acc, Judge-Acc), aggregates with bootstrap CIs, and the §2.5 cost block.

The non-negotiable subset for cross-paper comparability is **retriever, k, reader LLM, embedding
model, prompt, seed, judge model**. A large fraction of the GraphRAG literature omits the prompt —
and §3.1's LightRAG spread (F1 2.4 vs 48.3) is what that omission costs.

### 4.2 Caching and determinism

LLM calls are the only expensive and the only nondeterministic part. Treat them as a pure function
and cache them:

- **Cache key** = SHA-256 of `(model_id, full_message_list, temperature, top_p, seed, max_tokens,
  response_format, tool_schema)`. Anything that changes the output must be in the key; nothing that
  does not should be. Content-addressed store on disk, one file per key, alongside the token counts
  and latency so a cached replay still produces a cost record (flagged `cached: true`).
- **`temperature=0` is not determinism.** Batching and kernel nondeterminism mean repeated calls
  differ even at temperature 0, and providers rotate model weights behind undated aliases. So:
  always pin dated snapshots, set `seed` where the provider supports it, and rely on the cache — not
  the provider — for replay. A re-run of a completed experiment should be a cache walk with zero API
  calls; assert that.
- **Extraction caching is separate and much more valuable.** KG construction over 11,656 passages is
  the dominant cost. Cache per-chunk extraction keyed on `(chunk_hash, extraction_prompt_hash,
  model_id, schema_hash)` so that changing the retriever or the reader does not re-index.
- **Cache the judge too**, but note BenchmarkQED deliberately injects a random `score_id` per call to
  *defeat* caching. If you cache judge calls, drop `score_id` from the key and accept that the
  4 trials then differ only by position, not by sampling. Cleaner: keep `score_id` out of the prompt
  entirely, set `trial_index` in the key, and sample at `temperature > 0` for the replicates.
- Retrieval is deterministic given a frozen index; still hash the index and store the hash.

### 4.3 Smoke test vs full run

Same code path, one parameter. `--limit N` takes the **first N ids of the pinned id list** after a
seeded shuffle that is fixed per dataset — so the 20-question smoke set is stable across runs and is
a genuine subset of the 1000. Do not re-sample per run.

Practicalities:

- At N=20 the corpus should still be the **full** 1000-question corpus, otherwise the smoke test
  exercises a retrieval task that does not exist. Index once, reuse across N. If full-corpus
  indexing is too slow to iterate on, add a separate explicitly-labelled `--tiny-corpus` mode that
  builds the corpus from the N questions only, and refuse to write a comparable run record from it.
- Stratify the 20 by question type so the smoke set covers bridge/comparison (HotpotQA) and 2/3/4-hop
  (MuSiQue). An unstratified 20 from MuSiQue is ~10 two-hop questions and tells you nothing about
  multi-hop behaviour.
- N=20 is for "does the pipeline run end to end and produce non-garbage". It is **not** for
  comparing pipelines — the standard error on EM at N=20 is ≈0.11, wider than nearly every gap in
  §3. Enforce this: refuse to emit a comparison table below some N, or emit it with CIs so wide the
  point is obvious.
- Budget guard: fail fast if projected token spend for the full run exceeds a configured cap,
  estimated from the smoke run's measured per-question cost.

### 4.4 Domain evaluation with no gold answers (the Liao "legal corpus" case)

The gold-answer-free case is the same harness with two swaps:

1. **Question source.** Instead of a fixed question file, AutoQ synthesises the question set from
   the corpus. Its four classes are local (answerable from a small number of text regions), global
   (require reasoning over large portions of the corpus), data-linked multi-hop local (combining
   related local questions that share named entities), and the AutoD-controlled sampling that keeps
   corpora comparable (topic-cluster breadth × samples-per-cluster depth). The synthesised question
   set is an artefact: hash it, version it, and store it exactly like a downloaded question file, so
   the run record schema in §4.1 is unchanged.
2. **Scoring.** Replace the EM/F1/recall block with AutoE pairwise (§2.4) between named conditions.
   This requires a designated `base` condition — naive dense RAG — and reports every other pipeline
   as a win rate against it per criterion, with the paired significance test.

Two consequences for the design. First, **`base` must be a first-class concept in the run record**,
because a pairwise result is a property of a *pair*, not of a run; store `base_run_id` on the
comparison record. Second, retrieval metrics are simply absent here — there are no gold passages —
so the harness must tolerate a metric set that varies by dataset rather than assuming a fixed
column list. Design the results schema as `{metric_name: value}` with a declared metric set per
dataset, not as a fixed table.

The same machinery covers §1.4's rubric benchmarks (ResearchQA, DeepResearch Bench, WildGraphBench's
summarization slice): AutoE's assertion-based scoring — binary pass/fail per assertion — is the
rubric path, and is already implemented in `benchmark_qed/autoe/assertion/`.

---

## Decisions we recommend

1. **Primary target is the HippoRAG 1000-question protocol on all three datasets**, built from
   upstream releases and verified against the HippoRAG `reproduce/dataset/` files by content hash.
   Do not use `Zly0523/linear-rag` (no license, no provenance) or `102202132zbz/rag_test` (corpora
   an order of magnitude smaller than HippoRAG's; declared apache-2.0 cannot relicense CC BY-SA
   HotpotQA content) as the source of truth.
2. **Report the file's numbers and hashes, not the paper's.** The released HotpotQA corpus is 9,811
   passages against a paper that says 9,221. State which artefact you used.
3. **Report EM, token-F1, Contain-Acc, Judge-Acc, R@2 and R@5 on every run.** Use HotpotQA's
   `normalize_answer` (identical in both implementations) but adopt **HippoRAG's** max-over-aliases
   aggregation and **no** yes/no zeroing, and say so — this makes numbers comparable to the GraphRAG
   literature rather than to the HotpotQA leaderboard.
4. **Mandatory baselines, every time:** closed-book no-retrieval (contamination floor), BM25-only,
   and oracle-gold-passages (reader ceiling). Without the first and third, a pipeline delta is
   uninterpretable.
5. **Adopt BenchmarkQED AutoE verbatim** for the no-gold-answer path: four criteria as implemented,
   tie = 0.5, even `trials` with position swap, paired test with multiple-comparison correction.
   Do not hand-roll a pairwise judge.
6. **Use a judge from a different model family than any reader under test**, and record the judge's
   A/A win rate on the run as a bias diagnostic.
7. **Second tier of datasets, in priority order: BrowseComp-Plus** (the only fixed-corpus, tiered-
   gold, MIT-licensed, genuinely agentic benchmark), **WildGraphBench** (noisy real-world corpora,
   Apache-2.0, already benchmarks the exact systems `triplum` reimplements), **GraphRAG-Bench
   2506.05690** (MIT, ships `evidence_relations`). Shape the dataset adapter so a benchmark can
   declare its own metric set, its own gold-label tier(s), and whether it requires an agentic loop.
8. **Exclude for licensing:** GraphRAG-Bench 2506.02404 (academic-only, no redistribution) and
   InfoDeepSeek (CC BY-NC, and live-web non-reproducible).
9. **Treat indexing cost as a reported metric**, not overhead. It is the main axis on which
   GraphRAG loses and no QA table shows it.
10. **Target Generation 2 of the protocol and label it as such** in every run record: reader
    Llama-3.3-70B-Instruct (or GPT-4o-mini for the cheap tier), retriever NV-Embed-v2, top-5,
    HotpotQA corpus 9,811. That is the configuration with the densest set of published comparison
    rows (§3.1), including a strong naive-dense baseline with EM, F1, R@2 and R@5 all in one place.
11. **Hold the embedder fixed across all four pipelines.** §3.1 shows the embedder swing on HotpotQA
    F1 (~12 points BM25 → NV-Embed-v2) is an order of magnitude larger than any architecture effect
    (≤1 point). A pipeline comparison with a free embedder is not a pipeline comparison.
12. **If only one dataset runs at full scale, make it MuSiQue** — it is where the graph methods
    actually separate from dense retrieval (HippoRAG 2 +2.9 F1 / +5.0 R@5 over NV-Embed-v2, versus
    +0.2 F1 on HotpotQA).

## Open questions

- **The Liao et al. 2026 paper could not be located.** No paper titled "Best Practices in Graph
  Retrieval-Augmented Generation: A Systematic Evaluation" appears on arXiv, in ACL Anthology, or in
  general search as of 2026-09-16, under Liao or Fraunhofer FIT. The likely explanation: **SEMANTiCS
  2026 runs 15–17 September 2026 in Ghent** — i.e. it is taking place this week, so proceedings are
  not yet indexed. Everything in the brief about that pipeline (hierarchical 512-token chunks,
  schema-based triplet extraction, hypothetical-question + entity retriever, cross-encoder rerank,
  GraphML in the prompt) is therefore **specified only by the brief**, not by a source I could
  verify. Get the PDF before implementing; several of those choices (hypothetical-question indexing
  in particular) have materially different published variants.
  *Editor's note (2026-09-16):* the pipeline description does have a primary source, the official
  SEMANTiCS 2026 programme abstract (see [`papers.md`](papers.md) and
  [`landscape.md`](landscape.md)); the abstract names the winning choices but not their exact
  variants, so the point stands: get the PDF, or ask the authors, before implementing.
- **The sampling rule behind the 1,000-question sets is undocumented.** HotpotQA's are all
  `level == "hard"` **[measured]**, so it is not a uniform sample of dev. Pin the id lists; do not
  attempt to regenerate them.
- **Why the HotpotQA corpus grew from 9,221 to 9,811** between HippoRAG 1 and 2 is not explained in
  either paper. Papers citing "the HippoRAG corpus" may be on either.
- **The LightRAG spread (§3.1) is unresolved.** F1 2.4 vs 48.3 on HotpotQA across two reproductions.
  Nobody has published a diagnosis. If `triplum` reimplements LightRAG this is worth settling — it is
  a small, self-contained, citable result.
- **GFM-RAG's dataset-statistics table lists MuSiQue at 6,119 and 2Wiki at 11,656** — the reverse of
  HippoRAG's published corpora. Its other numbers track the protocol, so this reads as a typo, but
  footnote it if you cite their corpus sizes.
- **EA-GraphRAG does not state its embedder** (only "encoder M"), which makes its rows
  non-reproducible as published.
- **Which judge models the 2026 papers actually use is only partly documented.** FRAMES
  (Gemini-Pro-1.5), LongMemEval (GPT-4o), GraphRAG-Bench (GPT-4o-mini) and BenchmarkQED's default
  (`gpt-4.1`) are verified; Edge et al. never states its judge. There is no 2026 consensus judge.
- **Size discrepancies to resolve before publishing:** MultiHop-RAG 2,556 (paper) vs 2,560 (HF);
  WildGraphBench 1,100 (abstract) vs 1,197 (repo README).
- **BenchmarkQED has no accompanying arXiv paper** that I could find — only the MSR blog and the
  repo. Cite the source code.
- **Does 2Wiki's `evidences` field (gold KG triples) support a direct triplet-extraction metric?**
  It should — precision/recall of extracted triples against gold — but no paper I saw does this. If
  it works it is a differentiated contribution rather than a reproduction.

## Sources

**Datasets**
- HotpotQA: [arXiv:1809.09600](https://arxiv.org/abs/1809.09600) · [hotpotqa/hotpot](https://github.com/hotpotqa/hotpot) · [HF `hotpotqa/hotpot_qa`](https://huggingface.co/datasets/hotpotqa/hotpot_qa)
- MuSiQue: [arXiv:2108.00573](https://arxiv.org/abs/2108.00573) · [TACL 2022](https://aclanthology.org/2022.tacl-1.31/) · [StonyBrookNLP/musique](https://github.com/StonyBrookNLP/musique) · [HF `dgslibisey/MuSiQue`](https://huggingface.co/datasets/dgslibisey/MuSiQue) · [HF `bdsaglam/musique`](https://huggingface.co/datasets/bdsaglam/musique)
- 2WikiMultiHopQA: [Alab-NII/2wikimultihop](https://github.com/Alab-NII/2wikimultihop) · [HF `framolfese/2WikiMultihopQA`](https://huggingface.co/datasets/framolfese/2WikiMultihopQA)
- Prepackaged: [HF `Zly0523/linear-rag`](https://huggingface.co/datasets/Zly0523/linear-rag) · [HF `102202132zbz/rag_test`](https://huggingface.co/datasets/102202132zbz/rag_test)

**Protocol and systems**
- HippoRAG: [arXiv:2405.14831](https://arxiv.org/abs/2405.14831) · [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) (`reproduce/dataset/`, `src/hipporag/evaluation/`, `src/hipporag/utils/eval_utils.py`)
- HippoRAG 2: [arXiv:2502.14802](https://arxiv.org/abs/2502.14802)
- LinearRAG (ICLR 2026): [arXiv:2510.10114](https://arxiv.org/abs/2510.10114) · [DEEP-PolyU/LinearRAG](https://github.com/DEEP-PolyU/LinearRAG)
- MS GraphRAG: [arXiv:2404.16130](https://arxiv.org/abs/2404.16130)
- RAPTOR: [arXiv:2401.18059](https://arxiv.org/abs/2401.18059)
- LightRAG: [arXiv:2410.05779](https://arxiv.org/abs/2410.05779)
- GFM-RAG: [arXiv:2502.01113](https://arxiv.org/abs/2502.01113) · PropRAG: [arXiv:2504.18070](https://arxiv.org/abs/2504.18070) · BridgeRAG: [arXiv:2604.03384](https://arxiv.org/abs/2604.03384)
- RAG vs. GraphRAG: [arXiv:2502.11371](https://arxiv.org/abs/2502.11371)
- Do We Still Need GraphRAG? / RAGSearch: [arXiv:2604.09666](https://arxiv.org/abs/2604.09666)
- Use Graph When It Needs / EA-GraphRAG: [arXiv:2602.03578](https://arxiv.org/abs/2602.03578)
- Unified graph-RAG analysis: [arXiv:2503.04338](https://arxiv.org/abs/2503.04338)
- Unbiased GraphRAG evaluation critique: [arXiv:2506.06331](https://arxiv.org/abs/2506.06331)

**2025–2026 benchmarks**
- FRAMES: [arXiv:2409.12941](https://arxiv.org/abs/2409.12941) · [HF `google/frames-benchmark`](https://huggingface.co/datasets/google/frames-benchmark)
- MultiHop-RAG: [arXiv:2401.15391](https://arxiv.org/abs/2401.15391) · [yixuantt/MultiHop-RAG](https://github.com/yixuantt/MultiHop-RAG)
- BrowseComp-Plus: [arXiv:2508.06600](https://arxiv.org/abs/2508.06600) · [ACL 2026](https://aclanthology.org/2026.acl-long.1023/) · [texttron/BrowseComp-Plus](https://github.com/texttron/BrowseComp-Plus)
- LongMemEval: [arXiv:2410.10813](https://arxiv.org/abs/2410.10813) · [xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval)
- Loong: [arXiv:2406.17419](https://arxiv.org/abs/2406.17419) · [EMNLP 2024](https://aclanthology.org/2024.emnlp-main.322/) · [MozerWang/Loong](https://github.com/MozerWang/Loong)
- GraphRAG-Bench (textbooks): [arXiv:2506.02404](https://arxiv.org/abs/2506.02404) · [jeremycp3/GraphRAG-Bench](https://github.com/jeremycp3/GraphRAG-Bench)
- GraphRAG-Bench (ICLR'26 / "When to use Graphs in RAG"): [arXiv:2506.05690](https://arxiv.org/abs/2506.05690) · [GraphRAG-Bench/GraphRAG-Benchmark](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)
- WildGraphBench: [arXiv:2602.02053](https://arxiv.org/abs/2602.02053) · [BstWPY/WildGraphBench](https://github.com/BstWPY/WildGraphBench)
- InfoDeepSeek: [arXiv:2505.15872](https://arxiv.org/abs/2505.15872) · [YunjiaXi/InfoDeepSeek](https://github.com/YunjiaXi/InfoDeepSeek)
- DeepResearch Bench: [arXiv:2506.11763](https://arxiv.org/abs/2506.11763) · ResearchQA: [arXiv:2509.00496](https://arxiv.org/abs/2509.00496)

**Metrics and evaluation methodology**
- HotpotQA official eval: [`hotpot_evaluate_v1.py`](https://github.com/hotpotqa/hotpot/blob/master/hotpot_evaluate_v1.py)
- BenchmarkQED: [microsoft/benchmark-qed](https://github.com/microsoft/benchmark-qed) · [MSR blog](https://www.microsoft.com/en-us/research/blog/benchmarkqed-automated-benchmarking-of-rag-systems/)
- Contamination: CofCA [arXiv:2402.11924](https://arxiv.org/abs/2402.11924) · LastingBench [EMNLP 2025 Findings](https://aclanthology.org/2025.findings-emnlp.993/) · [Survey on Data Contamination, arXiv:2502.14425](https://arxiv.org/abs/2502.14425)
- Judge bias: [Position Bias in LLM-as-a-Judge](https://aclanthology.org/2025.ijcnlp-long.18.pdf) · [Self-Preference Bias, arXiv:2410.21819](https://arxiv.org/abs/2410.21819) · [Justice or Prejudice?, arXiv:2410.02736](https://arxiv.org/abs/2410.02736)
