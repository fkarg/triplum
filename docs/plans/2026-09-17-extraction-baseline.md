# Plan: extraction baseline

Snapshot 2026-09-17. Derived from
[`../specs/2026-09-17-extraction-baseline.md`](../specs/2026-09-17-extraction-baseline.md);
the spec says what, this says in which order and where. Each step is one commit that leaves
the suite, `ty`, ruff, cargo and the strict docs build green.

## Shape

```
triplum/extract/
  protocol.py   ExtractorSpec, ResolverSpec, Extractor protocol, Extraction, the span and
                claim frame schemas
  stages.py     extract(chunks, documents, extractor, recorded_at) and
                resolve(extraction, resolver, recorded_at): the D2 frame builders shared by
                every extractor
  rules.py      spaCy dependency rules -> spans and claims
  small_model.py GLiNER spans + GLiREL relations -> spans and claims (closed vocabularies)
  resolvers.py  exact, fuzzy -> same_as facts; canonical_id union
  cached.py     CachedExtractor: per-chunk disk cache keyed on (spec, chunk text)
triplum/eval/triples.py    exact and partial one-to-one scoring, span P/R/F1, counts
triplum/store               put_graph, facts, mentions, neighbours, graph identity binding
triplum/bench               ExtractConfig, run_extraction, ensure_graph, runs.kind,
                            extraction_runs, `triplum bench extract`, report/show for kind
```

An extractor's only job is to turn chunks into a **spans** frame (chunk, offsets, surface,
label, kind entity or literal, datatype, parsed value) and a **claims** frame (chunk, sentence
span, subject span, predicate, object span, status, reason). `stages.extract` does the rest
identically for every extractor: document-scoped entity ids, mentions, label and type facts,
one fact plus one single-chunk support group per accepted claim. That is the seam the LLM
extractors of 2b plug into.

## Steps

1. **Nullable confidence.** `schema.rs` and `migrations.sql`: `facts.confidence` and
   `mentions.confidence` nullable; store migration rebuilds the still-empty graph tables in
   stores created under schema 1 and bumps `schema_version` to 2. Test: an old store opens and
   accepts a null-confidence fact.
2. **Extract package, rules extractor.** `protocol`, `stages`, `rules`, `cached`; extra
   `extract`; ty override; licence rows; unit tests per rule, literal typing, negation and
   modality, subordinate exclusion, determinism across `recorded_at`.
3. **Resolvers.** `exact`, `fuzzy`; `same_as` facts with two-chunk support; `canonical_id`
   union; tests on a synthetic mention table.
4. **Store graph side.** Protocol methods, SQL visibility per D4, `put_graph` rejections,
   graph identity meta; two-principal visibility fixture test.
5. **Metrics.** `eval.triples`: normalisation, exact, partial (CaRB-style, greedy one-to-one
   by descending slot score; optimal assignment is a later refinement noted in the docstring),
   span scores from document metadata entities, counts; tests on hand-built cases including
   the `work_for`/`work_against` non-match.
6. **Bench.** `questions_hash` covers triples (every stored QA identity changes once; the
   fixtures are cheap to rerun); `ExtractConfig`, `run_extraction`, `ensure_graph`, run store
   `kind` column with the QA-only columns made nullable by a `runs` rebuild, `extraction_runs`
   table; fingerprint `EXTRACT` module list; `triplum bench extract`; report and show render
   extraction rows. Integration test over every extraction fixture: metrics non-zero, same
   output hash twice, `ensure_graph` skips on rerun, identity lookup returns the run.
7. **small_model extractor.** Extra `extract-models`, vocabularies from the dataset (entity
   types from document metadata, relations from gold predicates) or from the config; refuses
   without a relation vocabulary; `model`-marked tests; licence rows.
8. **Docs and numbers.** `flow.md` extraction section and the baseline table for both
   extractors on CaRB, CoNLL04, SciERC, GenWiki, GraphJudge and 2Wiki evidences; `api/index.md`
   rows; `api/extract.md`; nav; README status line.

## Deviations from the spec

Recorded here as they happen.

- Step 2: `resolve` takes the chunks frame as well (`resolve(extraction, chunks, resolver,
  recorded_at)`), because an entity's document is only reachable through its mention chunks
  and the spec's signature had no way to tell two documents apart.
- Step 5: the partial matcher compares tokens up to inflection (prefix with at least four
  shared characters, at most three extra) instead of stemming, and the predicate slot must
  exceed 0.5 while the argument slots need at least 0.5; with three-way "at least 0.5" the
  peer's `work for` / `work against` pair matched. `exact` normalises strings only.
- Step 5: one-to-one assignment is greedy by descending slot score, not optimal.
- Step 6: the exact and partial scores are computed for every extractor on every gold set;
  the spec's "unavailable" typed score for `rules` on CoNLL04 and SciERC is a different
  measure (schema-conformant relation F1) that nothing reports yet. The rules rows on those
  sets are labelled a floor in `flow.md`.
- Steps 3 and 4 are one fingerprinted call, `extract.stages.build`, after the diff review found
  the composition outside the graph identity (review record in the spec). Exact
  matching is unaffected (ties are exact duplicates, which count once); partial can differ
  from the Hungarian optimum by at most the assignments a greedy choice forecloses.
