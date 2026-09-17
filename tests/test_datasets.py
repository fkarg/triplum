"""Built-in sources: lazy, identified without reading, independent parts; the catalog and the
committed fixtures."""

import json

import pytest
from triplum.bench.inputs import Benchmark, materialize
from triplum.data.corpus import CHUNK_SCHEMA, DOC_SCHEMA, GRANT_SCHEMA, chunk_id, content_id
from triplum.datasets import fixtures, registry
from triplum.datasets import hipporag as hr
from triplum.eval.inputs import QUESTION_SCHEMA, TRIPLE_SCHEMA, GoldMappingError
from triplum.settings import Settings
from triplum.utils.data import Take

Q, C = "hipporag/hotpotqa.json", "hipporag/hotpotqa_corpus.json"


def _mini_hotpot(write):
    questions = [
        {
            "_id": "q1",
            "question": "Who?",
            "answer": "Bob",
            "type": "bridge",
            "level": "hard",
            "supporting_facts": [["A", 0], ["B", 0]],
            "context": [["A", ["Alice met Bob."]], ["B", ["Bob is tall."]], ["C", ["Noise."]]],
        },
        {
            "_id": "q2",
            "question": "What?",
            "answer": "yes",
            "type": "comparison",
            "level": "hard",
            "supporting_facts": [["C", 0]],
            "context": [["C", ["Noise."]], ["D", ["Other."]]],
        },
    ]
    corpus = [
        {"idx": 0, "title": "A", "text": "Alice met Bob."},
        {"idx": 1, "title": "B", "text": "Bob is tall."},
        {"idx": 2, "title": "C", "text": "Noise."},
        {"idx": 3, "title": "D", "text": "Other."},
    ]
    write(Q, questions)
    write(C, corpus)


def _hotpot(settings, pin) -> Benchmark:
    files = pin(Q, C)
    return Benchmark(
        name="hotpotqa",
        corpus=hr.HippoRAGCorpus("hotpotqa", settings, files),
        qa=hr.HippoRAGQuestions("hotpotqa", settings, files),
    )


def test_hotpot_style_parts_are_independent_and_keyed_by_title(settings, pin, write):
    _mini_hotpot(write)
    benchmark = _hotpot(settings, pin)
    q = hr.HippoRAGQuestions("hotpotqa", settings, pin(Q, C))[0]  # resolves gold on its own
    assert q.gold == tuple(sorted(chunk_id(content_id(t), 0) for t in ("A", "B")))
    fr = materialize(benchmark)
    assert fr.corpus.chunks.height == 4 and fr.corpus.documents.height == 4
    assert fr.extraction is None and fr.qa is not None
    row = fr.qa.filter(fr.qa["id"] == "q1").row(0, named=True)
    assert row["answer"] == "Bob" and set(row["gold_chunk_ids"]) <= set(fr.corpus.chunks["id"])
    assert row["aliases"] == ["Bob"] and row["answerable"] and row["as_of"] is None
    assert json.loads(row["metadata"])["candidate_chunk_ids"] == sorted(
        chunk_id(content_id(t), 0) for t in ("A", "B", "C")
    )
    a = fr.corpus.chunks.filter(fr.corpus.chunks["document_id"] == content_id("A"))
    assert a["text"][0] == "A\nAlice met Bob."
    assert fr.corpus.grants["principal"].unique().to_list() == ["public"]


def test_musique_keys_by_title_and_text(settings, pin, write):
    questions = [
        {
            "id": "m1",
            "question": "Q",
            "answer": "X",
            "answer_aliases": ["Y"],
            "answerable": True,
            "paragraphs": [
                {"idx": 0, "title": "T", "paragraph_text": "one", "is_supporting": True},
                {"idx": 1, "title": "T", "paragraph_text": "two", "is_supporting": True},
                {"idx": 2, "title": "U", "paragraph_text": "three", "is_supporting": False},
            ],
            "question_decomposition": [],
        }
    ]
    corpus = [
        {"title": "T", "text": "one"},
        {"title": "T", "text": "two"},
        {"title": "U", "text": "three"},
    ]
    q, c = "hipporag/musique.json", "hipporag/musique_corpus.json"
    write(q, questions)
    write(c, corpus)
    files = pin(q, c)
    inputs = materialize(
        Benchmark(
            corpus=hr.HippoRAGCorpus("musique", settings, files),
            qa=hr.HippoRAGQuestions("musique", settings, files),
        )
    )
    assert inputs.qa is not None and inputs.corpus.documents.height == 3
    row = inputs.qa.row(0, named=True)
    assert sorted(row["gold_chunk_ids"]) == sorted(
        chunk_id(content_id("T", t), 0) for t in ("one", "two")
    )
    assert row["aliases"] == ["X", "Y"]


def test_fingerprint_needs_no_files_and_ignores_roots(tmp_path):
    a = hr.HippoRAGCorpus("hotpotqa", Settings(data=tmp_path / "nowhere"))
    b = hr.HippoRAGCorpus("hotpotqa", Settings(data=tmp_path / "elsewhere"))
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != hr.HippoRAGQuestions("hotpotqa").fingerprint()
    assert a.fingerprint() != hr.HippoRAGCorpus("musique").fingerprint()
    assert not (tmp_path / "nowhere").exists()


def test_take_selects_questions_and_leaves_the_corpus_identity(settings, pin, write):
    _mini_hotpot(write)
    benchmark = _hotpot(settings, pin)
    assert benchmark.qa is not None
    whole = materialize(benchmark)
    one = materialize(Benchmark(corpus=benchmark.corpus, qa=Take(benchmark.qa, 1)))
    assert one.qa is not None and one.qa["id"].to_list() == ["q1"]
    assert one.corpus_hash == whole.corpus_hash
    assert one.evaluation_hash != whole.evaluation_hash
    assert one.corpus.chunks.height == whole.corpus.chunks.height


def test_gold_outside_the_corpus_is_caught_at_materialization(settings, pin, write):
    questions = [
        {
            "_id": "q1",
            "question": "Who?",
            "answer": "Bob",
            "type": "bridge",
            "level": "hard",
            "supporting_facts": [["ZZZ", 0]],
            "context": [["A", ["x"]]],
        }
    ]
    write(Q, questions)
    write(C, [{"idx": 0, "title": "A", "text": "x"}])
    questions = hr.HippoRAGQuestions("hotpotqa", settings, pin(Q, C))
    assert questions[0].gold == (chunk_id(content_id("ZZZ"), 0),)  # the record parses
    with pytest.raises(GoldMappingError, match="not in corpus"):
        materialize(_hotpot(settings, pin))


def test_duplicate_corpus_key_is_caught_at_materialization(settings, pin, write):
    write(Q, [])
    write(C, [{"idx": 0, "title": "A", "text": "x"}, {"idx": 1, "title": "A", "text": "y"}])
    with pytest.raises(GoldMappingError, match="duplicate"):
        materialize(_hotpot(settings, pin))


def test_registry_entries_are_pinned_lazy_and_fixtures_load(tmp_path):
    nowhere = Settings(data=tmp_path / "nowhere")
    for name, entry in registry.ENTRIES.items():
        assert entry.name == name
        benchmark = registry.build(name, nowhere)  # no I/O: constructing and fingerprinting
        parts = [p for p in (benchmark.corpus, benchmark.qa, benchmark.extraction) if p]
        assert parts and all(len(p.fingerprint()) == 64 for p in parts), name
        pinned = registry.pinned(name, nowhere)
        assert pinned.files and all(len(f.sha256) == 64 for f in pinned.files), name
        assert not (tmp_path / "nowhere").exists()
        if not entry.fixture:
            continue
        ds = materialize(registry.load_fixture(name))
        assert ds.qa is not None or ds.extraction is not None, name
        assert dict(ds.corpus.documents.schema) == DOC_SCHEMA, name
        assert dict(ds.corpus.grants.schema) == GRANT_SCHEMA, name
        assert dict(ds.corpus.chunks.schema) == CHUNK_SCHEMA, name
        if ds.extraction is not None:
            assert dict(ds.extraction.schema) == TRIPLE_SCHEMA
        assert len(ds.corpus_hash) == 64 and len(ds.evaluation_hash) == 64
        if ds.qa is None:
            continue
        assert dict(ds.qa.schema) == QUESTION_SCHEMA
        for gold, answerable in zip(ds.qa["gold_chunk_ids"].to_list(), ds.qa["answerable"]):
            assert gold or ds.corpus.chunks.height == 0 or not answerable or entry.needs, name


def test_protocol_fixtures_have_twenty_questions():
    for name in ("hotpotqa", "musique", "twowiki"):
        ds = materialize(registry.load_fixture(name))
        assert ds.qa is not None
        assert ds.qa.height == 20 and ds.corpus.chunks.height > 20
        short = materialize(registry.load_fixture(name, n=3))
        assert short.qa is not None and short.qa.height == 3
    gold = materialize(registry.load_fixture("twowiki")).extraction
    assert gold is not None and gold.height > 0


def test_fixture_round_trip_keeps_chunk_ids(settings, pin, write, tmp_path):
    _mini_hotpot(write)
    benchmark = _hotpot(settings, pin)
    selected = fixtures.subset(benchmark, n=1, distractors=1)
    path = fixtures.write("rt", selected, tmp_path / "rt.json")
    ds = materialize(fixtures.read("rt", source=path))
    assert ds.qa is not None
    assert ds.qa.height == 1 and ds.corpus.chunks.height == 4  # gold + candidates + one filler
    full = materialize(benchmark)
    assert set(ds.corpus.chunks["id"]) <= set(full.corpus.chunks["id"])
    assert ds.corpus_hash != ds.evaluation_hash


def test_subset_keeps_original_ordinals_of_selected_segments():
    from triplum.data.corpus import Document, Segment
    from triplum.eval.inputs import Question
    from triplum.utils.data import RecordDataset

    text = "aa bb cc"
    doc = Document(
        id="d",
        source="t",
        text=text,
        segments=tuple(Segment(ordinal=i, start=3 * i, end=3 * i + 2) for i in range(3)),
    )
    question = Question(id="q", question="?", answer="cc", gold=(chunk_id("d", 2),))
    selected = fixtures.subset(
        Benchmark(corpus=RecordDataset([doc]), qa=RecordDataset([question])), n=1, distractors=0
    )
    assert selected.corpus is not None
    (kept,) = list(selected.corpus)
    assert kept.text == text and [s.ordinal for s in kept.segments] == [2]
    assert materialize(selected).corpus.chunks["id"].to_list() == [chunk_id("d", 2)]


def test_verify_reads_and_checks_a_dataset(monkeypatch, settings, pin, write):
    _mini_hotpot(write)
    benchmark = _hotpot(settings, pin)
    monkeypatch.setattr(registry, "build", lambda name, s=None: benchmark)
    ds = registry.verify("hotpotqa")
    assert ds.corpus.documents.height == 4 and ds.qa is not None and ds.qa.height == 2


def test_each_part_pins_only_the_files_it_reads():
    from triplum.datasets import browsecomp_plus, ectqa, gatemem, metaqa, tempo

    def names(part) -> list[str]:
        return [f.name for f in part.files.files]

    assert all("/documents/" in n for n in names(tempo.Corpus()))
    assert all("/examples/" in n or "/steps/" in n for n in names(tempo.Questions()))
    assert all(browsecomp_plus.is_corpus(f) for f in browsecomp_plus.Corpus().files.files)
    assert not any(browsecomp_plus.is_corpus(f) for f in browsecomp_plus.Questions().files.files)
    assert len(browsecomp_plus.Corpus().files.files) == 7  # the train shards are the corpus
    assert all("/data/" in n for n in names(ectqa.Corpus()))
    assert all("local_questions" in n for n in names(ectqa.Questions()))
    assert all(n.endswith("episodes.jsonl") for n in names(gatemem.Corpus()))
    assert all(n.endswith("checkpoints.jsonl") for n in names(gatemem.Questions()))
    assert names(metaqa.Corpus()) == names(metaqa.Triples()) != names(metaqa.Questions())
    assert names(hr.HippoRAGCorpus("hotpotqa")) != names(hr.HippoRAGQuestions("hotpotqa"))
    for name in registry.ENTRIES:  # the union still covers everything the benchmark reads
        assert registry.pinned(name).files, name


def test_subset_keeps_ancestors_of_selected_segments():
    from triplum.data.corpus import Document, Segment
    from triplum.eval.inputs import Question
    from triplum.utils.data import RecordDataset

    text = "section\n\nchild"
    doc = Document(
        id="d",
        source="t",
        text=text,
        segments=(
            Segment(ordinal=0, start=0, end=len(text)),
            Segment(ordinal=1, start=9, end=len(text), parent=0, level=1),
        ),
    )
    question = Question(id="q", question="?", answer="child", gold=(chunk_id("d", 1),))
    selected = fixtures.subset(
        Benchmark(corpus=RecordDataset([doc]), qa=RecordDataset([question])), n=1, distractors=0
    )
    assert selected.corpus is not None
    (kept,) = list(selected.corpus)
    assert [s.ordinal for s in kept.segments] == [0, 1]
    chunks = materialize(selected).corpus.chunks
    assert set(chunks["parent_id"].drop_nulls()) <= set(chunks["id"])


def test_fixture_write_consumes_a_one_shot_source_once(tmp_path):
    from collections.abc import Iterator

    from triplum.data.corpus import Document
    from triplum.utils.data import IterableDataset

    class OneShot(IterableDataset[Document]):
        def __init__(self) -> None:
            self.it = iter([Document(id="d", source="t", text="once")])

        def __iter__(self) -> Iterator[Document]:
            return self.it

        def fingerprint(self) -> str:
            return "one-shot"

    path = fixtures.write("once", Benchmark(corpus=OneShot()), tmp_path / "once.json")
    assert materialize(fixtures.read("once", source=path)).corpus.documents.height == 1


def test_negative_selection_is_rejected_for_fixtures_too():
    with pytest.raises(ValueError, match="non-negative"):
        registry.load_fixture("hotpotqa", -1)
    with pytest.raises(ValueError, match="non-negative"):
        registry.load("hotpotqa", -1)
    none = materialize(registry.load_fixture("hotpotqa", 0)).qa
    assert none is not None and none.height == 0
