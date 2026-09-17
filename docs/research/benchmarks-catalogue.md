# Benchmark catalogue: what `triplum` could auto-fetch next

Status: research note, 2026-09-16. Scope: every public benchmark we found that a knowledge-graph
harness could **auto-fetch and load into the canonical frames** (questions with gold answers,
a frozen corpus, gold passage ids or gold triples), beyond the three HippoRAG sets already
implemented. The question per row is fetchability and gold signal, not novelty.
[`benchmarks-multihop-qa.md`](benchmarks-multihop-qa.md) remains the protocol and metrics
document; this note extends its §1.4 and the benchmark tables in
[`temporal-and-permissions.md`](temporal-and-permissions.md) and
[`kg-construction.md`](kg-construction.md).

Method: three research passes (multi-hop QA with corpora; KG construction and extraction;
temporal, memory, abstention and access control), each reading the primary page (Hugging Face
API and dataset card, GitHub raw files, arXiv abstract) and fetching sample files. Licences are
**as declared on the data page**; "not stated" means no declaration, never an inference.
Eleven of the load-bearing licence and gating claims were re-checked against the Hugging Face API
by hand afterwards and all held. Rows marked *could not verify* were not fetched.

**Coverage.** Entity linking, KGQA over an existing KG and the standard open-domain and
reading-comprehension sets (NQ, TriviaQA, SQuAD, BoolQ, DROP, MS MARCO, KILT, BEIR, the shared
Wikipedia corpora and KG snapshots) are in a separate note,
[`benchmarks-standard.md`](benchmarks-standard.md): 114 configurations across seven families
with HTTP-verified URLs, sizes and licence declarations, and five adoption tiers. Entity
*resolution* on tables (Magellan, WDC) and open-IE canonicalisation (ReVerb45K, OPIEC) remain
unresearched.

---

## 1. Fetch mechanics, verified by HTTP

- `https://huggingface.co/datasets/<id>/resolve/main/<file>` works **anonymously** for every
  dataset below except NovelQA (`gated: auto`, returns 401). The pre-flight checks a fetcher should
  make are `https://huggingface.co/api/datasets/<id>?blobs=true` (per-file size, `gated`,
  `cardData.license`) and `https://datasets-server.huggingface.co/info?dataset=<id>` (configs,
  features, row counts); both are anonymous.
- GitHub raw works anonymously, including LFS blobs via `github.com/<org>/<repo>/raw/refs/heads/<branch>/<path>`.
  Watch the default branch (`zeroentropy-ai/legalbenchrag` is `master`). The GitHub JSON API is
  limited to 60 requests per hour unauthenticated and was exhausted mid-audit; a fetcher should use
  raw URLs, not the API.
- The HippoRAG `reproduce/dataset/*.json` files we already use are plain unauthenticated GitHub
  raw. **Upstream MuSiQue is Google Drive and upstream 2Wiki is Dropbox**, so the "verify the
  HippoRAG files against upstream releases" step in the protocol doc is not automatable.
- Not auto-fetchable and therefore out: anything on Google Drive or Dropbox (LegalBench-RAG,
  RAG-QA Arena base set, Wiki-ZSL, EvolvingQA, MemBench), gated Hugging Face repos (NovelQA),
  ModelScope-only hosting (Loong; modelscope.cn was unreachable, so its facts stay unverified),
  live-web corpora (InfoDeepSeek, CRAG task 3, RealTimeQA), and anything whose corpus is a
  Wikipedia dump or ZIM archive you must supply (HotpotQA fullwiki, FRAMES, FanOutQA, PopQA,
  EntityQuestions, NQ-Open, SituatedQA, StreamingQA).

## 2. Corrections to the existing research docs

Applied in the same commit as this note; listed here so the diff is explainable.

| Doc | Was | Is |
|---|---|---|
| benchmarks §1.4 | MultiHop-RAG "2,556 (HF shows 2,560)" | datasets-server reports 2,556; discrepancy closed |
| benchmarks §1.4 | WildGraphBench "1,197 (abstract says 1,100)" | the 12 split counts sum to 1,197; the abstract is stale. The card's advertised `gold_statements` field does **not** exist in the data; rows carry `question`, `question_type`, `answer`, `ref_urls` |
| benchmarks §1.4 | GraphRAG-Bench (a) at HF `jeremycp3/GraphRAG-Bench` | moved to `Awesome-GraphRAG/GraphRAG-Bench`; the academic-only, no-redistribution wording is verbatim on the new card, so the blocker stands |
| benchmarks §1.4 | GraphRAG-Bench (b) "MIT", "ships `evidence_relations`" as a gold-triple signal | the HF card declares **no licence**; MIT is a badge pointing at the code repo. `evidence` is a list of sentence strings and `evidence_relations` one free-text string per question, and answers are full sentences. It is not a drop-in triple metric |
| benchmarks §1.4 | BrowseComp-Plus at HF `Tevatron/browsecomp-plus`, 100,195 docs | two repos: `Tevatron/browsecomp-plus` (queries with inlined gold, evidence and negative doc text, 11.6 GB) and `Tevatron/browsecomp-plus-corpus` (the 100,195-doc frozen corpus, 5.3 GB). MIT on both |
| benchmarks §1.4 | `longmemeval-cleaned` licence "not verified" | MIT, same as the original; both cards checked |
| benchmarks §1.4 | ResearchQA "license unstated" | card declares MIT |
| temporal §A | ECT-QA listed by arXiv id only | released: HF `austinmyc/ECT-QA`, MIT, ungated, 480 transcripts plus 1,005 local and 100 global questions |
| temporal §A, §C | "none model a viewer"; "no published benchmark combines temporal and ACL dimensions" | GateMem (CC BY 4.0) and RBAC-Text2SQL (CC BY 4.0) give viewer-conditional gold answers. Neither is document retrieval and neither has a transaction-time axis, so the synthetic benchmark is still justified, on narrower grounds |

## 3. Catalogue

Columns: size is questions unless stated; **corpus** says whether a frozen text corpus ships with
the data; **gold** is the retrieval or graph gold signal, not the answer.

### 3.1 Multi-hop QA with a shipped corpus

| Benchmark | Source | Size | Corpus | Gold | Licence | Fit |
|---|---|---|---|---|---|---|
| **MoreHopQA** [2406.13397](https://arxiv.org/abs/2406.13397) | HF `alabnii/morehopqa`, raw JSON (viewer broken) | 1,118 verified, 14 MB | inline HotpotQA-style 10-paragraph `context` | per-step `paragraph_support_title` in a gold decomposition, plus the seed HotpotQA question | CC BY 4.0 | same record shape as HotpotQA, so the existing loader and dedup-into-corpus recipe apply; adds chain-level recall |
| **TEMPO** [2601.09523](https://arxiv.org/abs/2601.09523) | HF `tempo26/Tempo`, parquet, configs `examples`, `steps`, `documents` | 1,730 queries, 3,976 steps, 13 domains, 2.49 GB | **1,654,055 Stack Exchange docs** | `gold_ids` and `negative_ids` per query and per decomposed step; temporal coverage metrics | CC BY 4.0 (upstream CC BY-SA) | the only new find that satisfies every hard requirement and adds a temporal axis; 100x the HippoRAG corpus size, so start with two or three domain splits |
| **MultiHop-RAG** [2401.15391](https://arxiv.org/abs/2401.15391) | HF `yixuantt/MultiHopRAG` | 2,556, of which **301 null** | 609 news docs | `evidence_list` (title, url, fact) | ODC-BY | already vetted; the null class is the cheapest abstention signal we can get |
| **BrowseComp-Plus** [2508.06600](https://arxiv.org/abs/2508.06600) | HF `Tevatron/browsecomp-plus` and `-corpus` | 830, ~17 GB total | 100,195 docs | `gold_docs`, `evidence_docs`, `negative_docs` | MIT | already vetted; agentic only, canary-obfuscated fields |
| **WildGraphBench** [2602.02053](https://arxiv.org/abs/2602.02053) | HF `Bstwpy/WildGraphBench`, 3,932 files | 1,197 | raw reference pages per Wikipedia entity | `ref_urls`; join is URL to `references.jsonl` to a sanitised, truncated filename, which is lossy | Apache-2.0 | already vetted; answers are full sentences (judge, not EM); budget for the fuzzy join |
| **StratRAG** [2604.22757](https://arxiv.org/abs/2604.22757) | HF `Aryanp088/StratRAG`, 35 MB | 2,000 train, 200 val | 15-doc pool per question | gold at pool indices 0 and 1 | Apache-2.0 | HotpotQA-distractor re-cut by a single author; a deterministic **test fixture** for retrieval scoring, not a result |
| **SealQA** [2506.01062](https://arxiv.org/abs/2506.01062) | HF `vtllms/sealqa` | 111 / 254 / 254 | per-question doc sets of 12, 20, 30 | none beyond the inlined docs | Apache-2.0 | reader-robustness set, not retrieval; card announces an update on 2026-09-16, so pin a revision |
| **BRIGHT** [2407.12883](https://arxiv.org/abs/2407.12883) | HF `xlangai/BRIGHT`, 1.27 GB | ~1,384 across 12 domains | per-domain docs | `gold_ids`, `gold_ids_long`, `excluded_ids` | CC BY 4.0 | reasoning-intensive retrieval, not entity multi-hop; out-of-domain control at most |
| **CRAG** [2406.04744](https://arxiv.org/abs/2406.04744) | GitHub `facebookresearch/CRAG`, bz2, ~8 GB for task 3 | 4,409 | per-question raw HTML, no shared corpus, no gold doc ids | `false_premise`, `static_or_dynamic`, `popularity`, `alt_ans`; mock KG API | **CC BY-NC 4.0** | adopt the **label taxonomy**, not the data |
| **UltraDomain** [2410.05779](https://arxiv.org/abs/2410.05779) | HF `TommyChien/UltraDomain`, 2.17 GB | 20 domains | whole source doc inlined per row | none | Apache-2.0 | only useful to reproduce LightRAG win rates, i.e. the unresolved §3.1 spread |
| FRAMES, ResearchQA, DeepResearch Bench, Loong | see benchmarks §1.4 | | no corpus, or rubric-only, or unverifiable host | | | unchanged: tracked, not adopted |
| MINTQA, FinanceBench, NovelQA, LegalBench-RAG, RAG-QA Arena, FanOutQA, Bamboogle | | | no text corpus, PDFs, gated, Drive or Dropbox, ZIM, or no corpus | | | excluded, reasons in §1 |

**Single-hop and long-tail controls without a corpus**: PopQA (HF `akariasai/PopQA`, 14,267,
subject and object Wikidata ids plus aliases, **no licence tag**), EntityQuestions (Princeton zip,
4.8 MB, MIT), NQ-Open (CC BY-SA 3.0), TriviaQA (licence tag literally `unknown`). All need a pinned
Wikipedia snapshot. PopQA and EntityQuestions together are the standard "dense retrieval fails on
tail entities" evidence, which is exactly the claim a PPR-over-KG pipeline is supposed to beat.

**MuSiQue-Full** (unanswerable twins of the MuSiQue questions, CC BY 4.0, upstream on Google
Drive, mirrored on HF as `bdsaglam/musique`) is the cheapest abstention class for a corpus we
already index, with one caveat the research pass did not check: the HippoRAG corpus is the dedup
of the 1,000 sampled questions' paragraphs, and the unanswerable twins replace a supporting
paragraph with a distractor, so their paragraphs may fall outside it. A Full run is off-protocol
either way and must be labelled as a second configuration.

### 3.2 Temporal QA and incremental ingestion

| Benchmark | Source | Size | Corpus | Gold | Licence | Tests |
|---|---|---|---|---|---|---|
| **ECT-QA** [2510.13590](https://arxiv.org/abs/2510.13590) | HF `austinmyc/ECT-QA`, `data/{old,base,new}/*.json`, `questions/*.json` | 1,005 local + 100 global; **261 unanswerable** (242 out-of-scope, 19 false premise) | 480 earnings-call transcripts, 1.58M tokens, split base 2020–2023 vs new 2024 | `evidence_list` with filename, year, quarter; `question_type` single-, multi-, relative-time | MIT | **incremental ingestion (real before/after split), valid-time as-of, abstention** |
| **MenatQA** [2310.05157](https://arxiv.org/abs/2310.05157) | GitHub `weiyifan1023/MenatQA`, one JSON | 2,853 (scope, order, counterfactual) | inline Wikipedia paragraphs | `annotated_para`, explicit `time_scope` interval, counterfactual `updated_question` and `updated_answer` | **not stated** | valid-time perturbation; licence must be settled before use |
| **HoH** [2503.04800](https://arxiv.org/abs/2503.04800) | HF `russwest404/HoH-QAs`, parquet | not stated | outdated pages injected into the corpus | old and new answer via Wikipedia token diffs | Apache-2.0 | corpus-ingest staleness |
| **TimeQA** [2108.06314](https://arxiv.org/abs/2108.06314) | GitHub `wenhuchen/Time-Sensitive-QA` | ~41k | full Wikipedia paragraph per item | answer plus annotated time-evolving facts; no spans | BSD-3-Clause | valid-time as-of over inline text |
| **ChroKnowBench** [2410.09870](https://arxiv.org/abs/2410.09870) | HF `dmis-lab/ChroKnowBench` (biomedical split on Google Drive) | ~65k | mostly none | per-year answer sets 2010–2023 | CC BY 4.0 | validity intervals without a corpus |
| TempReason, ComplexTempQA, Test of Time, TRAM, DyKnow, RealTimeQA, TemporalWiki, StreamingQA, SituatedQA | see the report notes | | no corpus, or perplexity probes, or corpus must be rebuilt from a dump | | | excluded for the harness; ToT stays cited for contamination-free design |
| TempRAGEval, TimeR4, T-GRAG, LiveSearchBench, EvoWiki, Chronos | | | | | | **no verifiable release** |

Knowledge-edit sets with labelled multi-hop consequences: **MQuAKE** (GitHub
`princeton-nlp/MQuAKE`, MIT; CF-3k-v2 and T splits carry pre-edit `answer` and post-edit
`new_answer` on the same question plus `orig.triples` and `orig.new_triples`), MQuAKE-Remastered
(HF `henryzhongsc/MQuAKE-Remastered`, CC BY 4.0 on the data), RippleEdits (MIT, `original_fact`
next to the edit), KnowEdit (HF `zjunlp/KnowEdit`, MIT). All are framed as weight editing; the
corpus-ingest protocol is ours to write. **No benchmark anywhere labels the invalidating fact**; the
closest is a positional old/new pair. A gold "why do we no longer believe this" has to be derived.

### 3.3 Long-term memory and growing corpora

| Benchmark | Source | Size | Evidence ids | Update or contradiction family | Licence |
|---|---|---|---|---|---|
| **LongMemEval-cleaned** [2410.10813](https://arxiv.org/abs/2410.10813) | HF `xiaowu0162/longmemeval-cleaned`, 3.0 GB (`_s` 278 MB, `_m` 2.75 GB) | 500 | `answer_session_ids` plus per-turn `has_answer` | knowledge update, temporal reasoning, multi-session, abstention | MIT |
| **BEAM** [2510.27246](https://arxiv.org/abs/2510.27246) | HF `Mohammadta/BEAM-10M`, 344 MB | 10 conversations, 2,000 questions, up to 10M tokens | not confirmed per turn | separately scored contradiction resolution and knowledge update, plus abstention and event ordering | CC BY-SA 4.0 |
| **MemoryAgentBench** [2507.05257](https://arxiv.org/abs/2507.05257) | HF `ai-hyz/MemoryAgentBench`, 77 MB | 146 rows | partial | `Conflict_Resolution` split | MIT |
| LoCoMo [2402.17753](https://arxiv.org/abs/2402.17753) | GitHub `snap-research/locomo` | 10 of the paper's 50 conversations | partial | none | **CC BY-NC 4.0** |
| MSC, PerLTQA, MemBench, Zep DMR | | needs ParlAI; mainly Chinese, NC; Baidu or Drive; no released corpus | | | excluded |

### 3.4 Abstention

Failure modes: (a) evidence missing from the corpus, (b) inherently unknowable, (c) false premise,
(d) evidence retrieved but insufficient.

| Benchmark | Source | Unanswerable | Corpus | Mode | Licence |
|---|---|---|---|---|---|
| MultiHop-RAG null class | above | 301 of 2,556 | yes | (a) | ODC-BY |
| ECT-QA | above | 261 of 1,005 | yes | (a) and (c) | MIT |
| MuSiQue-Full | above | one twin per answerable question | per instance | (a) | CC BY 4.0 |
| SQuAD 2.0 [1806.03822](https://arxiv.org/abs/1806.03822) | HF `rajpurkar/squad_v2` | 53,775 | per-row paragraph | (a), adversarial | CC BY-SA 4.0 |
| KUQ [2305.13712](https://arxiv.org/abs/2305.13712) | HF `amayuelas/KUQ`, 10 MB | 6,884 labelled | no | (b) and (c) | MIT |
| FalseQA [2307.02394](https://arxiv.org/abs/2307.02394), CREPE [2211.17257](https://arxiv.org/abs/2211.17257), SelfAware | GitHub | | no, or retrieved passages only | (c), (b) | not stated |
| AbstentionBench [2506.09038](https://arxiv.org/abs/2506.09038) | HF `facebook/AbstentionBench`, needs `trust_remote_code` | 20 datasets | no unified corpus | all | **CC BY-NC 4.0** |
| RefusalBench, Sufficient Context, (QA)², Unanswerable-RAG | | | | | could not verify a release |

ECT-QA's 19 false-premise items are the only false-premise family found that sits on a shipped
corpus.

### 3.5 Access control and viewer-conditional answers

| Benchmark | Source | Size | Models a viewer | Gold | Licence |
|---|---|---|---|---|---|
| **GateMem** [2606.18829](https://arxiv.org/abs/2606.18829) | HF `Ray368/GateMem`, GitHub `rzhub/GateMem`, JSONL per domain | 91 episodes, 2,218 checkpoints | yes: principals with roles, every turn has a speaker and timestamp | per checkpoint `asker`, `as_of_turn_id`, `expected_action` in {answer 728, refuse 425, answer_redacted 302, no_memory 763}, regex `judge_spec`, `leak_targets` on 1,490 checkpoints | CC BY 4.0 |
| **RBAC-Text2SQL** [2607.22115](https://arxiv.org/abs/2607.22115) | HF `sharkiefff/RBAC-Text2SQL-Benchmark` | 21,502 eval | yes: column- and CRUD-level role policies | gold SQL when permitted, else a canonical refusal; metrics AC-F1, Safe-EX, violation rate, over-refusal rate | CC BY 4.0 (databases not redistributed; one split's gold is email-gated) |
| `respai-lab/RBAC` | HF | 280 | role and permission structure, no corpus | full, partial or denied plus rationale | CC BY 4.0 |
| ARBITER [2512.20535](https://arxiv.org/abs/2512.20535) | none | 389 | yes, synthetic | | **no release** |
| LeakDojo, OGX, Participant-Aware Access Control, DevRev-Search | | | no per-document permissions, or no dataset | | not ACL benchmarks; do not cite them as such |

GateMem independently arrived at four of the planned synthetic benchmark's design points:
principal-scoped questions, canary leak targets for judge-free leakage detection, refuse versus
answer-redacted versus no-memory as distinct expected actions, and an as-of cut over an
append-only log, which behaves like transaction time within one episode. Read it before finalising
the generator and cite it rather than claiming those four as novel. What still does not exist is a
document-retrieval corpus with per-document ACLs and a retrieval-level leakage metric, or anything
combining valid time, transaction time and a viewer.

### 3.6 KG construction: text to triples

| Benchmark | Source | Size | Gold | Licence | Fit |
|---|---|---|---|---|---|
| **GraphJudge corpora** [2411.17388](https://arxiv.org/abs/2411.17388) | GitHub `hhy-huang/GraphJudge`, line-aligned `.source` (JSON `[s,p,o]` list) and `.target` (text) files, scorer in repo | GenWiki-Hard 999 test / 69,788 train; SCIERC 100 / 346; rebel_sub 1,799 / 45,791 | gold triple set per passage | repo MIT; upstream CC0, CC BY-SA 4.0, not stated | lowest-effort real text-to-KG gold: `git clone`, read files |
| **GenWiki** (COLING 2020) | Edmond DOI 10.17617/3.YGO7EW, one 279 MB zip; reader in GitHub `zhijing-jin/genwiki` | 1.3M text–graph pairs (FULL), 750k (FINE) | DBpedia-aligned triples per paragraph, distant supervision | **CC0 1.0** | cleanest licence in this note; text is entity-masked, so not raw prose |
| **2Wiki `evidences`** | already vendored | 1,000 questions in our protocol set | human plus Wikidata triples per question; `evidences_id` only on inference and compositional questions and on three relations for the comparison types; test split has none | Apache-2.0 | **nobody has scored extracted triples against it** (searched; the nearest work, Distill-SynthKG [2410.16597](https://arxiv.org/abs/2410.16597), uses GPT-4o proxy triples instead). Recall-only, restricted to gold paragraphs |
| **CaRB** (EMNLP 2019) | GitHub `dair-iitd/CaRB`, TSV plus scorer | 634 test / 641 dev sentences | crowdsourced open-IE tuples, token-level P/R | MIT | open-IE coverage baseline for the unrestricted-triple arm |
| **BenchIE** [2109.06850](https://arxiv.org/abs/2109.06850) | GitHub `gkiril/benchie` | 300 sentences per language | fact synsets, exact-match P/R/F1 | **NEC academic or non-profit, non-commercial only** | strictest precision signal; optional, never default |
| **SciERC** | official site and the SpERT JSON mirror | 500 abstracts | entities, relations **and coreference clusters** | **not stated** | the one set with entity-resolution gold and triple gold on the same text; internal use only |
| **CoNLL04** | HF `DFKI-SLT/conll04` | 922 / 231 / 288 | typed spans, 5 relation types, gold clusters given | not stated | fixed-schema arm; "given gold mentions versus discovered" contrast |
| **LLMs4OL Challenge** | GitHub `sciknoworg/LLMs4OL-Challenge`, tasks Text2Onto, TermTyping, TaxonomyDiscovery, NonTaxonomicRE | per task, unverified | scores the **induced schema**, not instances | MIT; blind test sets behind CodaLab | the only family that evaluates schema induction |
| WikiEvents, SREDFM, FewRel, ADE | S3, HF | | events; multilingual silver triples; relation classification; one relation | MIT, CC BY-SA 4.0, MIT, unknown | weak fit |
| NYT10/11, Wiki-ZSL, WiRe57, LSOIE, OIE2016, SAC-KG, OntoURL, BenchIE-FL, Distill-SynthKG data | | | | LDC corpus withdrawn; no licence; Drive; no official release | excluded |

EDC, Docs2KG and iText2KG are systems with prompts and schemas, not gold sets: reference
implementations for the construction variants, not benchmarks.

## 4. Ranked shortlist

Ordered by value per unit of loader work, across all lanes. Each row names the triplum capability
it tests, which is the reason to add it.

1. **MoreHopQA**: multi-hop with a gold chain, same loader as HotpotQA. Tradeoff: HotpotQA-derived,
   and the last hop is often symbolic (counting, arithmetic), so report per-hop retrieval
   separately from answer EM.
2. **ECT-QA**: incremental ingestion with a real base/new split, valid-time as-of, and abstention
   including false premise, all on one MIT corpus. Tradeoff: one narrow domain, 1,105 questions,
   the 100 global questions need a judge.
3. **2Wiki `evidences`** as a triple-recall metric: zero fetch work, unclaimed in the literature.
   Tradeoff: recall only, partial id coverage, and the alias matching is the real design work.
4. **GraphJudge corpora** and **GenWiki**: real text-to-KG gold for sub-project 2b with near-zero
   loader work. Tradeoff: distant supervision, entity-masked text in GenWiki, mixed upstream
   licences in GraphJudge.
5. **MultiHop-RAG null class** and **MuSiQue-Full**: abstention on corpora we already index.
   Tradeoff: mode (a) only; MuSiQue-Full is off-protocol and its corpus coverage is unchecked.
6. **TEMPO**: the one new set with a frozen corpus, doc ids, per-hop gold, permissive licence and a
   temporal axis. Tradeoff: 1.65M docs is a multi-day KG-construction bill and the splits are very
   unbalanced; start with two or three domains.
7. **GateMem**: closest released artefact to the planned ACL benchmark. Tradeoff: conversational
   memory, not document retrieval; 91 episodes; regex judging.
8. **MQuAKE (CF-3k-v2, T)**: labelled multi-hop consequences of a fact change, a direct test that
   invalidation closes the old interval and propagates. Tradeoff: the ingest protocol is ours to
   write, and it gives no invalidating-fact link.
9. **LongMemEval-cleaned**: growing corpus with session and turn gold and a knowledge-update
   family, licence now settled. Tradeoff: `_m` is 2.75 GB and needs a judge.
10. **BrowseComp-Plus** and **WildGraphBench**: unchanged from the protocol doc's second tier, with
    the corrected fetch facts above.
11. **PopQA plus EntityQuestions**: long-tail control that is the canonical case for graph
    retrieval. Tradeoff: no corpus, PopQA has no licence tag.
12. **CaRB**, then **CoNLL04** and **SciERC**, then **LLMs4OL** for the 2b variants as they land.

Adopt for metric or taxonomy design only, not data: **RBAC-Text2SQL** (the AC-F1, Safe-EX,
violation-rate, over-refusal quartet), **CRAG** (false premise, static-to-real-time dynamism,
head/torso/tail popularity, `alt_ans`), **StratRAG** (as a deterministic retrieval-scoring fixture).

## 4b. Registered on 2026-09-17

Every row of the shortlist except WildGraphBench and LLMs4OL is now a registry entry
(`triplum data` lists them; `docs/specs/2026-09-17-dataset-registry.md` is the spec). Fetch facts
were re-verified by a Codex pass that downloaded each file, hashed it and joined a 50-question
sample of gold to the shipped corpus (50/50 everywhere a corpus ships); the pins live in
`python/triplum/eval/datasets/manifest.json`. What changed against the rows above:

- **MoreHopQA** ships two inline paragraphs per question, not ten; the corpus is their union
  (601 passages over the 1,118 verified questions).
- **ECT-QA** reporting quarters are periods, so `observed_at` stays 0 and the old/new split is in
  document metadata; the 100 global questions have no gold and are not loaded.
- **2Wiki full**: the `xanhho` parquet mirror keeps `evidences` but drops the Wikidata ids; the
  official zip (259 MB, Dropbox) is not registered.
- **MuSiQue full**: only the dev file is registered (59 MB; train is 477 MB); the 2,417
  unanswerable twins load with an `__unanswerable` id suffix.
- **BrowseComp-Plus**: 4.5 GB, not 11.6 GB; query strings and doc ids are obfuscated with the
  public canary and decoded by the loader; the query shards may need a Hugging Face token.
- **GateMem** turns lack a timestamp a quarter of the time and no per-turn visibility label
  exists, so grants are the speaker only and the set is declared `needs` a viewer per question.
- **LongMemEval-cleaned**: only `_s` (277 MB) is registered; haystacks are namespaced per
  question and the set is declared `needs` a corpus per question.
- **GraphJudge** GenWiki-Hard has a few hundred non-3-tuples, kept in document metadata.
- **Standard sets from the [standard benchmarks note](benchmarks-standard.md)**, registered the
  same day: its first two adoption tiers minus the KG-as-source sets. NQ-Open, AmbigQA, Bamboogle,
  FreshQA and both ARC splits are question-only; SQuAD 1.1/2.0 and BoolQ use the question's own
  passage as gold; QuALITY (115 articles as single chunks) and QASPER (papers chunked into
  abstract, paragraphs and captions, the first multi-chunk documents in the registry; 78 of 1,451
  test questions whose evidence is table content match no chunk and are not loaded) cover long
  documents. MetaQA and KQA Pro wait for a KG-as-source representation; OpenEA and the BEIR sets
  are not question sets in the canonical frames.
- **WildGraphBench** is not registered: its 3,894 reference pages are separate files joined by a
  slugified title, a 3,930-entry manifest for a second-tier set. **LLMs4OL** is term typing and
  taxonomy induction, which the canonical frames do not represent; both stay catalogue-only.

## 5. What the dataset adapter has to support

Consequences for the loader, derived from the rows above rather than from any single set:

- **Gold in four shapes**: doc ids (BrowseComp-Plus, TEMPO, BRIGHT), titles or title-plus-text
  (HippoRAG, MoreHopQA), URLs that must be joined to files (WildGraphBench, FRAMES), and sentence
  strings (GraphRAG-Bench (b)). Only the first two map onto `gold_chunk_ids` today.
- **A corpus can be a second repo** (BrowseComp-Plus) or **absent** (the control sets), so the
  corpus and the question set need separate fetch and hash identities.
- **An unanswerable class** with a gold of "abstain" and an over-refusal counter on the answerable
  rest. Nothing in the metrics module handles this yet.
- **Ingestion slices** with `observed_at` set from the data (ECT-QA old/base/new, HoH, MQuAKE
  edits), which is the first real use of the `observed_at` column we currently zero.
- **Gold triples per question** (2Wiki, GraphJudge, GenWiki) alongside or instead of gold passages.
- **A viewer per question** (GateMem) and per-document grants that are not all `public`.
- **Per-hop gold** (MoreHopQA, TEMPO steps) for chain-level recall.

## Open questions

- Entity resolution on tables and open-IE canonicalisation: not researched. Entity linking and
  KGQA-over-KG are covered in [`benchmarks-standard.md`](benchmarks-standard.md); none of those
  sets is registered yet, and the KG-backed ones need a KG ingestion path first.
- MuSiQue-Full paragraph coverage against the HippoRAG corpus: unmeasured.
- TEMPO's per-domain sizes and whether `gold_answers` can be scored without a judge: not inspected.
- Loong: ModelScope unreachable, nothing verified.
- BEAM per-turn evidence ids, MemBench and PerLTQA files, RefusalBench, Sufficient Context,
  EvolvingQA, EvoWiki, Chronos, and TGB's per-dataset licences: not spot-verified.
- MenatQA, SciERC, CoNLL04, PopQA licences: not stated at source; internal use only until settled.
- Decoding on Graphs [2410.18415](https://arxiv.org/abs/2410.18415) and the imperfect-KG error
  taxonomy [2603.14828](https://arxiv.org/abs/2603.14828) may overlap the 2Wiki triple-recall
  idea; neither paper was read.

## Sources

Primary pages fetched on 2026-09-16: the Hugging Face dataset API and cards for every HF id
named above; GitHub raw files and LICENSE files for every GitHub repo named above; arXiv abstract
pages for every arXiv id named above; the Edmond Dataverse API record for GenWiki; the LDC
catalogue page for LDC2008T19; the Princeton EntityQuestions zip; the SpERT dataset mirror.
