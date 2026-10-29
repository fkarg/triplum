# Interface map (draft, not approved)

Working frame for BE14: the benchmark run lifecycle and every interface it needs. Names marked
**exists** are implemented; everything else is a proposal under the review gate in AGENTS.md.
Questions live in [benchmark evidence](questions/benchmark-evidence.md) and
[retrieval](questions/retrieval.md).

## Lifecycle

```text
Corpus dataset ─► Converter* ─► Source* ─► Chunker* ─► [EmbeddingText* ─► Embedder*] ─► index/store
                                                                          (indexing cost)
QA dataset ─► QAQuestion ─► Query (question, choices, context)        gold stays outside
  per question × repeat(seed):
    Query ─► Retriever(viewer) ─► list[Hit] ─► [Fuser] ─► [Reranker] ─► EvidenceFormatter
          ─► LLM request ─► LLM ─► Answer (text, cited hits, usage)
  per sample:   Normaliser steps ─► AnswerScorer {EM, F1, Contain, Judge}
                RetrievalScorer {span-coverage R@k, variants} (hits, gold, key→Source binding)
  across repeats: Reducer      across samples: Aggregator (mean, interval)
  ─► SampleRecord / RunRecord ─► report / compare
```
`*` exists today (prototypes for indexing remain under review).

Three trust zones, composed by an ordinary run function: preparation (load, validate bindings,
prepare Sources and indexes), public execution (sees only the public question projection, Viewer and
seed) and privileged evaluation (holds gold). The public projection excludes answers, evidence,
answerability and free metadata. The oracle baseline is a privileged selector that receives
evidence and feeds the ordinary answering path; it is not a Retriever. Cache bypass must hold for
every nested component, not only a top-level flag.

## Inventory

| Interface | Input → output | Baseline need |
| --- | --- | --- |
| QAQuestion, Evidence (records) | see BE1 | now |
| QuestionInput (record) | question, choices, context keys, as_of | now |
| Viewer (record) | principals, as-of | now (trivial public/now) |
| RetrievalHit (record) | chunk + optional score; order is rank | now |
| Retriever | (question input, viewer) → list[RetrievalHit]; k configured | now: BM25 |
| OracleSelector | (evidence, viewer) → list[RetrievalHit] | now: oracle baseline |
| QAPipeline | (public input, viewer, seed) → Prediction | now |
| EvidenceFormatter | (query, hits) → LLM request + citation labels | now; empty hits = closed-book |
| LLM | request → response (text, usage) | now; one protocol, full request = cache key |
| Answerer | (query, hits) → Answer | now; formatter + LLM + citation parsing |
| Normaliser | str → str | now |
| AnswerScorer | (prediction, question) → float or None | now |
| RetrievalScorer | (hits, question, binding) → float or None | now |
| Score (record), Scorer | one metric for one sample; value or explicit exclusion | now |
| RepeatReducer | one question's scores across repeats → score | once repeats exist |
| Aggregator | scores across questions → MetricSummary (eligible, excluded, failed) | now |
| SampleResult, RunSpec, RunResult, Usage, StageError | per-attempt results, manifest, usage by stage/role | now |
| Fuser | list[list[Hit]] → list[Hit] | later (fusion baseline) |
| Reranker | (query, hits) → list[Hit] | later |
| QueryTransform | query → query(s) | later |
| Refiner | (query, hits) → hits, spans preserved | later |
| Graph retriever | same Retriever protocol, hits traceable to spans | later |

## Known risks from comparable frameworks

Scores written onto shared records; refiners returning bare strings (lost provenance); retrieval
caches inside retrievers (conflicts with cache-free benchmarks); global configuration hidden from
run identity; metrics that raise silently dropped.
