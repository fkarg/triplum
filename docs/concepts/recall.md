# Retrieval recall

**Recall** measures how much of a question's gold evidence the top `k` hits contain. It scores a
retriever on its own, before any model reads the hits, so it needs no API key and no LLM.
[`triplum.evaluation.recall`][triplum.evaluation.recall] provides three functions:

1. [`resolve_evidence`][triplum.evaluation.recall.resolve_evidence] turns a question's
   [gold evidence](benchmark-inputs.md#evidence) into references to stored Sources.
2. [`score_recall`][triplum.evaluation.recall.score_recall] scores one question's hits at
   several `k`.
3. [`summarize_recall`][triplum.evaluation.recall.summarize_recall] averages the scores of many
   questions at one `k`.

## Example

```python
from triplum.datatype import (
    Collection,
    QAQuestion,
    QuestionInput,
    Source,
    SpanEvidence,
    Viewer,
)
from triplum.evaluation.recall import resolve_evidence, score_recall, summarize_recall
from triplum.steps.chunking import FixedSize
from triplum.steps.retrieval import BM25
from triplum.store import MemoryStore

collection = Collection(name="Shop policies")
source = Source(
    collection_id=collection.id,
    origin="policy.md",
    external_id="policy",
    text="Returns are accepted within 30 days. Refunds take 5 days.",
)
store = MemoryStore()
store.add_sources([source], allow=["public"])
store.replace_chunks(source.id, FixedSize(20)(source))

question = QAQuestion(
    id="q1",
    input=QuestionInput(text="How many days do refunds take?"),
    answers=["5 days"],
    evidence=[[SpanEvidence(document="policy", start=37, end=57)]],
    answerable=True,
)
gold = resolve_evidence(question, {"policy": source.id})

public = Viewer(principals=frozenset({"public"}))
hits = BM25(store, viewer=public)(question.input.text, viewer=public, k=2)
print([(h.chunk.start, h.chunk.text) for h in hits])
scores = score_recall(hits, gold, ks=(1, 2))
for k, score in scores.items():
    print(k, score)
print(summarize_recall([scores[2]]))
```

```text
[(40, 'unds take 5 days.'), (20, ' within 30 days. Ref')]
1 recall=0.0 all_gold=False character_recall=0.85 retrieved_characters=17
2 recall=1.0 all_gold=True character_recall=1.0 retrieved_characters=37
recall=1.0 all_gold=1.0 character_recall=1.0 retrieved_characters=37.0 questions=1 no_gold=0 denominator=1 character_denominator=1
```

1. The gold evidence is `Refunds take 5 days.`, characters `[37, 57)` of the policy.
   `resolve_evidence` replaces the document key `"policy"` with the Source's id.
2. `FixedSize(20)` cuts that sentence across two chunks. The best hit holds only
   `unds take 5 days.`, so at `k=1` the span is not covered and recall is 0. That hit still holds
   17 of the span's 20 characters, so character recall is 0.85.
3. At `k=2` the two hits together contain the whole span, so recall is 1.

## Resolve evidence first

`resolve_evidence(question, sources)` returns the question's evidence sets with each native
document key replaced by a Source id: a `SpanEvidence` becomes a
[`ResolvedSpan`][triplum.evaluation.recall.ResolvedSpan] with the same offsets, and a
`DocumentEvidence` a [`ResolvedDocument`][triplum.evaluation.recall.ResolvedDocument].

`sources` maps the benchmark's document keys to Source ids within one collection. For a
benchmark's own corpus, the keys are the Sources' [`external_id`](source.md#external-id)s:

```python
keys = {s.external_id: s.id for s in corpus if s.external_id is not None}
```

A key missing from `sources` raises `KeyError` naming the question and the key. Resolve every
question before retrieving, so a mismatched corpus fails at once instead of scoring as zero.

## How coverage is scored

`score_recall(hits, evidence, ks=(2, 5))` returns a
[`RecallAtK`][triplum.evaluation.recall.RecallAtK] for each `k` in `ks`. For each `k` it takes
the first `k` hits as given, without reranking or removing duplicates; fewer hits are scored as
they are.

- **A span is covered** when the chunks among the top `k` that come from its source together
  contain all of its characters. Adjacent and overlapping chunks combine; a gap leaves the span
  uncovered. Coverage is strict: a span that is 90% retrieved counts as not covered.
- **A document is covered** when any top-`k` chunk comes from it.
- **Each evidence set** scores the fraction of its items covered, each item weighing the same.
- **The question** takes its best set. Items of different sets never combine.

Coverage uses only each chunk's `source_id` and its character range
`[start, start + len(text))`; it reads no store and compares no text. `k` below 1 raises
`ValueError`.

Recall trusts its inputs. It does not remove duplicate hits, and it does not check that the
viewer could read each hit; a duplicate still takes one of the top `k` places. It also does not
know who asked: gold in a source the viewer cannot read is never retrieved, so it counts as a
miss. Benchmark fixtures carry no document grants, so evaluations that depend on permissions are
not supported yet; see [Legacy fixtures](benchmark-inputs.md#legacy-fixtures).

A `RecallAtK` has four fields:

- `recall`: the best set's fraction of covered items.
- `all_gold`: whether some set is covered completely.
- `character_recall`: the best set's fraction of gold characters that lie inside top-`k` chunks
  of the same source. Overlapping gold spans count their shared characters once. The best set is
  chosen separately from `recall`, so the two may come from different sets. This follows
  Chroma's token recall for chunking evaluation, counted over characters instead of tokens. A
  document has no character extent, so `character_recall` is `None` when any set contains
  document evidence.
- `retrieved_characters`: how many distinct source characters the top `k` hits contain.
  Overlapping chunks count their shared characters once, so this measures how much of the corpus
  was retrieved, not how much text a reader would receive.

With one chunk per whole passage and whole-passage gold, `recall` is HippoRAG's passage recall
R@k and `all_gold` its all-gold recall AR@k.

## Questions without gold

A question whose `evidence` is `[]` has nothing to cover: its `recall`, `all_gold` and
`character_recall` are `None`.
Its `retrieved_characters` are still counted.

`summarize_recall(scores, no_gold="exclude")` averages one `k` across questions into a
[`RecallSummary`][triplum.evaluation.recall.RecallSummary]:

- `recall` and `all_gold`: means over the `denominator` questions. The default leaves questions
  without gold out; `no_gold="zero"` counts them as 0.
- `character_recall`: the mean over the `character_denominator` questions, which are the
  `denominator` questions without document evidence. With `no_gold="zero"`, questions without
  gold count as 0 here too.
- `retrieved_characters`: the mean over all `questions`.
- `questions`, `no_gold` and `denominator`: how many questions were scored, how many had no gold,
  and how many entered the `recall` and `all_gold` means.

A mean over no questions is `None`.

## BM25 on a fixture and on HotpotQA

`examples/bm25_recall.py` scores [BM25](retrieval.md) on a benchmark. It stores the corpus with
public access, keeps each passage as one chunk with [`WholeText`](chunking.md#whole-text),
resolves all evidence, then retrieves five hits per question with the default `HIPPORAG1`
settings. It needs no API key. Given a repository fixture, it needs no network or cache either:

```sh
uv run python examples/bm25_recall.py tests/fixtures/hotpotqa.json
```

```text
R@2 0.600  AR@2 0.300  CR@2 0.563  chars 968  (20 of 20 questions with gold)
R@5 0.775  AR@5 0.600  CR@5 0.747  chars 2639  (20 of 20 questions with gold)
```

`AR@k` is the `all_gold` mean, `CR@k` the `character_recall` mean and `chars` the mean distinct
retrieved characters. `CR@k` differs from `R@k` because the two weigh gold differently: strict
recall gives each gold passage the same weight, while character recall weighs each passage by
its length. Twenty questions are too few to compare with published results.

Given `hotpotqa`, it scores the 1,000 [HotpotQA](datasets.md#load-hotpotqa) questions over
9,811 passages, downloading them on first use. The optional second argument chooses the
[gold unit](datasets.md#choose-the-gold-unit) and defaults to `passage`. A run takes about 30
seconds:

```sh
uv run python examples/bm25_recall.py hotpotqa passage
```

```text
R@2 0.562  AR@2 0.247  CR@2 0.550  chars 896  (1000 of 1000 questions with gold)
R@5 0.732  AR@5 0.503  CR@5 0.725  chars 2451  (1000 of 1000 questions with gold)
```

With `sentence`, `R@2` is 0.571 and `R@5` 0.737, and `CR@2` 0.567 and `CR@5` 0.732; `AR@k` is
unchanged, since a passage is retrieved whole or not at all. HippoRAG's paper
([arXiv 2405.14831](https://arxiv.org/abs/2405.14831), Table 2) reports BM25 R@2 55.4 and R@5
72.2 on HotpotQA, within about one point of the passage-gold run. That the pinned files are
the corpus and questions the paper's run used has not been established, so treat the comparison
as approximate.

## Reference

- [`resolve_evidence`][triplum.evaluation.recall.resolve_evidence],
  [`ResolvedSpan`][triplum.evaluation.recall.ResolvedSpan] and
  [`ResolvedDocument`][triplum.evaluation.recall.ResolvedDocument]
- [`score_recall`][triplum.evaluation.recall.score_recall] and
  [`RecallAtK`][triplum.evaluation.recall.RecallAtK]
- [`summarize_recall`][triplum.evaluation.recall.summarize_recall] and
  [`RecallSummary`][triplum.evaluation.recall.RecallSummary]

Next: [Decision points](decisions.md), every place you choose an implementation.
