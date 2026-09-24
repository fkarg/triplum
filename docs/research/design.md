# Design record

Decisions and the alternatives considered while scoping the project. This is a living record:
change a decision here when it changes; do not append
contradictions.

## Goals and non-goals

**Goal.** A composable, high-performance sandbox for everything LLM-plus-KG: construction from text,
retrieval (GraphRAG in all its variants), serialisation for prompts, storage backend comparison
(RDF vs property graph vs relational), and evaluation deep enough to say *when* a graph helps and
when it does not. A research project: the output is measurements that decide between techniques,
and a library whose modules recombine into the next experiment (the doctrine and its
consequences are in `AGENTS.md`).

**First application.** Question answering / RAG, measured on public agentic multi-hop QA benchmarks.
All other KG applications (search, recommendation, digital twins, ...) come later; the data layer
must not preclude them. The owner's own corpora are the second application and the reason the
loaders take local files: a folder of papers (PDF), then podcast and video transcripts (YouTube
and other sources), ingested in full, extracted, linked across sources and searched. Media
transcription and OCR are separate sub-projects; the ingest layer takes text and its provenance.

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

Canonical frames govern store and processing-stage boundaries, not arbitrary dataset records.
`utils.data` separates indexed/streaming access from lazy loading and collation; source authors
choose their record types. Both dataset base classes require `fingerprint()` identifying ordered
logical content without consuming iteration. A built-in source's identity is a versioned recipe
(pinned file digests, parser version, record contract, resolved parameters) known before any
read; an in-memory source hashes its content. Loading batch size and physical chunk layout do
not affect identity. This is not Python `__hash__`.

Benchmark sources must replay the same ordered records on every traversal for a given fingerprint.
Generic loaders can still consume one-shot iterators, but a one-shot source is unsuitable for a
benchmark: an artifact miss may read it again. A changed corpus, including a seeded variant, has
its own fingerprint and therefore its own store. Data variants use a fixed seed at construction;
replicates keep the data fixed and vary pipeline randomness. `DistractorCorpus` is the first
concrete variant: it keeps question evidence and selects additional chunks with a fixed seed.

*Built-in datasets.* Sources yield pydantic records at the boundary:
`Document` with the segments the source ships as units, `Question`, `Triple`. Document ids are
the source's declared key (an upstream id, else a content key), never parse position; chunk ids
are `chunk_id(document_id, ordinal)`, so a question resolves its gold from its own record.
Collators project record lists onto the canonical frames; the consumer chooses the batch size.
Chunking beyond source segments is a later stage. The earlier source design is in the
[temporary foundation note](../notes/previous-foundation.md).

Canonical tables, defined once as Arrow schemas owned by `triplum-core`. Times are UTC instants
(integer microseconds); intervals are closed-open; an open end uses a max sentinel rather than NULL
so range predicates stay simple.

| table | columns (initial) |
|---|---|
| documents | id (source-declared), source, uri, observed_at, metadata (JSON) |
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

Store and bulk processing modules accept and return these frames, which makes using a module
alone cheap. Dataset sources may use custom records, adapted to frames at those boundaries.

*Alternative.* A pydantic object model mirrored by serde structs. Nicer to navigate in a notebook,
but every Rust call converts object graphs and two definitions must stay in sync. Rejected.

N-ary statements (an event with several participants) are represented as an event entity plus
binary role facts; this survived the peer review's grouping attack and needs no extra table.

**v1 restriction.** Extraction produces only single-chunk support groups (independently
sufficient evidence). Multi-chunk groups exist only for explicit derivations; the one v1
derivation is a `same_as` fact from resolving two mentions, which cites both mention chunks as
one group, so a merge is invisible to a viewer who cannot see both sides. Traversal follows
visible `same_as` facts; `canonical_id` is a global materialisation for reporting, never a
visibility shortcut (peer review of the extraction spec). Rule-based extractors have
no calibrated confidence, so `confidence` is nullable on facts and mentions rather than a
fabricated number. Any fact without support is rejected at the store boundary.

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

RDF 1.2 reifiers are an export target only. The earlier literature survey is archived in the
[research snapshots](../notes/research-snapshots.md).

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

The temporal and ACL fixture families are listed in the
[stack walk](../plans/stack-walk.md); earlier precedents are in the
[research snapshots](../notes/research-snapshots.md).

### D5. Composition by plain callables

A stage is a callable with typed frames in and out. A pipeline is a plain function calling stages.
Configuration is a frozen dataclass per pipeline; its hash is part of every run record. Sweeps are
the benchmark runner's job. No DAG framework, no YAML, no plugin registry until there is a
demonstrated need.

*Alternatives.* Component DAGs and YAML-composed operators add a layer we do not need while the
number of pipelines is single-digit.

### D6. One LLM protocol, thin adapters, disk cache

`complete(messages, schema=None) -> Completion(text, parsed, usage, cached)`. Adapters:
OpenAI-compatible (covers vLLM, Ollama, OpenRouter, most providers), a CLI subprocess adapter for
local harness subscriptions (`claude -p`, `codex exec`), and a native Anthropic adapter when a
reader needs it (not built; the CLI adapter covers Claude today). A content-addressed disk cache
keyed on the **full effective request** (adapter id, model id and revision, messages, output schema,
generation parameters) stores the raw response, so reruns are free and
replay is exact. Model id plus prompt alone is not a valid key: the peer review collided two requests
that differed only in output schema. Cached replay is not general determinism; runs record whether
they were served from cache. CLI adapters must be invoked statelessly (no ambient conversation,
filesystem or tool context) or they fall outside this contract. Structured output via JSON schema
where the provider supports it. Parse/retry provenance is still open (R5 in the
[caching gap map](../specs/caching-and-monitoring.md)).

*Alternatives.* litellm (a supply-chain incident tracked in Microsoft GraphRAG's issue #2289; heavy),
rig (Rust framework). Rust crates `genai`/`async-openai` are the choice if the Rust side ever
needs to call models directly.

*Owner's decision.* pydantic-ai is adopted, under this protocol rather than
instead of it: one adapter over its direct model-request API replaces the per-provider adapters
and gives validated structured output, and its typed message and output datatypes are the
default candidates for `Message` and `Completion` when the adapter lands (with the LLM
extractor spec, the first stage where structured output changes results). An agent loop is
cacheable as a whole: the request is the agent specification plus its inputs, the response is
the final output, and the key is that whole. The condition is that every tool the loop can
call is a pure function of inputs already in the run identity (the store bound to its corpus
hash, the config); a tool over ambient state falls outside the contract, like a stateful CLI
adapter.

### D6a. Every expensive stage is repeatable and cacheable

Not just LLM calls. Any stage whose cost is noticeable (corpus build, embedding a corpus,
index build, reranking, extraction, a whole run) is a plain function wrapped as a *stage*
(`triplum.stage`): its artifact is addressed by a **data key** over the identities of its
arguments (source fingerprints, upstream artifact keys, configs, adapter specs, the derived seed)
and validated by a **code manifest** discovered at run time, the first-party functions the stage
actually executed with docstring-stripped source hashes, the plain-data constants they read, and
the distribution versions involved. A rerun fetches the artifact when the key matches and the
manifest, and the manifests of every input artifact along the lineage, still hash the same; a
code edit reruns exactly the stages that executed it, against fetched inputs. No version strings:
a library whose users override helpers cannot rely on anyone bumping one. Author rules: a stage
that returns a stream runs under its own seed and records code on each pull, not while idle. A stage
reads everything that shapes its output from its arguments and constants, never from mutable
module state or the environment. Store effects (ingestion, embeddings, the graph) are recorded by
the store itself. Provenance (artifacts, invocations, their input edges, manifests) lives in the
run store, so lineage is a query. The cache root is one directory per machine. The SQLite run
store is the sole live event stream: every call and stage writes a timed, priced event, and effective
cost and runtime per question are reported next to quality. No stage may *require* the cache to
function, but every stage participates. The earlier stage design is in the
[temporary foundation note](../notes/previous-foundation.md). The earlier form (a hash of the pipeline's source files in
the run identity) is superseded.

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

Earlier backend surveys are in the [research snapshots](../notes/research-snapshots.md).

### D8. Benchmark-first

The first sub-project is the harness, not a pipeline. A benchmark composes independent corpus,
QA and extraction sources; gold triples are not a field on generic datasets or corpora. Built-in
sources live in `triplum.datasets`, separate from evaluation. The harness loads these sources into the canonical schema,
runs `(pipeline factory, dataset, evaluators, viewer)`, and writes one SQLite run store. A run record
identifies everything that produced an answer: dataset and artifact ids (document revisions, chunking,
extraction output, resolution decisions, index builds), code version, pipeline config hash, model ids
and revisions, embedding spec, prompts, seeds, effective viewer and time context, evaluator config.
Cache hits and misses are measured outcomes, not identity fields.
Construction cost and per-query cost are recorded separately with component timings. Reports
are Polars frames. Stage code manifests validate reuse as described in D6a; the run identity is
computed from data and configuration before sources are read. The operational contract is
[`../benchmarking.md`](../benchmarking.md).

Hold the embedder fixed across pipeline comparisons. Every results table carries EM, token-F1,
Contain-Acc, Judge-Acc, R@2, R@5 and indexing cost, with closed-book, BM25-only and oracle-passage
baselines. The judge comes from a different model family than each reader under test; record
its A/A win rate. For the no-gold path, use BenchmarkQED AutoE's head-to-head protocol. The
[benchmarking contract](../benchmarking.md) defines run identity and reporting; earlier dataset
and model comparisons are in the [research snapshots](../notes/research-snapshots.md).

The "auto-benchmark for your corpus" is the same runner plus BenchmarkQED-style question synthesis
for corpora without gold answers; that arrives with the temporal+ACL synthetic benchmark.

*Replicates.* An experiment is a configuration, a root seed and a replicate
count, default one. Replicate `r` runs under `derive(root, r)`; a stage draws from a seed derived
from that and its name, so stages perturb only themselves. Adapters declare whether the seed
changes their answer (LLMs yes, embedders and rerankers no by default); the derived seed enters
a seed-sensitive adapter's request and cache key, and a stage taking such an adapter reruns per
replicate while everything else is fetched. Every replicate is a run; replicate 0 is the run a
plain command reports. The variance report joins the replicates' stages by structural key and
classifies each from the recorded content hashes: inputs agreeing and outputs differing *adds*
variance, inputs differing and outputs agreeing *absorbs* it; with the metric spread underneath.
It measures variance under the declared seed policy, not all execution variance.

### D9. Repository and DX

Development and smoke runs on a laptop, full runs and local models on a GPU workstation. Nothing
assumes a machine; local-model adapters pick CUDA, MPS or CPU and record it in the spec. Runs are
not compared across machines and caches are not shared.


Cargo workspace under `crates/` (Polars layout: `[workspace.package]`, feature-flagged umbrella
crate, separate bindings crate). Python under `src/triplum/`, maturin mixed layout, uv. marimo
notebooks (plain `.py`, git-diffable) over the same package; Rust exploration stays in cargo examples
and tests. pytest and cargo test; one integration test per pipeline on a 20-question fixture.

Human-facing CLI discovery is a priority: exact matches first, unique prefixes accepted,
single fuzzy matches accepted with a notice; ambiguous/missing finite choices offered
interactively on terminals. All interaction
uses stderr; unresolved selectors with --no-input or nonterminal use yield actionable
usage errors. Library identities
and opaque values stay exact. Contract: `docs/specs/cli-selection.md`.
Tests use focused helpers and real workflow fixtures. Report durations by default and branch
coverage explicitly in CI/on demand; mark real-model tests so the offline suite remains fast.
`uv run ty check` is required across source and tests; `cargo check` checks the Rust workspace.
Native exports carry matching Python stubs. Optional model dependencies stay optional in the
lean check, with a second CI check against installed local-model dependencies. Fix contracts
instead of excluding modules or using broad diagnostic suppressions.
Pre-commit exports the Git index and runs Cargo, ty and Ruff against that snapshot, preserving
unstaged and untracked work. Ruff formatting is checked without rewriting files during commit.

The benchmark assembly layer assumes SQLite; that seam is extended when a second backend
arrives, not before. Implementation state lives in `docs/flow.md` and `docs/api/index.md`, not
here.

*Documentation and API surface.* The reference is FastAPI's documentation:
a tutorial of one concept per page, each page built around one runnable example file that a
test executes against the committed fixtures, so an example that rots fails CI; a curated
top-level namespace (`triplum` and each package `__init__`) that exports the names the tutorial
uses and hides the module layout; a reference generated from the code, where only the
documented public surface is rendered and a docstring is the decision to make a symbol public,
not a coverage count. Research notes keep their dense, decision-record form. Sequenced after
the extraction baseline, caching and run monitoring are functional end to end.

### D10. Name

`triplum`. The original naming survey is in the
[research snapshots](../notes/research-snapshots.md).

## Research sequence

The [foundation stack walk](../plans/stack-walk.md) is the current work order.
After its interfaces settle, the first comparisons are graph retrieval against matched
non-graph baselines, KG-construction variants against the non-LLM extractor, SQLite against
Neo4j, and an embedding sweep with the embedder held fixed across pipeline comparisons.
Small temporal and ACL fixtures gate graph retrieval on zero leakage. Later work covers
additional backends, private corpora and non-QA applications. Each comparison gets a spec and
plan at its own design gate; the [research notes](README.md) hold candidate evidence.

## Review record

This is the outcome ledger, not a second design narrative. The earlier review details and
falsification probes are recoverable through the commits in the
[temporary foundation note](../notes/previous-foundation.md). Binding decisions are in D1–D10
above and the active contracts they link.

| Gate | Peer | Outcome |
|---|---|---|
| Initial architecture | Codex, GPT family | **Changed decisions:** proposition/assertion/support identities, viewer-relative invalidation, derived visibility, full-request cache keys, and viewer-projected graph kernels. **Rejected:** an unmeasured SQLite conversion bottleneck claim. |
| Harness implementation | Codex, GPT family | **Found unique defects**, fixed with tests: ACL/index updates, visibility before top-k, cache key scope, gold mapping, run identity, judge/cost accounting, and deterministic ranking. |
| Dataset/loader redesign | Claude Opus 5 | **Added verification** for atomic ingestion, ACL, and global resolution; **rejected** eager-only and batch-dependent identity proposals. |
| Dataset identity and built-in sources | Codex, GPT family; fresh-context GPT-family fallback | **Changed decisions** on versioned source fingerprints and source-specific ids; **found unique defects**, fixed with tests, in collators, frame hashing, fixtures, and gold checks. |
| Extraction baseline | Codex, GPT family | **Found unique defects**, fixed with tests, in graph visibility, provenance, history, scoring, and resolver idempotence; **changed** graph identity to cover extraction plus resolution. |
| CLI selection | Claude Opus 5; fresh-context GPT-family fallback | **Changed** non-interactive handling and single fuzzy-match policy; **added verification** for missing and ambiguous selections. A final Claude diff review failed authentication and had no decision impact. |
| Typing and hooks | Claude Opus 5; fresh-context GPT-family review | **Changed** optional-model type-check placement; **added verification** for snapshot isolation and whole-project checks; **rejected** replacing the requested `uvx` hook. |
| Stage contract and implementation | Codex, GPT family | **Changed decisions** on execution keys, stream lifetime, store effects, and artifact publication; **found unique defects**, fixed with tests, in manifest validation, empty streams, and judge identity. |
| Foundation layout and documentation | Fresh-context GPT-6 fallback; cross-model CLI unavailable | **Added verification** for package builds and preservation of live requirements. **Found unique documentation defects** in D8's code-identity wording, the premature R10 completion claim, and `graph_identity`'s ineffective pre-run identity slot; the docs now state the actual behavior and track the remaining decision. |
| Benchmark source replay and corpus variants | Claude Opus 5.5 | **Found unique defect:** a one-shot source produced an empty cold run under an unchanged fingerprint. **Changed decision:** seeded corpus variants belong in fingerprinted sources so each variant gets a separate store; replicate seeds vary pipeline stages only. A process-wide content guard was rejected as extra mutable state that cannot prove replay across processes. |
| First distractor variant | Fresh-context GPT-6 fallback; Claude Opus 5.5 CLI safeguard error | **Changed decision:** reuse the eager fixture selector inside a lazy fingerprinted source, so identity remains available before data is read. The peer found that calling the fixture selector at construction would forfeit identity-before-read. A fresh-context GPT-6 diff review **added verification** for non-integer counts and distinct selected chunks, and fixed guide ordering. |
| Lazy stream execution | Claude Opus 5.5 | **Found unique defect:** a streamed stage used its consumer's seed or zero when pulled, then cached that result under the producer's seed key. The fix scopes the producer seed and code recording to each pull; a separate local review found unrelated code entering the manifest while a stream was idle. A diff review **added verification** for later-pull helpers and failure cleanup, and identified per-item monitoring cost. Existing seeded stream artifacts made before this correction are not invalidated by a wrapper-only change; no current production stream stage reads `stage_seed()`. |
