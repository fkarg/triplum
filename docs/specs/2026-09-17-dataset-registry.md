# Dataset registry

Snapshot 2026-09-17. Follows the [benchmark catalogue](../research/benchmarks-catalogue.md) and
the [dataset status](2026-09-16-dataset-status.md) spec.

## Goal

Offer every benchmark in the catalogue's ranked shortlist, and the standard QA, KGQA and
entity-linking sets the follow-up research adds, as auto-fetchable datasets: exact URLs, pinned
SHA-256 per file, one loader each into the canonical frames, a committed smoke fixture, a licence
row. The HippoRAG three stay the default protocol. Nothing new runs by default; everything new is
one `--dataset` away.

## Behaviour

- `triplum data` lists every registered dataset with family, whether it belongs to the default
  protocol, whether it is large, and the local state generalised to n files (`not downloaded`,
  `partial`, `verified`, `invalid`).
- `triplum data fetch --dataset <name>|default|all`. A bare `fetch` means `default`, the protocol
  three, as before. `all` fetches every dataset whose pinned download total is at or under
  300 MB and says which large ones it skipped; a large dataset downloads only when named, and
  naming it in `bench run --dataset` counts as naming it.
- `triplum bench run --dataset <name>` accepts any registered dataset that has questions and no
  declared missing runner capability. An extraction-only dataset (gold triples, no questions) is
  refused. A dataset whose `needs` names a capability the runner lacks (a viewer per question, a
  temporal query) is refused with that capability, before any model is built. A dataset without
  a corpus refuses every pipeline except `closed_book`.
- Retrieval recall is defined per question: `r2`/`r5` are null when the question has no gold
  chunk (corpus-less dataset, or an unanswerable question that has no supporting passage), and
  the run's mean is over the questions that have one. A gold passage the loader cannot map is
  still an error, never a null.
- Questions marked unanswerable keep the dataset's own abstain string as `answer` and set
  `answerable = false`. Scoring abstention (over-refusal, abstain accuracy) is a later metrics
  spec; the loader only preserves the label.
- Time columns hold real instants only. `documents.observed_at` is set when the source gives a
  date (ECT-QA call dates, LongMemEval session dates), otherwise 0; an ordinal ingestion order
  (old/base/new, an edit sequence) is kept in `documents.metadata`, never turned into a fake
  timestamp. `questions.as_of` is the valid-time instant a question asks about, when the source
  gives one; anything else temporal stays in `questions.metadata`.
- Gold triples (2Wiki `evidences`, GraphJudge, GenWiki, CaRB, CoNLL04, SciERC) land in a
  `triples` frame keyed by document and, where it exists, question. Extra annotations that are
  document-scoped (typed spans, coreference clusters) go into `documents.metadata`. Triple recall
  is a later metric.
- Anything question-scoped that no column holds (decompositions, per-hop answers, candidate
  distractor ids, viewer principals, SPARQL, entity ids) is kept as JSON in `questions.metadata`
  rather than dropped, so a later metric does not need a loader change.

## Registry model

```python
File(url, name, sha256, bytes)  # name is the path under the data root
Spec(name, family, files, licence, parse, default, fixture, needs)
Dataset(name, questions, documents, grants, chunks, triples, corpus_hash, questions_hash)
```

- `questions` gains `answerable: Boolean`, `as_of: Int64` (nullable) and `metadata: Utf8` (JSON).
  The other frames keep the D2 columns. `triples` is `(question_id, document_id, subject,
  predicate, object)` with nullable ids.
- Files live at `$TRIPLUM_DATA/<name>`; the HippoRAG three keep `hipporag/<file>` so nothing
  already downloaded moves. Fetch, status and verify are generic over `Spec.files`; the per-dataset
  code is the parser only, `parse(paths, n) -> frames`, grouped one module per source
  (`hipporag.py`, `morehopqa.py`, ...). `large` is derived from the pinned byte total.
- **Identity follows parsed content, not source bytes.** `corpus_hash` is a hash over the
  documents, grants and chunks frames; `questions_hash` over the questions frame. The pinned
  SHA-256 per file is provenance and drift detection for the download; the store file, the run
  identity and the fixture all key on the parsed frames, so a parser correction invalidates a
  stale store instead of reusing it, and fixture and full loads share one definition.
- Fixtures move from raw-format subsets to one canonical `tests/fixtures/<name>.json` holding the
  parsed frames for the first 20 questions plus their gold chunks, their candidate distractors
  from `metadata` where the dataset ships them, and a fill of 40 further chunks sampled with a
  fixed seed (the first 40 chunks for extraction-only datasets). One fixture writer and one
  reader replace per-dataset raw subsetting. Canonical fixtures exercise the runner; parser
  correctness is pinned by synthetic source-shaped records in the parser tests. The six existing
  HippoRAG fixture files are regenerated in the new format; fixture run identities change, which
  is acceptable for smoke runs.

## Boundaries

The registry owns names, files, hashes, licences and the missing-capability note; parsers own
record shapes; the CLI renders and resolves names through the selection policy; the runner
consumes frames and never inspects the source format. Adding a dataset is one `Spec`, one parser,
one fixture, one licence row, and a line in the catalogue.

## Out of scope, named as follow-ups

Shared corpora for the corpus-less control sets (DPR `psgs_w100`, KILT Wikipedia); ingesting a KG
as the source for the KGQA-over-KG sets; abstention and triple-recall metrics; per-hop recall; a
per-question viewer in the runner (GateMem) and temporal queries (ECT-QA as-of), both declared
via `needs` until the runner has them; the store acting on `observed_at`/`as_of`.

## Verification

- Registry integrity test: unique names, every file pinned, every fixture parses into the
  declared schemas, gold chunk ids resolve, non-empty `questions` or `triples`, unanswerable or
  corpus-less questions may have empty gold.
- Per-source parser tests on synthetic records, as `test_datasets.py` does for HippoRAG today.
- Identity tests: a chunk-text or grant change alters `corpus_hash` and not `questions_hash`;
  a question subset alters only `questions_hash`.
- CLI workflow tests: `data` lists all datasets and states without fetching; bare `fetch` takes
  the default three; `fetch all` skips a large dataset and says so; `bench run` refuses
  extraction-only datasets, datasets with a `needs` note, and non-closed-book pipelines on
  corpus-less datasets.
- The integration fixture test runs every pipeline on every fixture that has a corpus and no
  `needs` note.

## Design review

2026-09-17, GPT via `codex` (`peer-review --mode design`), verdict "challenges", with executed
falsifications. **Changed decisions:** corpus and question identity hash the parsed frames rather
than the raw files, which also removed the corpus/question file membership from `File` and the
concatenation ambiguity the peer demonstrated; `large` is derived from pinned bytes instead of a
flag; bare `fetch` means the default protocol; ordinal ingestion order stays in metadata and only
real instants enter `observed_at`/`as_of`; document-scoped extraction annotations live in
`documents.metadata`; a `needs` note makes the runner refuse datasets whose viewer or temporal
semantics it cannot honour, instead of silently running a static evaluation. **Added
verification:** per-question null recall including unanswerable questions on a corpus-bearing
dataset; identity tests above; extraction-only fixture selection is deterministic. **Rejected
with reason:** a separate parsed-corpus identity distinct from `corpus_hash` (one identity over
parsed frames already serves store reuse and run identity; two would need reconciling); a
versioned framed manifest for source hashes (per-file pins plus the parsed-content identity
cover provenance and drift without a manifest format). **No impact:** the peer's counterproposal
otherwise matches the spec (plain registry, per-source parsers, one `Dataset`).
