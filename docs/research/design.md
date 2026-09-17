# Design record

Decisions taken on 2026-09-16 while scoping the project, with the alternatives that were considered
and why they lost. This is a living record: change a decision here when it changes, do not append
contradictions.

## Goals and non-goals

**Goal.** A composable, high-performance sandbox for everything LLM-plus-KG: construction from text,
retrieval (GraphRAG in all its variants), serialisation for prompts, storage backend comparison
(RDF vs property graph vs relational), and evaluation deep enough to say *when* a graph helps and
when it does not. Industry-first: the output is one system that performs, not a paper.

**First application.** Question answering / RAG, measured on public agentic multi-hop QA benchmarks.
All other KG applications (search, recommendation, digital twins, ...) come later; the data layer
must not preclude them.

**Non-goals for now.** Multi-machine deployment. A public Rust-facing API. A UI. Serving
infrastructure. Reproducing more than four pipelines before the harness reports numbers.

## Decisions

### D1. Python-first, Rust behind a clean boundary

Python is the user surface and the control plane: pipeline composition, LLM providers, prompts,
dataset loaders, judges, notebooks. Rust holds the data plane where it is measurably worth it: the
canonical schemas and visibility logic, lexical and vector indexes, traversal and PPR kernels,
serialisers.

Rule for placing code: if it touches an LLM or a dataset loader it is Python. If it touches the
graph or an index and a Python version is the measured bottleneck, or a better crate already exists,
it is Rust. Do not port to Rust speculatively.

*Alternatives.* Rust-everything with thin bindings (PyTorch style) would force reimplementing LLM
clients, tokenizers and loaders and would put a compile cycle in every notebook iteration. Pure
Python with "Rust later" tends to design the data layer around Python objects, which is precisely
what makes the port painful; the Arrow decision below is the mitigation.

### D2. Arrow-native shared data layer

Canonical tables, defined once as Arrow schemas owned by `triplum-core`. Times are UTC instants
(integer microseconds); intervals are closed-open; an open end uses a max sentinel rather than NULL
so range predicates stay simple.

| table | columns (initial) |
|---|---|
| documents | id (content-addressed), source, uri, observed_at, metadata (JSON) |
| document_grants | document_id, principal, granted_at, revoked_at (system-versioned: revocation closes, never deletes) |
| chunks | id, document_id, parent_id (hierarchy), level, span_start, span_end, text |
| chunk_embeddings | chunk_id, embedding_spec (model id plus revision plus dims), vector |
| entities | id (opaque, timeless), canonical_id |
| facts | id, proposition_id, subject_id, predicate, object_id (nullable), object_literal (nullable), object_datatype, object_lang, valid_from, valid_to, recorded_at, invalidated_at, invalidated_by_fact_id, confidence |
| fact_support | fact_id, group_no, chunk_id, extractor, recorded_at (a fact is supported by ANY group; a group needs ALL its chunks) |
| mentions | entity_id, chunk_id, span_start, span_end, confidence |

Three identities, kept apart on purpose (the peer review's central objection to the first draft):

- **Proposition**: the normalised `(subject, predicate, object)` triple, identified by
  `proposition_id`, a hash over the normalised components. Purely a grouping key.
- **Assertion**: one `facts` row. One source's claim about a proposition, with its own validity
  interval, confidence and transaction time. Two documents asserting the same proposition with
  different validity windows are two rows sharing a `proposition_id`.
- **Extraction occurrence**: one `fact_support` row, with the extractor identity and its own
  `recorded_at`. Support has a transaction-time boundary, so evidence added today cannot make a
  fact visible in a query that asks what was known last year.

Object rules: exactly one of `object_id` and `object_literal` is set (a CHECK, not a convention);
literals carry a datatype tag and optional language tag, and the literal-normalisation version is
part of the extractor identity.

Things that are deliberately *not* columns:

- **Entity names, types and aliases.** They are facts with literal objects (`label`, `type`, `alias`
  predicates) so they carry validity time and provenance like everything else. A privately sourced
  name must not show on a publicly visible entity, and an entity can be renamed. Display names are
  chosen from visible label facts at query time.
- **Entity-resolution merges.** A `same_as` fact with provenance, not a bare `canonical_id` write.
  In v1 the canonical mapping is still computed globally for speed, but because the merge is a
  provenance-bound fact it can be made viewer-aware later without a schema change. The temporal+ACL
  benchmark includes a "merge derived from a private document" family to keep this honest.
- **ACL on facts or entities.** Visibility is derived (D4) and only ever materialised as an index.

Python sees Polars DataFrames, zero-copy across PyO3 via the Arrow C data interface. Rust kernels
operate on columns. Persistence to Parquet or Lance and loading into any SQL engine is free.
Thin row dataclasses exist for notebook display and small manipulations only; they are views, not
a second model. Arrow batches are the *bulk interchange* format; narrow query results (a ranked
list of chunk ids, a neighbourhood) may use small typed results rather than a full frame.

Every module accepts and returns these frames, which is what makes "use a module alone" cheap: a
consumer produces a frame without importing the rest of the library.

*Alternative.* A pydantic object model mirrored by serde structs. Nicer to navigate in a notebook,
but every Rust call converts object graphs and two definitions must stay in sync. Rejected.

N-ary statements (an event with several participants) are represented as an event entity plus
binary role facts; this survived the peer review's grouping attack and needs no extra table.

**v1 restriction.** Extraction produces only single-chunk support groups (independently sufficient
evidence). Multi-chunk groups exist only for explicit derivations, which v1 does not perform. Any
fact without support is rejected at the store boundary.

### D3. Bi-temporal facts

`valid_from`/`valid_to` are world time; `recorded_at`/`invalidated_at` are transaction time, with
SQL:2011 semantics: rows are never overwritten or deleted, an update closes the old version and
inserts a new one. Entity ids are timeless; every attribute and relation is a fact that carries
time. Ingestion is episodic: a later document may yield a fact that contradicts an earlier one, and
the contradiction is recorded as `invalidated_at` plus `invalidated_by_fact_id` on the older fact.
Invalidation therefore has provenance, which Graphiti lacks.

Invalidation is **viewer-relative**: the older fact counts as invalidated only for viewers who can
see the invalidating fact. Otherwise a private correction would silently delete a public fact (the
peer review executed exactly this counterexample).

A `Viewer` carries `as_of_valid` and `as_of_recorded`, both defaulting to now, plus a
`permission_revision` that pins the ACL snapshot the query was authorised against. Rewinding
`as_of_recorded` rewinds facts, **not grants** (see D4). Retrieval caches are keyed on graph
revision, permission revision, viewer and both times.

Extraction decomposes text into atomic claims before producing tuples (ATOM's first module) so
that a validity interval and a supporting span are unambiguous per fact.

RDF 1.2 reifiers are an export target only; the spec is still a working draft. Literature, benchmarks
and the failure modes of existing systems are in
[`temporal-and-permissions.md`](temporal-and-permissions.md).

### D4. Permissions derived from provenance

Documents carry system-versioned grants to principals. A chunk is visible iff its document has a
grant to one of the viewer's principals that is active *now* (grants are evaluated at wall-clock
time even when `as_of_recorded` is in the past; an audit mode that rewinds grants is a separate,
separately authorised tool). A fact is visible iff at least one of its support groups is fully
visible. An entity is visible iff a visible fact touches it, and every attribute shown for it comes
from visible facts only.

Enforcement rules:

- **Filter inside the index, then rank.** The vector table is partitioned by a hash of the
  document's principal set (a sound coarse pre-filter); the FTS5 table carries an ACL token column
  ANDed into the match; a materialised `fact_principal(principal, fact_id)` closure is the exact
  check, refreshed on ingest and on grant change. Top-k is cut after the filter, never before.
- **Graph kernels run on the viewer's projection.** Degrees, PageRank normalisation, neighbourhood
  shape and any aggregate are computed over visible facts only; a hidden edge must not change a
  visible transition weight. Practically: materialise the visible adjacency for the viewer, then run
  the kernel.
- **Embeddings never leave the store for an excluded row** (vec2text reconstructs text from vectors).
- **Derived content inherits the ACL of its inputs and may never widen it.** This includes cached LLM
  outputs and anything written back to the graph.
- **No community or global summaries in v1.** A summary over the union graph is contaminated and
  cannot be redacted afterwards. Revisit as per-ACL-bucket summaries once bucket cardinality has been
  measured on real data.
- **Absence means "no support in this view"**, and the answer contract is refusal, not a guess.

Details, production precedents and the synthetic benchmark design are in
[`temporal-and-permissions.md`](temporal-and-permissions.md).

### D5. Composition by plain callables

A stage is a callable with typed frames in and out. A pipeline is a plain function calling stages.
Configuration is a frozen dataclass per pipeline; its hash is part of every run record. Sweeps are
the benchmark runner's job. No DAG framework, no YAML, no plugin registry until there is a
demonstrated need.

*Alternatives.* neo4j-graphrag-python's component DAG and DIGIMON's YAML-composed operators are
the two best existing designs (see [`landscape.md`](landscape.md)); both add a layer we do not need
while the number of pipelines is single-digit.

### D6. One LLM protocol, thin adapters, disk cache

`complete(messages, schema=None) -> Completion(text, parsed, usage, cached)`. Adapters:
OpenAI-compatible (covers vLLM, Ollama, OpenRouter, most providers), Anthropic, and a CLI subprocess
adapter for local harness subscriptions (`claude -p`, `codex exec`). A content-addressed disk cache
keyed on the **full effective request** (adapter id, model id and revision, messages, output schema,
generation parameters) stores the raw response plus parse/retry provenance, so reruns are free and
replay is exact. Model id plus prompt alone is not a valid key: the peer review collided two requests
that differed only in output schema. Cached replay is not general determinism; runs record whether
they were served from cache. CLI adapters must be invoked statelessly (no ambient conversation,
filesystem or tool context) or they fall outside this contract. Structured output via JSON schema
where the provider supports it, otherwise parse-and-retry.

*Alternatives.* litellm (a supply-chain incident tracked in Microsoft GraphRAG's issue #2289; heavy),
pydantic-ai or rig (frameworks, more than we need). Rust crates `genai`/`async-openai` are the
choice if the Rust side ever needs to call models directly.

### D6a. Every expensive stage is repeatable and cacheable

Not just LLM calls. Any stage whose cost is noticeable (corpus build, embedding a corpus,
index build, reranking, extraction, a whole run) is content-addressed on (input hash, config hash),
persists its output, and is skipped on rerun. The cache root is one directory per machine. Cache
hits are recorded in the run identity. Cost and runtime are metrics: every call and stage writes a
timed, priced event to the run store, and effective cost and runtime per question are reported next
to quality. This is a
second-class concern in the sense that no stage may *require* the cache to function, but every
stage must participate. Spec: `docs/specs/2026-09-16-harness-and-baselines.md`, "Caching and
repeatability".

### D7. Store protocol with SQLite first

One `Store` protocol whose every read takes a `Viewer`. Backend one is SQLite: FTS5 for BM25,
sqlite-vec for vectors, recursive CTEs for bounded traversal, `rusqlite` and the stdlib module.
Chosen for simplicity and single-machine performance at the scales we expect for a long time.
Cost: SQLite is row-based, so the Arrow boundary needs a conversion. Whether it dominates depends on
access pattern, not on the engine: narrow, filtered, batched reads feeding a kernel are cheap;
repeated wide neighbourhood materialisation is not. Rule: push filters and projections into SQL,
fetch text only after evidence is selected, batch adjacency reads, and profile store time, decoding,
Arrow construction and kernel time separately before adding any custom batching layer. Recursive
CTEs are for bounded k-hop only; PPR and other iterative kernels run on an in-memory CSR built from
the viewer's visible adjacency. Known constraint: FTS5's BM25 constants are fixed (k1 1.2, b 0.75),
which matters when comparing lexical scoring across backends.

Follow-on arms for the backend comparison, in order: **Neo4j** first (the property-graph incumbent
with native vector index, `neo4j-graphrag`, and GDS for PageRank; the question to answer is where
a graph database starts to pay off over SQLite for GraphRAG workloads, and at what scale and query
shape), then Oxigraph (RDF, SPARQL, `pyoxigraph`), LadybugDB (embedded property graph, Cypher, the
Kùzu successor), and DuckDB (columnar, Arrow zero-copy; can attach the SQLite file directly, so it
doubles as the analytics layer over backend one).

The `Store` protocol exposes typed capabilities, not query fragments: `visible_facts(viewer)`,
`neighbors(seeds, k, direction, predicates, viewer)`, `adjacency_batches(viewer)`,
`vector_search(vector, k, filter, viewer)`, `bm25(query, k, filter, viewer)`, and a typed
predicate-path request for patterns. A backend declares which filters it can apply exactly; an
unsupported filter fails or falls back to a measured exact path, never to silent over-fetch.
Neo4j Community has no RBAC or property-based access control, so on both stores the visibility
predicate is part of the query, which is what makes the comparison fair.

Details in [`storage-sqlite.md`](storage-sqlite.md) and [`store-comparison.md`](store-comparison.md).

### D8. Benchmark-first

The first sub-project is the harness, not a pipeline. It loads datasets into the canonical schema,
runs `(pipeline factory, dataset, evaluators, viewer)`, and writes one SQLite run store. A run record
identifies everything that produced an answer: dataset and artifact ids (document revisions, chunking,
extraction output, resolution decisions, index builds), code version, pipeline config hash, model ids
and revisions, embedding spec, prompts, seeds, effective viewer and time context, evaluator config,
and cache state; construction cost and per-query cost are recorded separately with component
timings. Reports are Polars frames. Code is identified per pipeline by a hash of the source files
it executes (not the git sha), so unrelated edits do not orphan runs and a crashed run can be
resumed by identity; the contract is `docs/benchmarking.md`.

Protocol commitments from [`benchmarks-multihop-qa.md`](benchmarks-multihop-qa.md): the HippoRAG
1000-question corpora rebuilt from upstream releases and verified by content hash (HotpotQA is
9,811 passages in the released files, not the 9,221 in the paper); "generation 2" configuration
(Llama-3.3-70B-Instruct or GPT-4o-mini reader, NV-Embed-v2 retriever, top-5) labelled in every run;
the embedder held fixed across all pipelines, because the embedder swing is an order of magnitude
larger than any architecture effect; every run reports EM, token-F1, Contain-Acc, Judge-Acc, R@2,
R@5 and indexing cost; mandatory baselines on every table: closed-book (contamination floor),
BM25-only, oracle gold passages (reader ceiling); the judge from a different model family than any
reader under test, with an A/A win rate recorded; BenchmarkQED AutoE adopted verbatim for the
no-gold path; MuSiQue is the dataset to run at full scale if only one can be, because it is where
graph methods actually separate from dense retrieval.
Protocol and metrics in [`benchmarks-multihop-qa.md`](benchmarks-multihop-qa.md).

The "auto-benchmark for your corpus" is the same runner plus BenchmarkQED-style question synthesis
for corpora without gold answers; that arrives with the temporal+ACL synthetic benchmark.

### D9. Repository and DX

Development and smoke runs on a laptop, full runs and local models on a GPU workstation. Nothing
assumes a machine; local-model adapters pick CUDA, MPS or CPU and record it in the spec. Runs are
not compared across machines and caches are not shared.


Cargo workspace under `crates/` (Polars layout: `[workspace.package]`, feature-flagged umbrella
crate, separate bindings crate). Python under `python/triplum/`, maturin mixed layout, uv. marimo
notebooks (plain `.py`, git-diffable) over the same package; Rust exploration stays in cargo examples
and tests. pytest and cargo test; one integration test per pipeline on a 20-question fixture.

Human-facing CLI discovery is a priority: exact matches first, unique prefixes accepted,
single fuzzy matches accepted with a notice; ambiguous/missing finite choices offered
interactively on terminals. All interaction
uses stderr; unresolved selectors with --no-input or nonterminal use yield actionable
usage errors. Library identities
and opaque values stay exact. Contract: `docs/specs/2026-09-16-cli-selection.md`.
Tests use focused helpers and real workflow fixtures. Report durations by default and branch
coverage explicitly in CI/on demand; mark real-model tests so the offline suite remains fast.
`uv run ty check` is required across source and tests; `cargo check` checks the Rust workspace.
Native exports carry matching Python stubs. Optional model dependencies stay optional in the
lean check, with a second CI check against installed local-model dependencies. Fix contracts
instead of excluding modules or using broad diagnostic suppressions.
Pre-commit exports the Git index and runs Cargo, ty and Ruff against that snapshot, preserving
unstaged and untracked work. Ruff formatting is checked without rewriting files during commit.

As of 2026-09-17, stage/adapter boundaries are cohesive; no broad module split is warranted.
The next focused structural work is RunStore's connection ownership, followed by an audit of
the manually maintained benchmark fingerprint dependencies (factories and fake adapters are
currently omitted). The benchmark assembly layer still assumes SQLite; extend that seam when
introducing a second backend rather than adding speculative interfaces now.

### D10. Name

`triplum`. Free on PyPI and crates.io as of 2026-09-16. See [`naming.md`](naming.md).

## Sub-projects, in order

1. **Foundation** (this record, README, research docs, SOTA monitor).
2. **First concrete task**, three threads sharing one harness and one corpus set (HotpotQA, MuSiQue,
   2WikiMultiHopQA under the 1000-question protocol), each answering one question:
   - **2a. Retrieval pipelines.** Runner plus naive dense baseline reporting numbers first; then
     hybrid with rerank; then Liao et al. best-practice GraphRAG and PPR-over-KG, with a matched
     graph-disabled ablation so a graph benefit is not merely a reranker or evidence-budget benefit.
     Question: which retrieval design wins on multi-hop QA, and by how much over the baselines.
   - **2b. KG-construction variants.** Same corpus, same retriever, swap the construction: open
     information extraction vs schema-based prompts vs ontology-aware prompts; with and without
     atomic-fact decomposition; entity-resolution variants (exact, fuzzy, embedding, LLM). Measured
     intrinsically (Text2KGBench-style triple P/R/F1 and ontology conformance where a schema exists)
     and extrinsically (downstream QA delta). Question: how much does construction quality move
     retrieval quality, and which construction choices matter. Background survey in
     [`kg-construction.md`](kg-construction.md).
   - **2c. Store comparison, SQLite vs Neo4j.** Same graph, same queries, both stores behind the
     `Store` protocol: k-hop neighbourhood, filtered vector search, BM25, PPR, pattern queries, at
     increasing corpus scale and viewer selectivity. Question: where do the benefits of a graph
     database start to show for basic GraphRAG usage. Methodology in
     [`store-comparison.md`](store-comparison.md).
   - **2d. Embedding sweep.** The dense baseline rerun once per embedding spec (API and local
     models, several size tiers; list in [`embeddings.md`](embeddings.md)); the winner is then
     pinned for 2a to 2c. Runs first, because the embedder swing on multi-hop recall is larger
     than any architecture effect, and it is the cheapest sweep (no graph rebuild).
   Part 1 of sub-project 2 (harness, non-graph baselines, embedding sweep) is specified in
   [`../specs/2026-09-16-harness-and-baselines.md`](../specs/2026-09-16-harness-and-baselines.md).
   Before any graph ingestion in 2a or 2b: small deterministic temporal/ACL contract fixtures (the
   seven question families in `temporal-and-permissions.md`, at toy scale) gating on retrieval-level
   leakage of zero.
3. **Further backends**: Oxigraph and LadybugDB implementations of `Store`, same benchmark as 2c.
4. **Temporal + ACL synthetic benchmark** and question synthesis for gold-less corpora.
5. **KG-construction V&V** in full: Text2KGBench (LettrIA-refined), SHACL (pyshacl or `pyrudof`),
   mapped onto the Schmidt et al. taxonomy.
6. Private benchmarks; more pipelines (agentic iterative, community summaries once principal-scoped,
   LightRAG-style local/global); non-QA applications.

Each sub-project gets its own spec and plan before code.

## Review record

- 2026-09-16, `peer-review --mode diff-review` on the part-2 harness (datasets, metrics, stages,
  runner, run store, CLI), peer: Codex (GPT family). Verdict "challenges". **Found unique defects,
  all fixed with regression tests**: unmapped gold passages silently scored recall 1.0 (loader now
  raises on missing or duplicate keys; verified zero on the full corpora); store reuse was decided
  by chunk count (now bound to the corpus hash in the store's meta table); run identity omitted the
  dirty flag and the prompt text (now hashes of reader and judge prompts, plus dirty); the seed was
  recorded but never sent to the model (now in GenParams, so in the cache key); judge usage was
  discarded and cached calls had null cost (judge returns its completion; cost is always computed
  and `cached` is a separate flag; report shows nominal vs spent); prices were not snapshotted per
  run (new `run_prices` table); the judge-family rule was not enforced (now raises for real models);
  the reranker was neither cached nor recorded (CachedReranker, pair count in the retrieve event);
  ties at the top-k cut were nondeterministic (chunk id tie-break everywhere). **Simplification
  accepted**: dead `RunConfig.from_json` removed. **Confirmed by the peer**: normalisation and F1
  match the official HotpotQA evaluator; hidden chunks cannot reach the hybrid stage.
- 2026-09-16, `peer-review --mode diff-review` on the part-1 implementation (scaffold, data layer,
  store, model protocols), peer: Codex (GPT family, CLI default model). Verdict "challenges".
  **Found unique defects, all fixed with regression tests**: `INSERT OR REPLACE` on documents
  cascaded and deleted the document's chunks and FTS rows on a second `put_documents`; grant
  changes through `put_documents` left `chunks.acl_tokens` and vec0 partitions stale; vector search
  cut top-k before the exact visibility check and the principal-set hash used an ambiguous NUL
  join; the LLM cache key ignored adapter configuration (`base_url`, CLI argv), letting two
  endpoints replay each other's answers. **Also fixed**: `level` typed Int64 in the store's chunk
  frame against Int32 in the canonical schema (the Polars view is now derived from the Arrow
  schema); a tmp-file race in the cache; fastembed's constant revision (now package version).
  **Rejected/no impact**: none. The peer could not execute the Python tests (no polars on its
  host) or build the PyO3 crate (host Python 3.9); those paths are covered by our own suite.

- 2026-09-16, `peer-review --mode design`, peer: Codex (GPT family, CLI default model). Verdict
  "challenges". Ten executable falsification attempts. **Changed the decision**: separate
  proposition / assertion / extraction identities; `recorded_at` on support rows; entity attributes
  and resolution merges as facts; support groups with ANY-group-fully-visible semantics;
  viewer-relative invalidation; cache key on the full effective request; run records identifying
  constructed artifacts; graph kernels on the viewer's projection; v1 restricted to
  single-chunk support. **Rejected**: an unconditional "SQLite conversion will dominate" claim (the
  peer itself rejected it for lack of measurements; D7 now says to profile first). **Survived**:
  timeless entity ids (rename attack), binary role facts for n-ary events (grouping attack),
  Python-first composition, SQLite-first, the run store, marimo and maturin layout.

- 2026-09-17, `peer-review --mode design` on CLI selection, peer **Claude Opus 5**.
  Verdict challenges; thirteen named falsification attempts. **Changed decision:** opt-in
  local coverage (explicit in CI) and --no-input on groups/commands as well as root.
  **Added verification:** no database creation on missing-run lookup, data-fetch choices,
  missing diff operand, distinct diff inputs, canonical rerun identity and opaque suffixes.
  **Rejected with reason:** dropping interactive menus, fuzzy IDs and command prefixes
  conflicts with the user's explicit requirement; multiple matches require a choice and scripts should use full names. The user later
  explicitly chose automatic acceptance of a single plausible fuzzy match. Question selection remains single-valued. Full rationale
  in the selection spec. The peer also confirmed the vendored-Click type incompatibility;
  implementation uses Typer callbacks and its own group class, not standalone Click types.

- 2026-09-17, fresh-context GPT-family subagent review of CLI selection: **added
  verification** for unknown IDs in populated stores, truly empty stores, omitted question
  filters returning every question and canonical sweep choices. No blocking defect found;
  made report accept --no-input consistently with the other commands.

- 2026-09-17, final `peer-review --mode diff-review` attempted with Claude Opus 5: no
  review result (OAuth token expired, HTTP 401). **No decision impact; untested by that
  peer.** Fresh-context GPT-family review completed instead: no blocking code defect;
  **added verification** above, and corrected stale docs after the user explicitly chose
  automatic acceptance of a single plausible fuzzy match. Its 40 CLI tests passed.

- 2026-09-17, typing and modularity design review, peer **Claude Opus 5**; thirteen named
  falsification attempts. **Changed decision:** run the optional-model type check on macOS
  rather than install the CUDA dependency stack on Linux. **Added verification:** precise
  Viewer constructor/helper types and whole-project Ruff scope. **Rejected with reason:**
  replacing the explicitly requested `uvx` hook with `uv run`; the tool-version difference is
  documented. The claim that the global hooks path bypasses `.githooks` was false: the
  installed dispatcher explicitly delegates there. Executable mode is enabled at installation.
  Dataset migration/typing observations concerned concurrent, separate work and are not included
  in this commit. Fingerprint omissions and RunStore ownership are recorded above as follow-ups;
  changing the missing-run API or introducing broad splits is outside this typing task.
- 2026-09-17, fresh-context GPT-family hook/typing review: **added verification** for alternate
  indexes, dependency-environment reuse and snapshot cleanup. Its editable-install leakage
  attack confirmed ty rejects modules absent from the snapshot. No blocking defect found.
