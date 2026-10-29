# Benchmark baseline workstream

## Goal and scope

Owner request (2026-10-12): grill-me on the highest-value design areas, in priority order:

1. Benchmark inputs, gold evidence and measurement contract (`BE`).
2. Retrieval result type, Viewer-aware read contract and BM25 baseline (`RT`).
3. LLM protocol and minimal closed-book / BM25 / oracle QA workflow (`LQ`).
4. Dense retrieval and fusion as controlled substitutions (`DF`).
5. Cache binding designed against one real expensive block: continues as Q10/Q11 (+ needed
   slices of Q12/Q14/Q17) in [open questions](../plans/questions/ingress-identity.md), owned by the
   concurrent [ingress and caching](2026-10-12-ingress-caching.md) workstream.

Ranking source: read-only review this session; independent peer gpt-6.1-sol (codex),
review `c95f8ffc076943339ba3e42fc43d14ca`, produced the same ordering. Peer added two
verifications: confirm gold-to-span recoverability first; prove benchmark-wide cache bypass
across nested decorated calls.

## Execution and checkout

- Mode: sequential (default). Concurrent mode not offered yet.
- Checkout: existing checkout on `main`, no worktrees or branch switches (AGENTS.md rebuild gate;
  global CLAUDE.md default). A concurrent session works on ingress/cache; preserve its edits and
  that session ended 2026-10-13 with its work committed (`472b3a4`, `be042db`, `603921e`).
- Review gate: each interface goes through declaration draft → Claude Opus / cross-model peer →
  owner approval before implementation (AGENTS.md).

## Owner policies

- **One Q&A file per design area** (owner, 2026-10-12, this request). Implemented as
  `docs/plans/questions/` with area prefixes. Scope: all design questions going forward. The
  existing `open-questions.md` stays the ingress/cache file until its concurrent session allows a
  migration; Q7 (gold evidence) is cross-referenced from `BE`, not moved, for the same reason.
  AGENTS.md still names the single file; updating it is proposed, not done.

- **Evaluation choices are configurable options** (owner, round 1 answers to BE3/BE5, scope: all
  evaluation/measurement: recall counting, answer normalization/matching, evidence scoring).
  Define the interface first; commonly used academic variants must be available; research how
  papers measure before defining anything of our own, so results stay comparable. Resolves:
  BE5 is a pluggable policy, not one chosen rule; BE3 counting is a parameter with a default.
- **Provenance is fundamental** (owner, goals.md commit `8a3d81f`, reaffirmed in round 1): every
  search result traces to its source span; each source carries provenance to the original document;
  needed for answer trust, automatic verification and evaluation.

- **Lists, not variable-length tuples, in record fields** (owner, round 2 BE1). Scope: record and
  interface declarations. Fixed-arity pairs (e.g. a span) are not covered; ask if unclear.
- **Constraints before component shapes** (owner, round 2 BE10): identify the surrounding lifecycle
  and the full set of interfaces before fixing an individual interface's shape. Eval is likely a
  hierarchical pipeline of steps (normalisation etc. as blocks within it). Resolves: BE10 is
  reopened and waits for the lifecycle/interface map (BE14).
- **Block catalogue documentation** (owner, round 2): once interfaces are settled, write text-heavy
  docs: one overview page of all interfaces/steps, one page per interface with its implementations
  and usage, including cache examples for the more expensive steps. Target for a later P task; not
  before the interfaces it documents are approved.

## Architecture summary (current state)

No QA dataset type, retrieval result, text/vector index, Viewer, LLM protocol, answerer, metrics or
run loop exist. Corpus datasets (MultiHop-RAG, FRAMES, MarkdownFolder) yield `Source`.
`tests/fixtures/hotpotqa.json` has 234 documents and 20 questions; its 40 gold references are old
integer chunk ids that match no document id.

## Settled decisions (inherited)

- Q7 (owner): gold evidence is span-based; full or mostly-full span coverage wanted; proportional
  partial credit possible; exact counting deferred until benchmark design (now).
- Goals: benchmark runs neither read nor write the cache; seeded stochastic repeats; judge from a
  different model family than any reader; required metrics EM, F1, Contain-Acc, Judge-Acc, R@2,
  R@5, indexing cost; baselines closed-book, BM25, dense, fusion, oracle, non-LLM extractor.
- AGENTS.md: corpus and optional QA/extraction inputs compose separately; no universal
  benchmark-task schema; built-in datasets live in `datasets/`.

## Backlog

| ID | Decision | Prerequisites | Status |
| --- | --- | --- | --- |
| BE1 | QA benchmark dataset interface (direction b) | research: shared benchmark shapes | Open, research running |
| BE2 | How gold identifies its document | ID state report (done); Q12 status | Re-present with ID facts |
| BE3 | Evidence recall | — | Answered round 2 |
| BE4 | Gold granularity | — | Answered: native granularity, recorded |
| BE5 | Answer normalization and containment | — | Answered by policy: pluggable, academic variants |
| BE10 | Answer-scoring interface | BE14 | Reopened |
| BE11 | Per-question context (distractor) settings | BE14, collections | Deferred by owner |
| BE14 | Benchmark run lifecycle and full interface map | — | Accepted as frame (gap → BE17) |
| Q22, Q23, Q9 | Source id, collection, fingerprints | — | Answered round 4 |
| Q24, Q25 | Chunking result membership; store writes | — | Re-present with context |
| BE17 | Persistence between stages; separate index-build and retrieval runs | BE16, Q22–Q25 | Ready later |
| RT1 | Retrieval hit record | BE14 | Round 3 |
| RT2 | Retriever and oracle selector | BE14 | Round 3 |
| BE15 | Evaluation layering | BE14 | Round 3 |
| BE16 | Sample/run records, usage, errors | BE14 | Round 3 |
| RT3 | Viewer contract; Viewer on every store read; as_of semantics | RT2 | Next |
| LQ1 | LLM request/response protocol | BE16 | Queued |
| RT4 | Evidence formatting and citation format | LQ1 | Queued |
| BE12 | Retrieval-metric interface | RT result type | Blocked |
| BE13 | Multi-session / episodic benchmarks (LongMemEval) | BE1 | Deferred |
| BE6 | Run identity record and benchmark-wide cache bypass | BE1, LQ protocol | Backlog |
| BE7 | Unanswerable / no-gold handling and eligibility reporting | BE1, BE3 | Backlog |
| BE8 | Oracle-passage baseline construction | BE2, BE4 | Backlog |
| BE9 | Judge protocol (prompt, binary, validation sample) | LQ protocol | Backlog |
| new | Source provenance to the original document (goals edit) | ingress area | Candidate, to raise with concurrent session's Q series or here |

## Investigations

- Local fixtures/history/datasets map (explore subagent, read-only; facts checked by script):
  - All fixtures share one shape: `questions` (id, question, answer, aliases, gold: list[int],
    qtype, answerable, as_of, metadata), `documents` (id, source, text, segments, uri,
    observed_at, grants, metadata), optional `triples`. 16 corpus+QA fixtures; 10 question-only
    (gold empty); 7 extraction-only.
  - **Old gold ids are fully recoverable**: `chunk_id(doc_id, ordinal)` = first 15 hex of
    sha256("chunk\0" + canonical_json([doc_id, ordinal])) (`cad9ea4^:src/triplum/data/corpus.py:27`).
    Every gold id in all 16 corpus+QA fixtures resolves to (document id, segment) → paragraph-level
    (document, [start, end)). Fact-level spans recoverable as verbatim substrings for multihoprag
    (44/44), ectqa (55/55), qasper (226/233); hotpotqa_full supporting-sentence titles all match.
  - Old design (deleted `cad9ea4`, `477e9d0`, `eff578c`): frozen Question record; GoldMappingError
    instead of silently empty gold; HotpotQA-normalised EM/F1 max over aliases; contain = normalised
    gold substring of prediction; recall = fraction of gold ids in top-k, None without gold; binary
    judge `{correct: bool}` with enforced different family; `LLM.complete(messages, schema, params)`
    keyed by request hash; run identity fields incl. corpus/questions hashes, config, models, prompt
    hashes, seed, replicate, viewer; Viewer = principals, as_of_valid, as_of_recorded,
    permission_revision.
  - Current: `MultiHopRAGCorpus` loads corpus only; `datasets/frames.py` is a Polars frame stream,
    not the FRAMES benchmark. No QA/evidence/metric/retrieval/Viewer/LLM types. `make_fixture.py`
    is gone; `datasets/manifest.json` is unreferenced.
- External research (web subagent, cited): HotpotQA/2Wiki sentence-level supporting facts,
  MuSiQue paragraph `is_supporting`, MultiHop-RAG (title, url, fact) with whitespace-stripped
  substring relevance, FRAMES page URLs only. HippoRAG R@k = passage-set intersection with
  passage = retrieval unit, plus AR@k; KILT counts complete provenance sets and lost ~18% of
  examples re-anchoring spans across Wikipedia versions; Chroma uses token recall/IoU; RAGChecker
  notes chunking bounds recall. SQuAD normalization + max over aliases; HotpotQA yes/no rule;
  Contain-Acc in FlashRAG/Adaptive-RAG/Self-RAG is character substring ("no" matches "not").
  FRAMES autorater κ 0.889 vs humans; self-preference bias supports cross-family judges. Run
  identity practice: Inspect EvalSpec, lm-eval git/doc/prompt hashes, HELM per-request state;
  hosted seeds are best-effort, so harnesses log requests rather than claim reproduction.
- Owner edited goals.md during this session (uncommitted): user-specified corpora should be as
  straightforward as public benchmarks; **provenance is fundamental**: every search result traces
  to its source span, and each source carries provenance to the original document. Affects BE2,
  BE4 and the RT area; raises a Source-provenance question for the ingress area.

- Recall/citation/matching research (web subagent, primary sources):
  - Dominant multi-hop definition: HippoRAG family passage-set R@k (k=2,5) and AR@k (all gold
    retrieved), exact passage identity (text equality in code), mean per question; no-gold scored
    0 in HippoRAG code, filtered in KILT. GFM-RAG reuses it. IRCoT: title-set recall, unranked,
    budget 15. KILT: page-level provenance sets. FlashRAG: answer-string-in-context recall plus
    document-id recall. MultiHop-RAG: fact substring (whitespace-stripped) Hits@4/10, MAP/MRR@10,
    paper vs code disagree (fraction vs any hit). FRAMES never defines its recall. RAPTOR, MS
    GraphRAG, LightRAG, PathRAG, StructRAG, ToG, G-Retriever report no retrieval recall.
  - Chunk-size fairness: only Chroma (token IoU/precision) and an F1@k argument (2410.13070);
    no standard fixed-token-budget recall found.
  - Citation: ALCE citation recall/precision via NLI over cited passages; AttributionBench,
    ARES, RAGAS faithfulness; page-level citation scoring exists but none on FRAMES.
  - Answer matching: EM/F1 (SQuAD norm) everywhere; substring containment under many names
    (FlashRAG acc, BERGEN Match, Self-Ask cover-EM, ALCE EM-recall, LinearRAG Contain-Acc);
    LLM judges (FRAMES, BERGEN, LinearRAG); KG QA Hits@1.
  - Researcher default: span-coverage τ=1 mean per question (reduces to HippoRAG R@k when chunks
    = native passages), AR@k, retrieved tokens; fixed-token-budget variant for cross-chunker
    comparison. KILT-EM gating not re-checked.

- Benchmark-shape research (web subagent, primary sources): universal fields across benchmarks and
  harnesses are id, question, acceptable answers, metadata; choices first-class where multiple
  choice is scored (Inspect, lm-eval); corpus-bearing harnesses (FlashRAG, BEIR, KILT) keep the
  corpus as a separate collection joined by document ids; KILT provenance carries character spans.
  Molding: per-question contexts pooled into one corpus (HippoRAG); text evidence (QASPER,
  GraphRAG-Bench, MultiHop-RAG fact) string-matched to offsets; URL-only evidence document-level;
  unanswerable flags (MuSiQue-Full, QASPER, MultiHop-RAG null_query, LongMemEval _abs). Misfits:
  LightRAG/UltraDomain (no gold, win-rate protocol), LongMemEval (per-question incremental haystack),
  multi-select; open-ended generation fits structurally but not EM/F1. Risk: MuSiQue pooled titles
  may repeat (unverified), so origin uniqueness needs a check.

- Pipeline/eval interface research (web subagent, primary sources): retrieval results are
  `NodeWithScore`-style wrappers (LlamaIndex) or score-on-document (Haystack); no framework carries
  rank or producing retriever as fields; only LlamaIndex TextNode and Haystack ExtractedAnswer carry
  character offsets; Haystack DocumentJoiner/ranx fuse runs (RRF, weighted); LlamaIndex
  postprocessors unify rerank/filter; FlashRAG refiner returns strings (loses provenance), reranker
  hidden in retriever, retrieval cache inside retriever; DSPy global retriever config hides identity.
  Eval layers recur: per-sample transform (lm-eval filters, Inspect Score.answer) → per-sample score
  → reduce over repeats (Inspect reducers) → aggregate across samples with stderr → report/compare.
  Normalisation is either scorer configuration (Inspect, FlashRAG) or named filter chains (lm-eval).
  Run identity: Inspect EvalSpec/EvalSample/role_usage closest; nobody content-addresses config.
  FlashRAG silently drops raising metrics; DSPy substitutes failure scores.

## Rounds

### Round 5 owner answers (checkpoint, 2026-10-29)

- Q24 (answered): option (a). One current chunking per source; `chunks(source_id)` returns only the
  configured chunker's chunks, ordered by the per-source-unique ordinal; changing the chunker clears
  and recomputes the source's chunks (cache makes expensive state fast to reproduce). (b)-like
  membership may return with benchmark run design (randomness, variability).
- Q25 (answered): agrees with (c): insert if absent, equal duplicate no-op, unequal duplicate raises;
  cache unaffected. Derived with Q24: chunks are not insert-only; a write replaces the source's
  whole chunk list. Old Source versions remain (new text = new Source id).
- Owner asks whether to look into the unclosed SQLite connection warnings (question; assessment
  given, no fix applied).
- Note: chunks are derived records, so clearing them is consistent with the history requirement,
  which the session reads as applying to facts and sources; flag if the owner disagrees.

### Round 5 (Q24 re-presented, Q25 re-presented, Q26, Q27)

Session assessment before peer: Q24 one chunking per source per collection (experiments compare
chunkers in separate collections; no membership record); Q25 insert-if-absent, equal duplicate
no-op, unequal duplicate error, never delete; Q26 producers (Utf8File, MarkdownFolder,
MultiHopRAGCorpus) take `collection_id` in `__init__`, Source requires it; Q27 id derived during
validation, supplied id must match, records frozen.

Peer gpt-6.1-sol, review `4254cb6d42c34fce9021d55e9c5dea3b`, full JSON read. Falsifications:
coexisting chunk sizes 4/8/20 by id; two histories with identical chunk unions; empty result
invisible in the union; A→B→A observations indistinguishable; MemoryStore alias mutation
(observed); redundant Chunk.origin vs equal-id assumption; one collection per chunker.

- Q24: **divergence**. Peer: ordered `ChunkingResult(source_id, chunk_ids)` membership (no chunker
  identity), because the chunk union cannot recover one result or an empty result. Session: separate
  collections; peer objects that duplicates Sources and fails same-Source coexistence.
- Q25: agreement; peer adds full-value comparison, race-safe insert, parent/slice/origin validation.
- Q26: agreement, keyword-only `collection_id` on producers; chunkers copy it from the Source.
- Q27: agreement; peer observed the MemoryStore alias mutation, which freezing fixes (unique defect
  confirmation of a known backlog item).

Implementation decision (session, within the owner's "go ahead with deterministic ids"): proceed
with Q26/Q27 as agreed by session and peer; leave the store write contract (Q25) and membership
(Q24) for owner answers. With derived ids, replace-by-id of an equal record is a no-op, so the
store change can follow separately.

### Round 4 owner answers (checkpoint, 2026-10-29)

- Q22 (answered): one id per exact text version. The fingerprint may share behaviour with the id or
  be partly based on it, given its attributes work out. **Policy: no timestamp fields in any id or
  fingerprint** (scope: all record ids and value fingerprints).
- Q23 (answered, premise corrected): deterministic cross-installation benchmark record ids are not a
  requirement; the owner never formulated it (it came from the session's framing). Resolves the
  divergence: collection ids are persisted UUIDv7 for all corpora; no manifest-published ids, no
  derivation from corpus identity.
- Q24 (partial): agrees chunker identity is not stored in chunk ids. Questions the ChunkingResult
  record: chunks reference their Source for provenance anyway; asks for the full question and
  original answers again. Open; re-present with context.
- Q25 (clarification): asks whether this concerns the cache or the store; cache writes should
  silently replace and cannot conflict (that would have been a hit); indexing pipelines should not
  produce store conflicts either. Open; re-present with context (it is the store).
- Q9 (answered): whole-record fingerprints with the same dependencies as the id.
- P1 (AGENTS.md trim) accepted. Deterministic ids accepted ("go ahead"); scope limited to what
  Q22/Q23/Q9 and the agreed layouts settle, while Q24's result record and Q25's write semantics are
  re-presented.

### Round 4 (Q22–Q25, Q9: identity basics) — session assessment before peer

Research (web subagent, primary sources): LangChain separates content id (uuid5 of content+metadata
hash) from `source_id_key` grouping with scoped cleanup; LlamaIndex ref_doc_id + hash upserts;
Haystack content-hash ids with DuplicatePolicy; Weaviate uuid5 via plain concatenation
(non-injective); git blob = content, tree binds path; XTDB stable `_id` + four temporal columns;
SQL:2011 `PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)`; RFC 9562: SHA-256 name-based ids must be v8,
§6.13 cautions name-based primary keys (canonical encoding must be frozen). No framework puts
splitter configuration in chunk ids; coexistence via namespaces. Researcher flags the agreed Chunk
layout (ordinal but no chunker identity) as an incoherent hybrid.

Session assessment:
- Q22: Source id per text version = f(full collection id, origin, text); (collection, origin) is the
  document key grouping versions for history and provenance.
- Q23: Source gains `collection_id`; collection ids random UUIDv7 persisted by default; a benchmark
  may derive one from its corpus identity (needs id-free dataset fingerprints, Q14). Full collection
  UUID inside the hash; tag bits are locality only.
- Q24: result identity: chunk id = f(source id, chunker computation identity, ordinal, start, text);
  coexisting chunkings in one store, simple per-result reads; duplicated equal spans accepted.
- Q25: equal id + equal fields no-op; equal id + different identity fields error; no replace-by-id;
  obsolete records closed (not deleted) once temporal fields exist; ordinal overflow error.
- Q9: Source fingerprint text only; Chunk fingerprint start + text.

Round 4 peer: gpt-6.1-sol (codex), review `46079fc7b277487abf9b2966b4ffd738`, full JSON read.
Falsifications executed: A→B→A, origin/collection changes, ('ab','c') vs ('a','bc') framing,
identical chunks under different chunkers, changed output under one chunker, empty results,
ordinal boundary, cross-collection fingerprint replay, origin-reading computation, A→B→A against
history, current SQL merge/read behaviour. Dispositions:

- Q22: agreement (per-version id, exact strings, no implicit normalisation). Added verification:
  a second occurrence of A needs a temporal occurrence key separate from the Source id.
- Q23: agreement on persisted UUIDv7 and `Source.collection_id`. **Divergence**: peer rejects
  deriving benchmark collection ids from dataset content; proposes published ids in a benchmark
  manifest. Session's derivation needs id-free dataset fingerprints (Q14) to avoid circularity.
- Q24: **session revised to peer**: chunk id from output (source id, ordinal, start, text) without
  chunker identity, plus an explicit ordered `ChunkingResult` membership record. Unique defect in
  session option: chunker identity in ids still needs a membership selector to read one result, and
  duplicates unchanged chunks on code edits.
- Q25: agreement; peer added atomic publication, full-value comparison on equal ids, and the
  correct capacity (65,536 chunks: ordinals 0–65,535).
- Q9: **session revised to peer**: whole-record fingerprints include their context (Source:
  collection, origin, text; Chunk: source, ordinal, origin, start, text); cross-context reuse uses
  explicit smaller payloads. Unique defect: current Chunk fingerprint omits source_id, so a cached
  record can replay another collection's parent ids, violating Q1.

### Round 3 owner answers (checkpoint, 2026-10-13)

- AGENTS.md is bloated (complaint, no explicit ask); asks why ID migration is explicitly excluded.
  Finding: the exclusion was written in `e7ef7ad` (2026-10-08, agent consolidation of guidance) as
  a scope fence on the cache authorization, when only the Chunk layout was agreed. It is not a
  decision against deterministic IDs. Trimming AGENTS.md offered as a proposal, not done.
- The ingress session ended; its work is committed (`472b3a4` multi-argument decorators,
  `be042db`/`603921e` effective-context refresh; Q10/Q11/Q19–Q21 answered). Q12 was not advanced.
  Uncommitted files are all this session's.
- **Policy: settle open basics early** (owner): fix identity/record basics sooner rather than later,
  to keep fewer changes in flight. Scope: open record/identity/storage basics (Q9, Q12–Q14 and
  related). Applied: next round is the identity basics, ahead of RT3/LQ.
- BE14 (accepted with a gap): lifecycle accepted ("alright"); owner notes it does not say where
  datasets/predictions live between stages (memory, all at once, on demand) or whether index
  building and retrieval can be separate runs. Recorded as BE17.
- RT1, RT2, BE15, BE16: no explicit answer; remain open as presented.

### Round 3 (BE14, RT1, RT2, BE15, BE16) — session assessment before peer

- BE14: adopt the lifecycle in [interface map draft](../plans/interface-map.md); enforce the gold
  boundary by type: the pipeline receives a query record (question, choices, context), never the
  QAQuestion.
- RT1: `Hit(chunk: Chunk, score: float)`, list order = rank; producer recorded in run identity;
  fusion emits new Hits.
- RT2: `Retriever.__call__(query: str, viewer: Viewer, /) -> list[Hit]`, k in `__init__`; metrics
  slice top-k from the deepest k. Minimal `Viewer(principals, as_of)` with a public/now default.
- BE15: four layers: per-sample transform (Normaliser steps), per-sample scorers configured with a
  normaliser, Reducer across repeats, Aggregator across samples. Named profiles assemble them.
  lm-eval-style filter chains not adopted now.
- BE16: SampleRecord and RunRecord; per-sample errors recorded, never dropped; run marked incomplete.

Round 3 peer: gpt-6.1-sol (codex), review `a1347712184249d3a9dfb7431bd9c534`, full JSON read.
Falsifications: oracle under a gold-free Retriever; provenance from Chunk alone; post-ranking
Viewer filtering; stale stored ranks after rerank; R@5 from a k=2 reader; normalising evidence
offsets; unequal repeats (2/3 vs 3/4); judge failure after reader success; top-level cache flag with
nested cached components; answerable/metadata as public fields; double-counted preparation cost;
one as_of as bi-temporal snapshot. Dispositions:

- BE14: agreement on separated preparation / public execution / privileged evaluation. Unique
  defects adopted: `answerable` and free metadata can leak gold, so the public projection carries
  only question, choices, context, as_of; store reads lack Viewer today, so Retriever access safety
  needs RT3 first; cache bypass must cover nested components. Added verification.
- RT1: agreement; score optional (oracle has none); tie policy recorded.
- RT2: **session revised**: oracle is a privileged selector taking evidence, not an ordinary
  Retriever (session's map could not look up gold from a public query). Peer wraps query + viewer
  into one input item per the one-item step convention; session had separate arguments. k in
  `__init__` agreed; evaluated retrieval depth ≥ 5 recorded separately from reader consumption.
- BE15: agreement; normaliser is a child block passed into each scorer (owner's hierarchical
  shape); explicit Score/MetricSummary with eligible/excluded/failed; mean per question over repeats
  then across questions; bootstrap resamples questions. Added verification.
- BE16: agreement; per-attempt sample records, run manifest, usage by stage/role with unknown ≠ 0;
  abort on preparation/configuration/access errors, continue-and-mark-partial on sample/scorer errors.
- New: RT3 Viewer contract and Viewer-taking store reads; as_of valid- vs transaction-time.

### Round 2 owner answers (checkpoint)

- General: retrieval interfaces are not all identified, and indexing only has base blocks. Wants the
  block catalogue docs (policy above) once settled.
- BE1 (open): use lists; open to covering other benchmark formats beyond direct QA later; asks for
  the lifecycle of Evidence/QAQuestion instances (explained in chat; see "Lifecycle" below).
  Alternative evidence sets and bundle-vs-plain-composition remain unanswered.
- BE2 (open): sources will receive more provenance context. Asks why UUIDv8 implementation is not
  proceeding. Answer (facts): AGENTS.md explicitly excludes Source/Chunk ID migration from current
  authorization; Source layout width, canonical hash inputs, collection-id generation/seeding,
  construction/conflict and ordinal-overflow policy are unspecified; Source has no collection
  reference yet (membership deferred) though its hash needs full collection identity; the ingress
  workstream queued Q12 after Q10, now marked "Source inputs ready". Nothing technical blocks a
  Q12 draft; it has not been presented for approval.
- BE3 (answered): accepts the round-2 proposal (span-coverage default, named variants, no-gold
  excluded by default with zero-counting option, best alternative set, retrieved characters).
- BE10 (reopened by policy "constraints before component shapes").
- BE11 (deferred): owner ideas: quite specific collection filters; a dataset spawning multiple
  collections; the 10–20 passage setting may be a (re)ranking evaluation. Fact: HotpotQA distractor
  has 10 paragraphs (2 gold + 8 tf-idf distractors), 2Wiki 10, MuSiQue up to 20.

### Lifecycle of QAQuestion/Evidence (as explained to owner, proposal)

1. A `datasets/` adapter reads pinned upstream files, prepares document text (fixed join rules) and
   emits corpus records plus frozen QAQuestion records; evidence spans are computed against the text
   the adapter itself produced and validated (key resolves, span in bounds, evidence text matches).
2. Questions form an ordinary fingerprinted dataset; records are immutable and never stored in the
   record store.
3. A run prepares Sources from the corpus, indexes them, and keeps the key→Source binding.
4. Per question, only question text, choices and context eligibility reach the pipeline; answers
   and evidence never do (except the oracle baseline, which reads evidence by design).
5. Scorers read evidence (with the binding and retrieved chunk spans) and answers after the pipeline
   returns; results keep question id plus scores.

### Round 2 (BE1, BE2, BE3, BE10, BE11) — session assessment before peer

- BE1: frozen Pydantic `QAExample` (id, question, answers[first canonical], answerable,
  evidence: list[Evidence] | None (None = unannotated), choices, as_of, metadata);
  `Evidence(origin, start | None, end | None)`; a small `QABenchmark` Protocol bundling
  `corpus: Dataset[Source]`, `questions: Dataset[QAExample]`, evidence granularity and
  `fingerprint()`, validating that every evidence origin resolves.
- BE2: origin as key, uniqueness validated at load (adapter suffixes duplicates); independent of Q12.
- BE3: default τ=1 span coverage, mean per question, k=2,5, plus AR@k and retrieved characters;
  first variants: document-level recall, answer-in-context, MultiHop-RAG fact hits, Chroma char
  coverage/IoU; no-gold questions excluded with eligibility counts.
- BE10 (answer scoring interface): `AnswerMetric` Protocol `(prediction, example) -> float | None`,
  normaliser as a parameter; named profiles (SQuAD/HotpotQA, FlashRAG) assemble metrics.
  Retrieval-metric interface waits for the RT result type.
- BE11 (per-question context / distractor setting): separate dataset per setting rather than a
  scope field.

Round 2 peer: gpt-6.1-sol (codex), review `927468a2a2c442bc986e7f8d0ecb52f2`, full JSON read.
Falsifications run: union/gap/sliver interval assertions, no-gold denominator effect (0.5 vs 1),
alternative-set flattening (1 vs 0.5), duplicate-title dict loss, schema against MC/no-evidence/
unanswerable/KILT/context cases. Dispositions:

- BE1: **divergence**. Peer nests evidence under each gold answer (`GoldAnswer(answer, evidence)`)
  so alternative evidence sets stay alternatives (KILT); adds a `CorpusDocument(key, origin, text)`
  record and plain composition of two datasets (no bundle). Session keeps flat answers/evidence
  (first datasets have one evidence set; owner asked for simplicity) and a small bundle. Adopted
  from peer: per-evidence `granularity` + `locator` (records how evidence is offered, BE4), nullable
  evidence/answerability, `context` keys (BE11). Added verification.
- BE2: **divergence persists**: peer benchmark-local key via CorpusDocument; session origin with
  validated uniqueness. Peer's duplicate-title counterexample adds a load-time uniqueness check.
- BE3: agreement; peer added max over alternative evidence sets, distinct profile names (not one
  "R@k" label), no-gold excluded by default with explicit zero-counting option. Added verification.
- BE10: agreement on separate scorer callables + normaliser; peer: reproduction profiles keep
  character-substring containment, token-boundary is a separately named project profile.
- BE11: **session revised to peer**. A separate dataset per setting cannot express per-question
  scope; distractor settings need per-question eligible document keys enforced before ranking
  (unique defect in session's option). Pooling is a distinct, recorded setting.

### Round 1 owner answers (checkpoint)

- BE1 (partial): direction (b), but as an interface: a `QABenchmarkDataset`-like type, since
  many benchmarks share close-enough shapes that can be molded. Needs follow-up research and
  questions; do not overcomplicate. Open.
- BE2 (not answered, premise challenged): owner believed deterministic UUIDv8 Source ids were
  settled and implemented; asks to revisit their state first, noting collection-id stability depends
  on the dataset–storage linkage, whose API is not fully defined. Finding (verified in all refs,
  including branches, the runner-documentation worktree and remotes): **no UUIDv8 code was ever
  committed**; Source/Chunk/Collection use `uuid7`. Agreed on 2026-10-07 (`6c3c890`): Chunk payload
  `[collection 16][source prefix 42][ordinal 16][fingerprint 48]`, A→B→A Source recovery, ≥24
  collection-tag bits for Source. Still proposal/open: Source layout `[collection 24][scoped
  fingerprint 98]`, canonical hash inputs, collection-id generation/seeding, construction/conflict
  policy, ordinal overflow. Tracked as Q12/Q13 in the concurrent ingress workstream.
- BE3 (partial): direction (b), top-k must cover the gold span; make it easily configurable (policy);
  research how most papers count first. Open pending research.
- BE4 (answered): use each dataset's native granularity and record how it is offered. For page-only
  provenance, citing the correct page counts; datasets with finer provenance are scored more
  strictly. Research further. Later: agent-assisted "is this answer correct" (RAGAS-style)
  evaluation. Session note: this is close to the peer's option (c).
- BE5 (answered by policy): offer options behind an interface; commonly used academic variants
  available. Interface design is a follow-up question.

### Round 1 (BE1–BE5)

Session assessment recorded before reading the peer:

- BE1: one plain Pydantic QA record in `datatype/` (question, answers incl. aliases, gold evidence,
  answerable, metadata); QA dataset = `Dataset[Question]`, composed separately from the corpus
  `Dataset[Source]`. Limited to QA; extraction keeps its own types.
- BE2: gold references `Source.origin` as the dataset-owned key; uniqueness validated within the
  corpus. Avoids Q12 and any new field.
- BE3: proportional coverage (mean covered fraction per gold span) as primary R@k, since it equals
  HippoRAG R@k when chunk = passage; also report all-complete AR@k and retrieved characters.
- BE4: paragraph-level canonical (HippoRAG comparability); dataset loaders regenerate fixtures,
  mechanical legacy conversion only as cross-check.
- BE5: SQuAD normalization, max over aliases, HotpotQA yes/no rule, token-boundary containment.

Peer: gpt-6.1-sol (codex), review `2640da6f0f5e4b719ecf322f046db963`, full JSON read. Ran
interval/normalization counterexamples (complementary chunks, duplicate chunks, one-char gap,
oversized chunk, length weighting, no/not, empty normalized gold, Unicode offsets, duplicate keys).

Dispositions:

- BE1: agreement; peer added tri-state answerability, absent vs explicitly empty evidence, a
  separate page-level evidence form, and an external sample key (added verification).
- BE2: **divergence**. Peer: dataset document key bound to the actual run-local Sources; do not
  assume origin unique; validate prepared text by digest; missing/ambiguous keys are input errors.
  Session keeps origin-as-key but adopts validation of uniqueness and text digest (added
  verification); separate key field remains the peer's alternative.
- BE3: **divergence, session revised**. Peer: strict full coverage (τ = 1) primary R@k, with
  proportional coverage and all-evidence recall alongside, equal weight per span, duplicates still
  occupy ranks, plus retrieved-character volume. Peer's oversized-chunk counterexample (unique
  defect in session view: coverage alone rewards huge chunks) and owner's "full" wording move
  session to the peer's primary.
- BE4: **divergence**. Peer: canonical coordinates, native granularity (sentence stays sentence,
  paragraph stays paragraph, pages separate). Session: paragraph canonical for comparability.
  Both agree legacy fixtures convert mechanically to paragraph spans now.
- BE5: agreement on token containment; peer added strict categorical yes/no and a separately
  labelled dataset-native profile for reproductions (added verification).

## Implementation proposals

- **P1 AGENTS.md trim** (accepted 2026-10-29): committed `4e64b98`. Per-approval history removed;
  approval scope lives in specs; no-timestamp/no-manual-version rule added. Rules unchanged.
- **P2 deterministic ids** (accepted 2026-10-29, "go ahead"): `datatype/ids.py` (pure UUIDv8
  derivation), frozen Source/Chunk with derived/validated ids, `collection_id` on both, Chunk
  `ordinal`, fingerprints with id inputs, producers take `collection_id`, SQL columns, tests/docs/spec
  migrated (docs and tests by a scoped worker, reviewed by session). Out of scope: Q24 membership,
  Q25 write semantics, temporal history. Worker also fixed a pre-existing fingerprinting failure for
  PEP 695 generic Protocols (`Utf8File.fingerprint()` raised); session extended it to hash lazy
  bound/constraint/default definitions.
  Verification (observed): 332 passed, 90% branch coverage, ty, Ruff lint/format, cargo check/test,
  strict MkDocs; examples/naive.py and examples/cached_pipeline.py ran.
  Cross-model diff review gpt-6.1-sol `965d356755ca4eafa1c5c499c1c6ccd3` (1,124-payload packing
  check, tag-collision search, framing probes, TypeVar probes, frozen bypasses, SQL tampering):
  unique defect, chunk digest lacked the full collection id (16-bit tag collision let a chunk with an
  inconsistent collection share an id) → fixed with regression; unique defect, parameterized
  TypeVar bounds failed → fixed; added verification, independent layout vector test; nits: inlined
  single-use helper, removed duplicate assertion; parentheses nit not applied (cosmetic).
  Remaining known limit: `model_copy(update=...)` bypasses validation (documented; SQL reads reject).

## Lasting documentation targets

Contracts: new `docs/specs/benchmark.md` (and retrieval/LLM specs as they arise). Questions:
`docs/plans/questions/`. Implementation state: `docs/flow.md` and concept guides.
