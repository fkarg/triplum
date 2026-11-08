# Retrieval

**Retrieval** finds the chunks that best answer a query, among the chunks the reader may see.
A [`Retriever`][triplum.steps.retrieval.Retriever] takes the query text, a
[`Viewer`](../infrastructure/store.md#who-may-read) and a number `k`, and returns at most `k`
[`RetrievalHit`][triplum.datatype.hit.RetrievalHit]s, best first.

The library provides one retriever, [`BM25`][triplum.steps.retrieval.BM25]: lexical search over
the chunks in a [store](../infrastructure/store.md), scored by the
[bm25s](https://github.com/xhluca/bm25s) library with the Lucene BM25 formula.

## Example

```python
from triplum.datatype import Collection, Source, Viewer
from triplum.steps.chunking import WholeText
from triplum.steps.retrieval import BM25
from triplum.store import MemoryStore

collection = Collection(name="Shop policies")
texts = {
    "returns.md": "Returns are accepted within 30 days of purchase.",
    "refunds.md": "Refunds reach your account within 5 days.",
    "shipping.md": "Orders ship within 2 days.",
}
sources = [Source(collection_id=collection.id, origin=o, text=t) for o, t in texts.items()]

store = MemoryStore()
store.add_sources(sources, allow=["public"])
chunker = WholeText()
for source in sources:
    store.replace_chunks(source.id, chunker(source))

public = Viewer(principals=frozenset({"public"}))
retriever = BM25(store, viewer=public)
for hit in retriever("Are returns accepted after 30 days?", viewer=public, k=2):
    print(f"{hit.score:.3f} {hit.chunk.origin}")
```

```text
1.705 returns.md
0.068 shipping.md
```

1. [`WholeText`](chunking.md#whole-text) keeps each source as one chunk, so each policy is one
   retrieval unit.
2. `BM25(store, viewer=public)` reads every chunk `public` may read and indexes them. The
   retriever is configured once; each call takes only the query, the viewer and `k`.
3. The call returns the two best hits. `shipping.md` matches only on `days`, and scores above
   `refunds.md` because it is shorter.

## Hits

A `RetrievalHit` has two fields:

- `chunk`: the retrieved [chunk](chunk.md), with its `source_id`, `start` and `text`.
- `score`: the retriever's score, higher is better. It is `None` for producers that have no
  score, such as an oracle that returns the gold passages.

As for sources and chunks, unknown field names passed to `RetrievalHit` are silently ignored.

A list of hits is ranked: earlier hits rank higher. Scores are comparable only within one result
list, not across queries or retrievers. A hit does not record which retriever produced it; the
run that calls the retriever does.

## The contract

`Retriever` is a Protocol with one method:

```python
def __call__(self, query: str, /, *, viewer: Viewer, k: int) -> list[RetrievalHit]: ...
```

- Input: the query text, the viewer on whose behalf to search, and the maximum number of hits.
- Output: at most `k` hits, best first, only from sources `viewer` may read. The hits are the
  best among what `viewer` may read: filter before choosing the top `k`, not after, so hidden
  chunks never take the places of visible ones.

These rules are all the Protocol requires. Tie order, determinism, what happens for `k`
below 1 and whether the retriever reads a snapshot or the live store are left to each
implementation; the [BM25](#bm25) section states its choices.

Configuration such as the store and the scoring settings belongs in `__init__`, as for the other
[steps](decisions.md#how-the-pieces-fit). How a custom retriever, or the content it indexed,
enters a fingerprint or a run's identity is not defined yet.

## BM25

The rules in this section belong to `BM25`, not to the `Retriever` Protocol.

### Two viewers

`BM25` uses a viewer twice:

- **The corpus viewer**, passed at construction, decides which chunks are indexed: the current
  chunks of every source it may read.
- **The query viewer**, passed on every call, decides which indexed chunks may be returned.
  Each call reads the query viewer's sources from the store and drops every other chunk before
  ranking. A hidden chunk is never returned, never takes a top-`k` slot and never decides a tie.
  Sources the query viewer may read but the index does not hold are not returned either.

```python
from triplum.datatype import Collection, Source, Viewer
from triplum.steps.chunking import WholeText
from triplum.steps.retrieval import BM25
from triplum.store import MemoryStore

collection = Collection(name="Shop policies")
policy = Source(
    collection_id=collection.id,
    origin="returns.md",
    text="Returns are accepted within 30 days of purchase.",
)
memo = Source(
    collection_id=collection.id,
    origin="staff/returns-memo.md",
    text="Staff: returns after 30 days need a manager.",
)
store = MemoryStore()
store.add_sources([policy], allow=["public"])
store.add_sources([memo], allow=["staff"])
for source in (policy, memo):
    store.replace_chunks(source.id, WholeText()(source))

public = Viewer(principals=frozenset({"public"}))
staff = Viewer(principals=frozenset({"public", "staff"}))
retriever = BM25(store, viewer=staff)  # indexes both sources
query = "returns after 30 days"
print([h.chunk.origin for h in retriever(query, viewer=staff, k=5)])
print([h.chunk.origin for h in retriever(query, viewer=public, k=5)])
print(len(BM25(store, viewer=public)(query, viewer=staff, k=5)))
```

```text
['staff/returns-memo.md', 'returns.md']
['returns.md']
1
```

The public query never sees the staff memo, although it is the better match. The last line
indexes only public sources, so even a staff query finds just the policy.

!!! warning "Scores reveal term statistics of hidden sources"

    BM25 weighs each term by how many indexed chunks contain it and by the average chunk length.
    These statistics come from everything the corpus viewer indexed, not from what the query
    viewer may see. A visible chunk's score therefore depends on hidden texts, and comparing
    scores can reveal something about them. Elasticsearch document-level security behaves the
    same way. To avoid it, build the retriever with the same viewer you query with. Indexes
    scoped to each viewer are not available yet.

### A snapshot

`BM25` reads the store once, at construction, and keeps the index in memory. Sources added later,
replaced chunk lists and new grants do not reach it; build a new `BM25` to see them. The index is
not persisted. A store with no visible chunks gives an empty index, which returns `[]`.

### Every collection in the store

Store reads are not scoped to a [collection](collection.md), so `BM25` indexes every visible
source of every collection in the store. This matters when you rerun an example against the same
database file. `Collection(name=...)` gets a new random `id` on each run, so the same texts become
new sources with new ids, and the store keeps both copies. The second run then returns every
hit twice.

To rerun without duplicates, either start from a fresh database (a `MemoryStore`, or a new
SQLite file), or give the collection a fixed `id`, such as
`Collection(id=UUID("019a0000-0000-7000-8000-000000000001"), name="Shop policies")` with
`from uuid import UUID`. With a fixed `id`, the sources get the same ids again, and `add_sources`
skips sources that are already stored.

### Matching and order

- Chunks and queries are tokenized the same way: the text is lowercased (if the settings say
  so), and every whole, nonempty match of the settings' `token_pattern` is a token (capture groups
  do not change tokens). Indexed text is `chunk.text`
  only; benchmark passages that begin with their title therefore index the title as text.
- Matching is on whole tokens. With the default settings, a token is a lowercased match of
  `\w+`, so `return` does not match `returns`. There is no stemming and no stop-word removal, so
  common words such as `the` or `are` match and add to scores.
- A chunk is a hit only if it shares at least one token with the query, so fewer than `k` hits is
  normal. A query without any indexed token returns `[]`. `k` below 1 raises `ValueError`.
- Hits are ordered by score, highest first. Equal scores are ordered by the chunk's
  `(source_id, ordinal)`, so results do not depend on the order in which the store returns
  records.

### Settings and presets

[`BM25Settings`][triplum.steps.retrieval.BM25Settings] holds the configuration:

- `k1` and `b`: the BM25 parameters; `k1` at least 0 and `b` between 0 and 1, as in Lucene, so
  every chunk sharing a token scores above zero.
- `token_pattern`: the regular expression whose matches are tokens, `\w+` by default.
- `lowercase`: whether to lowercase text before tokenizing, `True` by default.

Two presets are provided:

| Preset | `k1` | `b` | Tokens | Purpose |
| --- | --- | --- | --- | --- |
| [`HIPPORAG1`][triplum.steps.retrieval.HIPPORAG1] (default) | 1.2 | 0.75 | lowercased `\w+` | approximates the Elasticsearch `standard` analyzer used by HippoRAG 1 |
| [`BM25S_DEFAULT`][triplum.steps.retrieval.BM25S_DEFAULT] | 1.5 | 0.75 | lowercased `\b\w\w+\b` | the bm25s defaults; one-character tokens are dropped |

Pass another preset or your own settings with `BM25(store, viewer=public, settings=BM25S_DEFAULT)`.
The retriever's fingerprint follows its settings only; which chunks it indexed is not part of it,
so do not cache retriever calls.

### Differences from Elasticsearch

The presets approximate Elasticsearch scoring; they do not reproduce it:

- Tokens are regular-expression matches, not Unicode word segmentation, so text such as `U.S.`,
  `3.14` or `don't` splits differently.
- Lucene stores each document's length in a single lossy byte; bm25s uses the exact length.

Expect small score differences and occasional swapped ranks compared with published results.
Stopwords, stemming and separate title fields are not supported yet.

## Reference

- [`RetrievalHit`][triplum.datatype.hit.RetrievalHit]
- [`Retriever`][triplum.steps.retrieval.Retriever], [`BM25`][triplum.steps.retrieval.BM25] and
  [`BM25Settings`][triplum.steps.retrieval.BM25Settings]

Next: [Retrieval recall](recall.md), scoring the hits against a benchmark's gold evidence.
