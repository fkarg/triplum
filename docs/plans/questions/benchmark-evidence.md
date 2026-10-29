# Benchmark inputs, evidence and measurement

Questions use the `BE` prefix. Process: [questions index](README.md).

## Open

### BE14. Benchmark run lifecycle and interface map

From owner round 2: identify the full lifecycle and every interface for indexing, retrieval and
evaluation before fixing BE10 and RT shapes. Research running.

Related: [Q7](ingress-identity.md#q7-representing-gold-evidence-in-benchmarks) (span-based gold,
counting deferred) is answered in part there; BE3 completes it. Round 1 peer: gpt-6.1-sol,
review `2640da6f0f5e4b719ecf322f046db963`.

### BE1. QA input representation

Owner (round 1, partial): direction (b) as a `QABenchmarkDataset`-like interface that the
benchmarks share after small molding. Follow-up research and questions; keep it simple.

No question type exists. Legacy fixtures bundle documents, questions and triples in one file.
AGENTS.md: corpus and QA inputs compose separately; no universal benchmark-task schema.

- (a) Restore the legacy combined schema.
- (b) One plain Pydantic QA record (question, accepted answers, optional gold evidence,
  answerability, metadata); a separately fingerprinted `Dataset` of them, paired explicitly with a
  corpus `Dataset[Source]`.
- (c) No shared record; each evaluator adapts dataset-specific records.

Claude: (b). Peer: (b), plus answerability true/false/unknown, unannotated evidence distinct from
explicitly empty evidence (neither scores as perfect recall), page-level evidence as a separate form,
and an external sample key for cross-run correspondence.

### BE2. How gold evidence identifies its document

Owner asked for the state of deterministic ids first. Finding: UUIDv8 ids were designed (Chunk
layout agreed 2026-10-07) but never implemented; Source layout, hash inputs and collection-id
generation remain open (Q12/Q13). To be re-presented.

Source ids are random per run; deterministic ids (Q12) are open. The owner's goals now require
each source to carry provenance to its original document.

- (a) Current Source UUIDs in gold. Unstable across runs.
- (b) Deterministic Source ids (Q12 first).
- (c) A dataset document key in gold, resolved to the run's actual Sources through `Source.origin`,
  validated unique within the corpus.
- (d) As (c), but a dedicated key kept separate from origin, with a run-local key→Source binding.

Claude: (c). Peer: (d); origin is not guaranteed unique, so do not assume it. Both: a missing or
ambiguous key or changed prepared text (checked by digest) is an input error, not a retrieval miss.
**Divergence:** reuse origin with validation versus a separate key.

### Round 2 (peer gpt-6.1-sol, review `927468a2a2c442bc986e7f8d0ecb52f2`)

Presented in chat; options and dispositions in the
[capture](../../brainstorms/2026-10-12-benchmark-baseline.md). BE1 declaration draft, BE2
origin-vs-key, BE3 default profile and variants, BE10 answer scorer Protocol, BE11 per-question
context keys.

### BE10. Answer-scoring interface

Owner (round 2): reopened. Eval is likely a hierarchical pipeline whose steps (normalisation etc.)
are blocks; establish the lifecycle and surrounding constraints first (BE14).

Separate callables per metric (EM, F1, containment, judge) with a pluggable normaliser and named
academic profiles. Claude and peer agree; see round 2.

### BE11. Per-question contexts (distractor settings)

Owner (round 2): deferred. Ideas: specific collection filters; a dataset spawning several
collections; the 10–20 passage setting may be a (re)ranking evaluation.

Claude originally: one dataset per setting. Peer: optional per-question eligible document keys,
enforced before ranking; pooling is a separately recorded setting. Claude revised to the peer.

### BE3. Evidence recall counting

Owner (round 1, partial): direction (b), configurable; research how most papers count first.

Gold spans and chunks have arbitrary boundaries. Owner wants full or mostly-full span retrieval.

- (a) Any overlap counts. A one-character sliver satisfies a paragraph.
- (b) Union of top-k same-document chunks must cover the span completely (τ = 1).
- (c) Union coverage at least τ < 1; needs a number.
- (d) Proportional: each span contributes its covered fraction.

Claude originally: (d) primary. Peer: (b) primary, with (d) and all-evidence recall (every span
complete) alongside; equal weight per span; duplicate chunks still use ranks; report retrieved
characters, because one huge chunk trivially covers small spans. **Claude revised to the peer's
position.** Cost: a one-character gap scores 0 strict, 0.99 proportional.

### BE4. Gold granularity and fixture provenance

Every legacy gold id decodes to a whole paragraph. Native annotations differ: HotpotQA/2Wiki
sentences, MuSiQue paragraphs, MultiHop-RAG fact strings, FRAMES page URLs. HippoRAG reports
passage-level R@k.

- (a) Paragraph everywhere: comparable to HippoRAG; discards finer annotation; pages cannot convert.
- (b) Minimal fact spans everywhere: needs new annotation.
- (c) Native granularity in common span coordinates; page-only evidence scored separately.

Claude: (a). Peer: (c). **Divergence.** Both: convert the legacy fixtures mechanically to paragraph
spans now; full datasets come from new loaders with conversion provenance recorded.

### BE5. Answer normalization and containment

Published Contain-Acc is a character-substring test, so "no" matches inside "not".

- (a) Reproduce published scoring, substring containment included.
- (b) SQuAD normalization, max over aliases, contiguous-token containment, strict yes/no.
- (c) Dataset-native scoring everywhere.

Claude: (b). Peer: (b) as the common profile, plus a labelled dataset-native profile for paper
reproductions; empty-after-normalization answers need explicit handling.


## Answered

### BE3 (answered). Evidence recall counting

Owner accepted the round-2 proposal: union of top-k same-document chunks must fully cover each gold
unit (page/document evidence: correct page/document), mean per question, k = 2 and 5, plus all-gold
recall and retrieved characters. Separately named variants: HippoRAG passage identity, document/title
recall, answer-in-context, MultiHop-RAG fact hits, character coverage/IoU. No-gold questions are
excluded and counted by default, with a zero-counting option. Alternative evidence sets take the best.

### BE4 (answered). Gold granularity

Owner: use each dataset's native granularity and record how it is offered. For page-only
provenance, citing the correct page counts as correct; finer provenance is scored more strictly.
Research further. Agent-assisted answer-correctness evaluation (RAGAS-style) comes later.

### BE5 (answered by policy). Answer normalization and containment

Owner: evaluation choices are options behind interfaces; commonly used academic variants must be
available. Interface design follows as a new question.
