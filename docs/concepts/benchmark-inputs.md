# Benchmark inputs

A question-answering **benchmark** gives you two things that belong together: a corpus to index
and the questions to ask over it. [`QABenchmark`][triplum.datasets.benchmark.QABenchmark] bundles
them, so the questions' gold evidence always refers to the corpus it came with. Each question is a
[`QAQuestion`][triplum.datatype.question.QAQuestion]: the public input a retriever or reader may
see, plus the answers and evidence that only evaluation may read.

## Load a fixture

The repository's test fixtures are small benchmark slices. `LegacyFixture` reads one in place.
From a checkout:

```python
from pathlib import Path

from triplum.datasets import LegacyFixture
from triplum.datatype import Collection

collection = Collection(name="HotpotQA fixture")
benchmark = LegacyFixture(Path("tests/fixtures/hotpotqa.json"))
corpus = benchmark.corpus(collection.id)
questions = benchmark.questions()
print(len(corpus), len(questions))

question = questions[0]
print(question.input.text)
print(question.answers)

texts = {source.origin: source.text for source in corpus}
for span in question.evidence[0]:
    print(span.document, repr(texts[span.document][span.start : span.end][:40]))
```

```text
234 20
what is one of the stars of  The Newcomers known for
['superhero roles as the Marvel Comics']
8a9695ac21cfb24cc673 'Chris Evans (actor)\nChristopher Robert E'
4c30d3dbd568c7c2f81a 'The Newcomers (film)\nThe Newcomers is a '
```

1. `corpus(collection.id)` is a [dataset](datasets.md) of [Sources](source.md) in the collection
   you pass. Each `origin` is the fixture's document id.
2. `questions()` is a dataset of `QAQuestion`s in the fixture's order.
3. The question needs two paragraphs together; each is a `SpanEvidence` naming its document and
   a character range of that document's text.

## The bundle

`QABenchmark` is a Protocol with two methods:

- `corpus(collection_id)` returns the benchmark's documents as a `Dataset[Source]` of that
  collection. A question-only benchmark returns an empty corpus.
- `questions()` returns a `Dataset[QAQuestion]` in the benchmark's native order.

Both are ordinary datasets, so a [`DataLoader`](datasets.md) consumes them and their
`fingerprint()` identifies their content. There is no shared schema beyond these two methods;
each benchmark decides how to read its native files.

## Questions

A `QAQuestion` has these fields:

- `id`: the benchmark's native question id, used to match the same question across runs.
- `input`: a `QuestionInput` holding only `text`, the question as posed. Pass this, and only
  this, to retrieval and answering steps; gold never appears in it.
- `answers`: accepted answers, canonical first.
- `evidence`: alternative evidence sets. A set is satisfied when all of its items are; any one
  set suffices. `[]` means the question has no gold evidence. An empty set is rejected, since
  retrieving nothing would satisfy it.
- `answerable`: whether the corpus supports an answer.
- `metadata`: the benchmark's native extras. These may contain gold, such as supporting
  sentences or labels, so metadata is for evaluation only.

Questions are frozen: fields cannot be reassigned. Nested lists and metadata are immutable by
convention.

## Evidence

An evidence item is one of two records:

- `SpanEvidence(document, start, end)`: characters `[start, end)` of one document's text are
  needed. `end` must be greater than `start`.
- `DocumentEvidence(document)`: the document as a whole is the evidence, for benchmarks that only
  record pages.

`document` is the benchmark's native document key, and offsets index the `Source.text` that the
same benchmark's `corpus()` yields. Resolving an evidence key to a stored Source is not
implemented yet. In legacy fixtures the key equals the Source's `origin`, which the example uses.

## Legacy fixtures

`LegacyFixture(path)` reads a `tests/fixtures/<name>.json` file:

- The file is parsed once, when you create the benchmark; later edits need a new instance.
- Each document becomes one Source with `origin` set to its document id and its text unchanged.
- Each gold id in the file names a stored paragraph of a document and becomes that paragraph's
  `SpanEvidence`. All of a question's gold forms one evidence set; without gold, `evidence` is
  `[]`.
- `answers` is the answer followed by its aliases, without duplicates. `metadata` keeps the
  file's question metadata, plus `qtype`, and `as_of` where set.
- Duplicate document or question ids, gold that names no paragraph, and paragraphs outside their
  document raise `ValueError` at construction.
- Fingerprints follow the yielded records, so the corpus fingerprint also changes with the
  collection.

Some fixture data is not carried: document grants, `observed_at` timestamps and per-question
candidate restrictions. The candidate lists remain in `metadata` with no defined meaning yet.
Evaluations that depend on permissions, time or distractor sets are therefore not supported by
these benchmarks.

## Reference

- [`QAQuestion`][triplum.datatype.question.QAQuestion],
  [`QuestionInput`][triplum.datatype.question.QuestionInput],
  [`SpanEvidence`][triplum.datatype.question.SpanEvidence] and
  [`DocumentEvidence`][triplum.datatype.question.DocumentEvidence]
- [`QABenchmark`][triplum.datasets.benchmark.QABenchmark] and
  [`LegacyFixture`][triplum.datasets.fixture.LegacyFixture]

Next: [Decision points](decisions.md), every place you choose an implementation.
