# BM25 retrieval and recall scoring

Status: **approved** by the owner (P8 and P9, 2026-11-07, "go P8, go P9") after round 8 (RT5 (a),
RT7 (c), RT8, BE12 (b)); implemented: `datatype/hit.py`, `steps/retrieval.py`, `WholeText` in
`steps/chunking.py`, `evaluation/recall.py`, `examples/bm25_recall.py`. Approval covers this page
only. Settled earlier: RT1/RT2 (hit record, `(query, /, *, viewer, k)`), RT3/RT6 ([source
access](source-access.md)), RT4 (bm25s, presets), BE3/BE4 (span coverage, native granularity).
Answers are in [retrieval](../plans/questions/retrieval.md) and
[benchmark evidence](../plans/questions/benchmark-evidence.md).

## P8: hits, Retriever and BM25

### `src/triplum/datatype/hit.py`

```python
class RetrievalHit(BaseModel):
    """One retrieved chunk. A list of hits is ranked: earlier hits rank higher."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float | None  # the producer's score; None where it has none (oracle)
```

Scores are comparable only within one result list. The producer is recorded by the run, not the
hit.

### `src/triplum/steps/retrieval.py`

```python
class Retriever(Protocol):
    """Find the chunks that best answer a query, among those `viewer` may read."""

    @abstractmethod
    def __call__(self, query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]:
        """At most `k` hits, best first; only chunks of sources `viewer` may read."""
        ...


class BM25Settings(FingerprintedDataModel):
    """Tokenization and Lucene BM25 scoring of one configuration; every field can be changed."""

    model_config = ConfigDict(frozen=True)

    k1: float = Field(ge=0)  # bounds keep every matching chunk's score positive
    b: float = Field(ge=0, le=1)
    token_pattern: str = r"\w+"  # whole nonempty matches are tokens, for chunks and queries
    lowercase: bool = True


HIPPORAG1 = BM25Settings(k1=1.2, b=0.75)  # default: ES `standard` analyzer, as HippoRAG 1
BM25S_DEFAULT = BM25Settings(k1=1.5, b=0.75, token_pattern=r"(?u)\b\w\w+\b")  # bm25s defaults


class BM25(Retriever, FingerprintedComputationMixin):
    """Lexical retrieval over a snapshot of a store's chunks, with bm25s.

    Indexes the current chunks of every source `viewer` may read at construction; those chunks
    are the term-statistics scope. Each call ranks only the chunks of sources its own viewer may
    read.
    """

    def __init__(
        self, store: RecordStore, /, *, viewer: Viewer, settings: BM25Settings = HIPPORAG1
    ) -> None: ...

    def fingerprint_config(self) -> dict[str, object]: ...  # settings only

    def __call__(self, query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]: ...
```

Guarantees:

- **Snapshot.** The index holds the chunks read at construction. Later sources, chunk
  replacements or grants do not reach it; build a new `BM25`. (No revoke operation exists, so a
  snapshot cannot keep a source readable after its access was withdrawn.)
- **Mask before ranking.** A call ranks only chunks whose source is in
  `{s.id for s in store.sources(viewer=viewer)}`, read on every call (no memo: the owner's
  simpler-first privacy policy; `sources()` loads texts, a known cost). Hidden chunks are never returned, never fill a top-k slot and never
  break a tie. The query viewer may see sources the index does not hold; they are not returned.
- **Term statistics** (document frequencies, average length) come from the indexed set, not from
  the query viewer's projection. With global statistics, a visible chunk's score depends on
  hidden texts: scores leak term statistics of hidden sources (Elasticsearch document-level
  security behaves the same). RT7 (c): accepted for now; viewer-scoped indexes later.
- Only chunks sharing at least one query token are hits, so fewer than `k` hits is normal; a
  query with no indexed token returns `[]`. Only the `lucene` variant is offered: its idf is
  positive, so sharing a token is the same as scoring above zero (the `robertson` idf can be
  negative; adding variants must keep matching separate from score sign). `k < 1` raises.
- A repeated query token counts again (`cat cat` scores twice `cat`), as Lucene sums repeated
  term clauses.
- Order: score descending, ties by `(chunk.source_id, chunk.ordinal)`. The index order is sorted
  the same way, so results do not depend on store iteration order.
- Indexed text is `chunk.text`. Fixture texts begin with `title\n`, so titles are indexed as
  text, as in HippoRAG's passage format; there is no separate title field.
- Fingerprint covers `settings` only. The indexed content's identity belongs to run identity
  (BE6) and the separate-index-run question (BE17).
- Construction reads everything into memory; no persistence of the index yet. An empty
  index (no visible chunks) is allowed and returns `[]`.
- Tokenization is ours, not `bm25s.tokenize`: optional lowercasing, then regex matches; the same
  for chunks and queries (RT8: part of indexing; stopwords, possessives and stemming later,
  possibly database-level analysis). bm25s scores token lists (exact `lucene` formula, observed).
  Ranking is ours too: full score vector, keep visible matching rows, stable sort. bm25s's `weight_mask` only zeroes masked scores
  (masked documents can still be returned at score 0, observed), and its top-k tie order changes
  when jax is installed; neither is relied on.
- Presets approximate Elasticsearch, they do not reproduce it: no UAX#29 tokenizer (`U.S.`,
  `3.14`, `don't` split) and Lucene stores document lengths in one lossy byte. Expect small score
  differences and occasional rank swaps against published numbers.
- Deferred: an `IRCOT` preset (ES `english`: possessive, Lucene's 33 stopwords, Porter via
  PyStemmer, whose 1980 Porter differs slightly from Lucene's) and IRCoT's two-field title/text
  scoring, which needs a title field chunks do not have.

Example:

```python
store.add_sources(fixture.corpus(collection.id), allow=["public"])
public = Viewer(principals=frozenset({"public"}))
retriever = BM25(store, viewer=public)
hits = retriever(question.input.text, viewer=public, k=5)
[h.chunk.origin for h in hits]  # legacy document ids, best first
```

Dependency: `bm25s` 0.3.16 (MIT; numpy only, no extras), recorded in `docs/licences.md`.

## P9: recall scorers and the first BM25 example

### `src/triplum/evaluation/recall.py`

```python
class ResolvedSpan(BaseModel):  # frozen, extra="forbid"; end > start
    source_id: UUID
    start: int
    end: int


class ResolvedDocument(BaseModel):  # frozen, extra="forbid"
    source_id: UUID


type ResolvedEvidence = ResolvedSpan | ResolvedDocument


def resolve_evidence(
    question: QAQuestion, sources: Mapping[str, UUID], /
) -> list[list[ResolvedEvidence]]: ...


class RecallAtK(BaseModel):  # frozen
    recall: float | None  # best set's fraction of fully covered items; None without gold
    all_gold: bool | None  # some set fully covered; None without gold
    retrieved_characters: int  # distinct source characters in the top k


def score_recall(
    hits: Sequence[RetrievalHit],
    evidence: Sequence[Sequence[ResolvedEvidence]],
    /,
    *,
    ks: Sequence[int] = (2, 5),
) -> dict[int, RecallAtK]: ...


class RecallSummary(BaseModel):  # frozen
    recall: float | None
    all_gold: float | None
    retrieved_characters: float | None  # mean over all questions
    questions: int
    no_gold: int
    denominator: int  # questions in the recall means


def summarize_recall(
    scores: Iterable[RecallAtK], /, *, no_gold: Literal["exclude", "zero"] = "exclude"
) -> RecallSummary: ...  # one k at a time
```

Guarantees:

- Evidence is resolved once, before retrieval: `sources` maps native document keys to Source ids
  of one collection, usually `{s.external_id: s.id for s in corpus if s.external_id is not None}`.
  A missing key raises `KeyError` naming question and key: a preparation error, never a zero.
- For each `k`, the first `k` hits, without reranking or deduplication. A span is covered when
  the union of the top-`k` chunks of its source contains all of `[start, end)`; a document when any
  top-`k` chunk is from its source. Per set: fraction of items covered (equal weight); per
  question: the best set; items of different sets never combine. `[]` evidence → `None`.
- Coverage uses `chunk.source_id` and `[chunk.start, chunk.start + len(chunk.text))`; it reads no
  store and compares no texts.
- Retrieved characters: distinct source characters (owner: overlaps count once), counted also for
  questions without gold. Delivered text, which counts overlaps twice, is a reader cost that
  belongs with LLM usage.
- Summaries: recall means over `denominator` questions; `no_gold="zero"` adds questions without
  gold as 0. Empty denominators give `None`.
- With one chunk per whole source and whole-document gold, `recall` equals HippoRAG's
  passage-set R@k and `all_gold` its AR@k.
- Not included: BE3's named variants (document/title recall, answer-in-context, MultiHop-RAG fact
  hits, character coverage/IoU; BE21 asks about a gold-coverage proportion), per-question run
  records (BE16), repeats and intervals (BE15).

### `WholeText` chunker (`src/triplum/steps/chunking.py`)

```python
class WholeText(Chunker, FingerprintedComputationMixin):
    """One chunk holding the whole source text; empty text yields no chunks."""
```

Needed so chunks equal the native passages of the fixtures, as HippoRAG's R@k assumes.

### Example: `examples/bm25_recall.py`

Takes a fixture path, stores its corpus in a `MemoryStore` with `allow=["public"]`, chunks with
`WholeText`, resolves all evidence, builds `BM25` with the default preset, retrieves `k=5` per
question with the public viewer, and prints R@2, R@5, AR@2, AR@5 and mean retrieved characters.
No API key, network or cache. On `tests/fixtures/hotpotqa.json` (observed, pinned by a test):
R@2 0.600, AR@2 0.300, R@5 0.775, AR@5 0.600, 968 / 2639 characters, 20 of 20 questions with
gold. Not compared against published numbers (20 questions only).

## Verification

`tests/test_retrieval.py` (memory and SQL stores): hidden best match never returned or
displacing visible hits; only the corpus viewer's sources indexed; ties by source id in both
insertion orders and by ordinal within a source; score equals the Lucene formula with the
preset's k1/b; unknown, empty, punctuation-only and case-differing queries; fewer than `k`;
empty and tokenless corpora; `k < 1`; snapshot after writes; presets differ on one-character
tokens; fingerprint follows settings. `tests/test_recall.py`: adjacent, overlapping, gapped,
short and other-source coverage; document evidence; best set without pooling; first `k` only;
distinct characters; no-gold; invalid `k`; resolution and unknown keys; union rejects an invalid
span; summary denominators; the example's output. Mutations (dropping the visibility filter,
not merging adjacent intervals) turn tests red (observed).

## Implementation review

- Cross-model diff review gpt-6.1-sol `d4dc780ad083409db6402a4d09ee3845` (ran both test modules;
  1,140 three-interval combinations against character-set unions; tokenless corpora in both
  orders; capture-group patterns; k1 0 vs negative). Unique defect: capture groups made `findall`
  return groups or tuples (retrieval raised) → whole matches, regression test (red before the fix,
  observed). Defect, also found by the general reviewer: unbounded `k1`/`b` made matching chunks
  score ≤ 0 and vanish → `k1 ≥ 0`, `0 ≤ b ≤ 1` (Lucene's own bounds), test. Nits applied
  (redundant `bool`, default `ks` in the example). No impact: inconsistent hand-built `RecallAtK`.
- General reviewer (no peer call): unique defect, patterns matching the empty string indexed `""`,
  turning non-matching chunks into hits, and `""` in bm25s's vocabulary crashed `get_scores` →
  empty matches skipped, test (red before the fix, observed). Added: example names its
  collection after the fixture and prints `n/a` without gold; `WholeText` fingerprint covered;
  repeated query tokens documented. Docs gap: closed by the docs sync in the same commit.
- Simplicity reviewer: test parametrized by expected result, docstring layout, comment placement,
  private `_store`, clearer `_covered` parameter applied. Not applied: nesting `_covered` inside the
  loop (Ruff B023, loop-variable closure); merging the two interval dicts (readability).
- Security reviewer: no access defects (mask before ranking, ties, construction scope, no
  existence oracle for hidden-only tokens, gold isolation). Confirmed the accepted global
  statistics leak with numbers. Latent: the fingerprint omits index scope, so caching retriever
  calls could serve another store's chunks; nothing caches retrievers today (Open below).

## Open

- BE21: a gold character-coverage proportion alongside strict span recall.
- Viewer-scoped term statistics for private corpora (RT7, deferred by the owner's privacy policy).
- Index persistence, content identity and separate index-build runs (BE6, BE17). Until then,
  retriever calls must not be cached: the fingerprint covers settings, not the indexed chunks,
  construction viewer or store grants (security review).
