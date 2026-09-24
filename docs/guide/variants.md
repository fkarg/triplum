# Seeded distractors

`DistractorCorpus` makes a corpus variant for a QA benchmark. It keeps the selected questions'
gold and available candidate chunks, then adds a fixed number of other chunks chosen by `seed`.

```python
from triplum.data.corpus import Document, chunk_id
from triplum.datasets.variants import DistractorCorpus
from triplum.eval.inputs import Question
from triplum.utils.data import RecordDataset

corpus = RecordDataset(
    [
        Document(id="answer", source="notes", text="Alice lives in Ghent."),
        Document(id="other-1", source="notes", text="Bob lives in Oslo."),
        Document(id="other-2", source="notes", text="Carol lives in Paris."),
    ]
)
questions = RecordDataset(
    [
        Question(
            id="q", question="Where does Alice live?", answer="Ghent", gold=(chunk_id("answer", 0),)
        )
    ]
)
variant = DistractorCorpus(corpus, questions, count=1, seed=7)
assert [doc.id for doc in variant] == [doc.id for doc in variant]
assert len(list(variant)) == 2
assert variant.fingerprint() != DistractorCorpus(corpus, questions, count=1, seed=8).fingerprint()
```

Use `variant` as a `Benchmark` corpus with the same questions. Constructing it and asking for its
fingerprint do not read either source. Each iteration currently reads the whole corpus to select
chunks. A seed belongs to the corpus variant; benchmark replicates keep that corpus fixed.
