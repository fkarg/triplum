"""BM25 retrieval recall on a legacy fixture: R@k, all-gold AR@k and character CR@k. No LLM."""

import sys
from pathlib import Path

from triplum.datasets.fixture import LegacyFixture
from triplum.datatype import Collection, Viewer
from triplum.evaluation.recall import resolve_evidence, score_recall, summarize_recall
from triplum.steps.chunking import WholeText
from triplum.steps.retrieval import BM25
from triplum.store import MemoryStore

if __name__ == "__main__":
    path = Path(sys.argv[1])
    fixture = LegacyFixture(path)
    collection = Collection(name=path.stem)
    corpus = list(fixture.corpus(collection.id))
    store = MemoryStore()
    store.add_sources(corpus, allow=["public"])
    chunker = WholeText()  # one chunk per native passage
    for source in corpus:
        store.replace_chunks(source.id, chunker(source))

    keys = {s.external_id: s.id for s in corpus if s.external_id is not None}
    questions = list(fixture.questions())
    gold = [resolve_evidence(q, keys) for q in questions]  # fails here on unknown keys

    reader = Viewer(principals=frozenset({"public"}))
    retriever = BM25(store, viewer=reader)  # default preset: HIPPORAG1
    scores = [
        score_recall(retriever(q.input.text, viewer=reader, k=5), evidence)
        for q, evidence in zip(questions, gold, strict=True)
    ]
    for k in (2, 5):
        summary = summarize_recall(s[k] for s in scores)
        if summary.recall is None or summary.all_gold is None:
            print(f"R@{k} n/a: no question has gold evidence")
            continue
        print(
            f"R@{k} {summary.recall:.3f}  AR@{k} {summary.all_gold:.3f}  "
            f"CR@{k} {summary.character_recall:.3f}  "
            f"chars {summary.retrieved_characters:.0f}  "
            f"({summary.denominator} of {summary.questions} questions with gold)"
        )
