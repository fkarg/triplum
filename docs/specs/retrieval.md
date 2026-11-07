# BM25 retrieval and recall scoring (draft for owner review)

Status: **draft**, not approved. Two separately approvable declarations: P8 (retrieval hit,
Retriever Protocol, BM25) and P9 (recall scorers, `WholeText` chunker, first BM25 R@2/R@5
example). Settled by the owner: RT1/RT2 (hit record, `(query, /, *, viewer, k)`), RT3/RT6 (store-owned
access, [source access](source-access.md)), RT4 (bm25s, presets; RT5's default is reopened
by new evidence), BE3/BE4 (span coverage, native granularity), the policy that established
baselines are named, tunable presets. Open: RT7, RT8 and BE12 in [retrieval](../plans/questions/retrieval.md)
and [benchmark evidence](../plans/questions/benchmark-evidence.md).

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


@dataclass(frozen=True)
class BM25Settings:
    """Tokenization and scoring of one BM25 configuration; every field can be changed."""

    k1: float
    b: float
    method: Literal["lucene", "robertson", "atire", "bm25l", "bm25+"] = "lucene"
    token_pattern: str = r"\w+"  # regex whose matches are tokens; keeps one-character tokens
    lowercase: bool = True
    # drop a trailing 's before splitting (ES english_possessive_stemmer)
    strip_possessive: bool = False
    stopwords: frozenset[str] = frozenset()
    stemmer: Literal["porter", "english"] | None = None  # PyStemmer algorithm: Porter or Porter2


HIPPORAG1 = BM25Settings(k1=1.2, b=0.75)  # ES `standard` analyzer on title\ntext, as HippoRAG 1
IRCOT = BM25Settings(  # ES `english` analyzer, one field (IRCoT sums separate title/text fields)
    k1=1.2, b=0.75, strip_possessive=True, stopwords=LUCENE_ENGLISH_STOPWORDS, stemmer="porter"
)
BM25S_DEFAULT = BM25Settings(k1=1.5, b=0.75, token_pattern=r"(?u)\b\w\w+\b")  # bm25s defaults
# Which preset is the default: RT5 (reopened). LUCENE_ENGLISH_STOPWORDS: Lucene's 33-word set.


class BM25(Retriever, FingerprintedComputationMixin):
    """Lexical retrieval over a snapshot of a store's chunks, with bm25s.

    Indexes the current chunks of every source `viewer` may read at construction; those chunks
    are the term-statistics scope. Each call ranks only the chunks of sources its own viewer may
    read.
    """

    def __init__(
        self, store: RecordStore, /, *, viewer: Viewer, settings: BM25Settings = HIPPORAG1
    ) -> None: ...  # default pending RT5

    def fingerprint_config(self) -> dict[str, object]: ...  # settings only

    def __call__(self, query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]: ...
```

Guarantees:

- **Snapshot.** The index holds the chunks read at construction. Later sources, chunk
  replacements or grants do not reach it; build a new `BM25`. (No revoke operation exists, so a
  snapshot cannot keep a source readable after its access was withdrawn.)
- **Mask before ranking.** A call ranks only chunks whose source is in
  `{s.id for s in store.sources(viewer=viewer)}`, computed once per distinct principal set and
  kept with the snapshot. Hidden chunks are never returned, never fill a top-k slot and never
  break a tie. The query viewer may see sources the index does not hold; they are not returned.
- **Term statistics** (document frequencies, average length) come from the indexed set, not from
  the query viewer's projection. With global statistics, a visible chunk's score depends on
  hidden texts: scores leak term statistics of hidden sources (Elasticsearch document-level
  security behaves the same). See RT7.
- Only chunks sharing at least one query token are hits, so fewer than `k` hits is normal; a
  query with no indexable token returns `[]`. Matching is decided by tokens, not by score sign:
  the `robertson` idf is negative for terms in most documents. `k < 1` raises `ValueError`.
- Order: score descending, ties by `(chunk.source_id, chunk.ordinal)`. The index order is sorted
  the same way, so results do not depend on store iteration order.
- Indexed text is `chunk.text`. Fixture texts begin with `title\n`, so titles are indexed as
  text, as in HippoRAG's passage format; there is no separate title field.
- Fingerprint covers `settings` only. The indexed content's identity belongs to run identity
  (BE6) and the separate-index-run question (BE17).
- Construction reads everything into memory; no persistence of the index yet. An empty
  index (no visible chunks) is allowed and returns `[]`.
- Tokenization is ours, not `bm25s.tokenize`: lowercase, optional possessive strip, regex
  matches, stopword removal, optional PyStemmer stem; the same function for chunks and queries.
  bm25s scores token lists (exact `lucene` formula, observed). Ranking is ours too: full score
  vector, keep visible matching rows, stable sort. bm25s's `weight_mask` only zeroes masked scores
  (masked documents can still be returned at score 0, observed), and its top-k tie order changes
  when jax is installed; neither is relied on.
- Presets approximate Elasticsearch, they do not reproduce it: no UAX#29 tokenizer (`U.S.`,
  `3.14`, `don't` split), PyStemmer's Porter is the 1980 algorithm while Lucene uses Porter's
  release-3 code (a few stems differ), Lucene stores document lengths in one lossy byte, and
  IRCoT's two-field title/text scoring is not available (chunks have no title field). Expect
  small score differences and occasional rank swaps against published numbers.

Example:

```python
store.add_sources(fixture.corpus(collection.id), allow=["public"])
public = Viewer(principals=frozenset({"public"}))
retriever = BM25(store, viewer=public)
hits = retriever(question.input.text, viewer=public, k=5)
[h.chunk.origin for h in hits]  # legacy document ids, best first
```

Dependencies: `bm25s` 0.3.16 (MIT; numpy only, no extras) and `PyStemmer` 3.1.0 (MIT/BSD), recorded
in `docs/licences.md`.

## P9: recall scorers and the first BM25 example

### `src/triplum/evaluation/recall.py`

```python
class RetrievalScorer(Protocol):
    """Score one question's ranked hits against its gold evidence; None when it has none."""

    @abstractmethod
    def __call__(
        self, hits: list[RetrievalHit], evidence: list[list[Evidence]], /
    ) -> float | None: ...


class SpanRecall(RetrievalScorer, FingerprintedComputationMixin):
    """Fraction of gold units the top `k` hits cover completely; best alternative set.

    A `SpanEvidence` unit is covered when the union of the top-`k` chunks of its source covers
    `[start, end)`; a `DocumentEvidence` unit when any top-`k` chunk is from its source.
    """

    def __init__(self, *, k: int, sources: Mapping[str, UUID]) -> None: ...


class AllGoldRecall(RetrievalScorer, FingerprintedComputationMixin):
    """1.0 when some alternative set is covered completely by the top `k` hits, else 0.0."""

    def __init__(self, *, k: int, sources: Mapping[str, UUID]) -> None: ...


def retrieved_characters(hits: list[RetrievalHit], /, *, k: int) -> int:
    """Characters of text in the top `k` hits."""


class RecallSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    mean: float | None  # None when no question is eligible
    eligible: int
    excluded: int  # questions without gold


def summarize(scores: Iterable[float | None], /, *, missing_as_zero: bool = False) -> RecallSummary:
    """Mean over questions with gold; `missing_as_zero` scores questions without gold as 0."""
```

Guarantees:

- `sources` maps each evidence key (`Evidence.document`, a native key) to the Source id it names:
  `{s.external_id: s.id for s in corpus if s.external_id is not None}`. A key missing from it
  raises `KeyError`: a mapping error, never a silent zero.
- Hits beyond `k` are ignored; fewer than `k` hits are scored as they are. `k < 1` raises.
- Per set: the fraction of its units covered (equal weight per unit). Per question: the best set.
  No evidence (`[]`) returns `None`.
- Coverage uses `chunk.source_id` and `[chunk.start, chunk.start + len(chunk.text))`; it does not
  read the store and does not compare texts.
- With one chunk per whole source and whole-document gold, `SpanRecall` equals HippoRAG's
  passage-set R@k and `AllGoldRecall` its AR@k.
- Not included yet: the named variants of BE3 (document/title recall, answer-in-context,
  MultiHop-RAG fact hits, character coverage/IoU), per-question records (BE16), repeats and
  intervals (BE15).

### `WholeText` chunker (`src/triplum/steps/chunking.py`)

```python
class WholeText(Chunker, FingerprintedComputationMixin):
    """One chunk holding the whole source text; empty text yields no chunks."""
```

Needed so chunks equal the native passages of the fixtures, as HippoRAG's R@k assumes.

### Example: `examples/bm25_recall.py`

Loads `tests/fixtures/hotpotqa.json`, stores the corpus in a `MemoryStore` with `allow=["public"]`,
chunks with `WholeText`, builds `BM25` with the default preset, retrieves `k=5` per question with
the public viewer, and prints R@2, R@5, AR@2, AR@5 and mean retrieved characters. No API key, no
network, no cache.

## Verification plan

- P8: hidden top-scoring chunk never returned and never displaces a visible one (the round-7
  forbidden-outranks-visible case), with two viewers over one index; ties ordered by
  `(source_id, ordinal)` independent of insertion order; zero-score and no-term queries; `k`
  larger than the visible set; snapshot ignores later writes; memory and SQL stores; preset values
  pinned against their published sources; tokenizer cases for RT8.
- P9: partial coverage by two adjacent chunks; a one-character gap scores 0; chunks of another
  source with overlapping offsets do not count; document evidence; best of two sets; `[]` → None;
  unknown key raises; `summarize` counts and `missing_as_zero`; the example runs as a test on the
  20-question fixture, with its numbers recorded.
- Docs: concept pages for retrieval and recall (one each), flow.md, licences.md.

## Unresolved tradeoffs

- RT7: where the index gets its chunks, access and term-statistics scope.
- RT5 (reopened): the round-6 premise that HippoRAG 1 used the ES `english` analyzer was wrong;
  which preset is the default.
- RT8: own tokenizer versus `bm25s.tokenize`, and how presets document their fidelity.
- BE12: scorer interface shape; location `evaluation/` (a new package) versus elsewhere.
