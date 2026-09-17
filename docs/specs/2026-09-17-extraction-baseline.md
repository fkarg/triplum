# Extraction baseline: non-LLM KG construction

Snapshot 2026-09-17. Spec for the first path that fills the graph tables (`entities`, `facts`,
`fact_support`, `mentions`) from chunks. It is deliberately LLM-free so that the LLM extraction
variants of sub-project 2b have a cheap, deterministic comparator, and so the store's graph side,
the extraction identity and the intrinsic metrics exist before any prompt is written. Research:
[`docs/research/kg-construction-nonllm.md`](../research/kg-construction-nonllm.md). Decisions it
relies on: D2 (three identities, one of `object_id`/`object_literal`, facts need support), D3
(atomic claims carry a span), D5 (stages are callables over frames), D6a (content-addressed
stages), D8 (extraction output is part of the run identity).

## Behaviour

1. **Two stages, plain callables over frames.** `extract(chunks, documents, extractor,
   recorded_at) -> Extraction` and `resolve(extraction, resolver, recorded_at) -> Extraction`.
   `Extraction` holds the four D2 frames (`entities`, `facts`, `fact_support`, `mentions`) plus
   a `claims` frame: every candidate clause the extractor saw (chunk, sentence span, subject
   span, predicate, object span, status, reason), accepted or not, so rejections are auditable
   and a later joint or generative extractor only has to produce grounded claims, not
   dependency-parser-shaped internals. Same input, same `recorded_at`, same output: no clock,
   no randomness, no network.
2. **Identity.** `ExtractorSpec` (name, version, model id and revision, rule-set hash) and
   `ResolverSpec` (name, parameters) are frozen dataclasses; their hashes are the `extractor`
   strings in `fact_support`. The rule extractor composes, internally, span detection (named
   entities with label, noun chunks, DATE/TIME/CARDINAL/MONEY/PERCENT/QUANTITY spans marked
   literal), relation rules (below) and grounding; that composition is an implementation
   detail, not the public protocol.
3. **Entity identity is document-scoped, resolution is evidence.** An entity's id is the hash
   of (document id, normalised surface): the same name inside one document is one entity, the
   same name in two documents is two entities until a resolver says otherwise. Resolvers emit
   `same_as` facts, each supported by one group holding both mention chunks (D2's one v1
   exception to single-chunk groups), so a merge a viewer cannot see both sides of does not
   exist for that viewer. v1 ships `exact` (NFKC, casefold, articles and possessives stripped,
   whitespace collapsed, same normalised surface across documents) and `fuzzy` (`exact` plus
   RapidFuzz `token_set_ratio >= t` within the same NER type). `canonical_id` is filled by a
   global union over all `same_as` facts for reporting only; traversal never reads it.
   Coreference is a later ablation.
4. **Rules, v1.** Only independent clauses: the verb is the sentence root or a `conj` of it,
   never under `mark`, `advcl`, `ccomp`, `xcomp`, `relcl` or `acl` (conditions, attribution,
   reported speech and relative clauses are recorded as claims with status `subordinate` and
   not materialised). Active transitive (`nsubj VERB dobj`), passive with agent (`nsubjpass
   VERB agent pobj`, swapped), prepositional (`nsubj VERB prep pobj`, predicate `verb_prep`),
   copula (`nsubj be attr|acomp`, predicate `be`), apposition (`X appos Y`, predicate `be`),
   with conjunct expansion on subjects and objects; a conjunct verb inherits the negation and
   modality of its head. Negated (`neg`) and modal (`aux` tagged `MD`) claims are recorded with
   that status and not materialised. Argument heads expand to the enclosing entity or
   noun-chunk span; a claim whose argument cannot be grounded to a span is `ungrounded`. An object that is a literal span becomes
   `object_literal` with a datatype (`date`, `number`, `money`, `percent`, `quantity`, `string`);
   dates parse with a fixed language and no reference to the current clock; unparsed dates stay
   strings.
5. **What the frames say.** Every grounded argument is a mention (entity, chunk, span). Every
   entity has `label` and, when NER gave one, `type` facts with literal objects, supported by
   the mention's chunk (D2: names are facts). Every accepted claim is one fact with one
   single-chunk support group. `fact.id` is the hash of (extractor, chunk, sentence span,
   proposition); `proposition_id` the hash of (normalised subject, predicate, object kind,
   object value, datatype, language), so an entity object and an equal literal never share a
   proposition. `valid_from` is the document's `observed_at` and `valid_to` the open sentinel:
   a declared approximation ("true from when we observed it") rather than inference from date
   spans, which v1 does not do (the research note's §6 explains why). `recorded_at` is the
   `recorded_at` argument. `confidence` is null for rules, not a fake probability; the schema
   and migration make it nullable.
5. **The store's graph side.** `Store` gains `put_graph(graph)` (entities, facts, support,
   mentions in one transaction; a fact without support or with both or neither object column
   is rejected), `facts(viewer)`, `mentions(chunk_ids, viewer)` and
   `neighbours(entity_ids, hops, viewer)`. Visibility follows D4 in SQL: a fact is visible iff
   one of its support groups is fully visible under the viewer's grants and both as-of instants;
   an entity iff a visible fact touches it; `neighbours` unions identities over visible
   `same_as` facts only. The store is bound to the corpus hash already; the graph adds a binding
   to the full graph identity below, so a different extractor, resolver or extract-module code
   on the same store is a refusal, not a silent mix.
7. **Bench integration.** Two identities, kept apart. The graph identity is (corpus hash,
   extractor hash, resolver hash, code hash of the extract modules); `bench.index.ensure_graph`
   skips only on an exact match and the store records it. The extraction run identity is the
   graph identity plus the gold hash (`questions_hash` now covers questions and `triples`) and
   the code hash of the scorer. Runs share the one `runs` envelope with a `kind` column
   (`qa` or `extract`) so events, artifacts and prices keep pointing at `runs`; QA-only columns
   become nullable and an `extraction_runs` detail table holds the metrics below.
   `triplum bench extract --dataset <name> --extractor <name> [--resolver <name>]` and the
   library call `bench.runner.run_extraction(cfg)`; an identical configuration returns the
   stored run.
8. **Intrinsic metrics** in `eval.triples`, per document (or per question where gold is
   per question) and micro-averaged, with one-to-one assignment between predicted and gold
   triples: `exact` (all three normalised strings equal) and `partial` (CaRB-style: token-level
   F1 per slot, all three slots at least 0.5, predicate stopwords removed, so `work_for` and
   `work_against` do not match). Duplicate propositions count once. Typed relation scores for
   CoNLL04 and SciERC are reported as unavailable until a versioned surface-to-schema map
   exists; their entity spans (kept in question metadata by those parsers) give span
   precision, recall and F1. 2Wiki `evidences` are not exhaustive, so its number is reported
   as evidence coverage (recall), not precision. Always: entities, facts, mentions, facts per
   chunk, claims by status, duplicate proposition rate, chunks per second. Extraction-only
   datasets (GraphJudge, GenWiki, CaRB, CoNLL04, SciERC) are the first targets.
9. **KG-as-source datasets.** MetaQA is registered (2026-09-17) with its KB verbalised into
   one chunk per entity in full sentences (`Kismet was directed by William Dieterle.` under
   Kismet, `William Dieterle directed Kismet.` under the director; templates versioned in the
   parser) and the KB triples in `triples` with `document_id` set. `put_graph` over gold
   triples (the oracle graph, supported by the verbalised chunk) and extraction over the
   verbalised chunks are the two ends of one scale; the latter is labelled synthetic, since it
   measures the templates as much as the extractor.

## Two extractors, one protocol

The research note's two stacks are both in scope, as two `Extractor` implementations behind the
same callable and the same `Extraction` output, so every number below is reported for each:

- **`rules`** (first): spaCy `en_core_web_sm` 3.8.0 (MIT) with the dependency rules above.
  Permissive, ~12 MB, tens of chunks per second.
- **`small_model`** (second, same plan): GLiNER `gliner_small-v2.5` (Apache-2.0) for spans with
  the dataset's type vocabulary, GLiREL `glirel-large-v0` for relations over a supplied relation
  vocabulary (weights declared CC BY-NC-SA 4.0 in the model prose while the package says
  Apache-2.0; recorded in `docs/licences.md` as research-only, which is fine for this project),
  optional `fastcoref` (MIT) as a coreference ablation. Around 3 GB of weights and single-digit
  chunks per second; installed through the `extract-models` extra. Its relation vocabulary is
  what makes CoNLL04 and SciERC typed scoring possible, so the "unavailable" typed scores below
  apply to `rules` only.

## Out of scope

Coreference in `rules`, external entity linking, temporal validity inference, atomic-claim
decomposition, a surface-to-schema map for scoring `rules` on typed sets, REBEL (kept as a
historical comparison if a paper needs it), and graph retrieval pipelines (the next spec;
`neighbours` exists so it can start).

## Dependencies

Extra `extract`: `spacy>=3.8.16`, the `en_core_web_sm` 3.8.0 wheel by URL (MIT), `rapidfuzz`,
`dateparser`. Extra `extract-models`: `gliner`, `glirel`, `fastcoref` with the pinned model
revisions from the research note. Rows in `docs/licences.md`. The lean environment stays lean:
the extractor modules import their libraries lazily and `ty` overrides list them, as for the
embedders.

## Verification

- Unit: each rule on one sentence; literal typing; negation and modal dropping; both
  resolvers on a synthetic mention table; `put_graph` rejections; D4 visibility on a
  two-principal fixture (a fact supported only by a private chunk is invisible to `public`,
  and so is an entity touched only by it).
- Integration: `extract` over every extraction fixture and the 2Wiki fixture, metrics
  non-zero, identical output hash on a second run; `ensure_graph` skips on rerun; the
  extraction run is found by identity.
- Numbers: exact and lenient P/R/F1 on CaRB, CoNLL04, SciERC, GenWiki test, GraphJudge and
  2Wiki evidences recorded in `docs/flow.md` as the baseline row every later extractor is
  compared against.

## Design review

Cross-model review via `peer-review --mode design` on 2026-09-17; the peer was GPT (codex CLI),
verdict "challenges", nine attempted falsifications named. Outcomes:

- **Changed the decision** (five): entity id was hash(type, surface), which conflates homonyms
  and splits an entity across inconsistent NER types; now document-scoped, with resolution as
  supported `same_as` facts. Global `canonical_id` could bridge public facts through private
  evidence; now traversal follows visible `same_as` only and merges cite both chunks. The
  extraction identity omitted gold and scorer code, and `ensure_graph` keyed on the extractor
  alone could reuse a stale graph after a code change; now two identities. The lenient matcher
  accepted `(ann, work_for, york)` for `(joann, work_against, new york)` in an executed check;
  replaced by one-to-one CaRB-style partial matching and typed scores marked unavailable. A
  separate extraction table would have orphaned events, artifacts and prices; now one `runs`
  envelope with a `kind`.
- **Added verification** (three): negation and modality scope on conditional, attributed and
  coordinated clauses (the subordinate-clause exclusion and the `claims` artifact come from
  this); replay with a different `recorded_at` and different `observed_at` documents must give
  distinct assertions and stable ids; the NOT NULL `confidence` in `schema.rs` and
  `migrations.sql` was confirmed by an in-memory insert and is now a schema change in scope.
- **No decision impact**: the three-part split becomes internal to the rule extractor (the
  peer's "should"); MetaQA verbalisation is labelled synthetic and uses full sentences.
- **Rejected**: none.

Owner's decision, 2026-09-17: this is a research project, so the GLiNER/GLiREL stack is a
shipped second extractor rather than a deferred option; its non-commercial relation weights are
recorded, not avoided. Intrinsic metrics first; graph retrieval is the next spec.
