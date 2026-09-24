"""Each source on small source-shaped records: gold resolution, abstention labels, timestamps,
triples and metadata, without the real downloads."""

import base64
import hashlib
import io
import json
import tarfile
import zipfile

import polars as pl
import pytest

from triplum.bench.inputs import Benchmark, materialize
from triplum.data.corpus import chunk_id, content_id
from triplum.datasets import (
    base,
    browsecomp_plus,
    ectqa,
    extraction,
    gatemem,
    long_document,
    longmemeval,
    metaqa,
    mquake,
    multihoprag,
    question_only,
    reading,
    tempo,
    wiki_multihop,
)
from triplum.eval.inputs import GoldMappingError


def _meta(frames, i=0):
    assert frames.qa is not None
    return json.loads(frames.qa["metadata"][i])


def _cid(*key: str) -> int:
    return chunk_id(content_id(*key), 0)


def test_hotpotqa_full_parquet_structs(settings, pin, write):
    name = "hotpotqa_full/v.parquet"
    write(name, b"")
    pl.DataFrame(
        {
            "id": ["h1"],
            "question": ["Who?"],
            "answer": ["Bob"],
            "type": ["bridge"],
            "level": ["hard"],
            "supporting_facts": [{"title": ["A", "B"], "sent_id": [0, 1]}],
            "context": [
                {
                    "title": ["A", "B", "C"],
                    "sentences": [["Alice ", "met Bob."], ["Bob."], ["Noise."]],
                }
            ],
        }
    ).write_parquet(settings.data / name)
    files = pin(name)
    fr = materialize(
        Benchmark(
            corpus=wiki_multihop.Corpus("hotpotqa_full", settings, files),
            qa=wiki_multihop.Questions("hotpotqa_full", settings, files),
        )
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["gold_chunk_ids"] == sorted([_cid("A", "Alice met Bob."), _cid("B", "Bob.")])
    assert fr.corpus.chunks.height == 3
    assert fr.corpus.chunks["text"][0] == "A\nAlice met Bob."
    assert _meta(fr)["candidate_chunk_ids"] == sorted(
        [_cid("A", "Alice met Bob."), _cid("B", "Bob."), _cid("C", "Noise.")]
    )


def test_twowiki_full_json_strings_and_evidence_triples(settings, pin, write):
    name = "twowiki_full/dev.parquet"
    write(name, b"")
    pl.DataFrame(
        {
            "_id": ["w1", "w2"],
            "type": ["comparison", "inference"],
            "question": ["Q1", "Q2"],
            "answer": ["yes", "no"],
            "context": [
                json.dumps([["A", ["a."]], ["B", ["b."]]]),
                json.dumps([["A", ["a."]], ["C", ["c."]]]),
            ],
            "supporting_facts": [json.dumps([["A", 0], ["B", 0]]), json.dumps([["C", 0]])],
            "evidences": [json.dumps([["A", "rel", "B"]]), json.dumps([])],
        }
    ).write_parquet(settings.data / name)
    files = pin(name)
    fr = materialize(
        Benchmark(
            corpus=wiki_multihop.Corpus("twowiki_full", settings, files),
            qa=wiki_multihop.Questions("twowiki_full", settings, files),
            extraction=wiki_multihop.TwoWikiFullTriples(settings, files),
        )
    )
    assert fr.corpus.chunks.height == 3  # A shared across questions
    assert fr.qa is not None
    assert fr.qa["gold_chunk_ids"].to_list() == [
        sorted([_cid("A", "a."), _cid("B", "b.")]),
        [_cid("C", "c.")],
    ]
    assert fr.extraction is not None
    assert fr.extraction.to_dicts() == [
        {
            "question_id": "w1",
            "document_id": None,
            "subject": "A",
            "predicate": "rel",
            "object": "B",
        }
    ]


def test_musique_full_twins(settings, pin, write):
    paras = [
        {"idx": 0, "title": "T", "paragraph_text": "one", "is_supporting": True},
        {"idx": 1, "title": "U", "paragraph_text": "two", "is_supporting": False},
    ]
    records = [
        {"id": "2hop__1_2", "paragraphs": paras, "question": "Q", "question_decomposition": [], "answer": "X",
         "answer_aliases": ["Y"], "answerable": True},
        {"id": "2hop__1_2", "paragraphs": paras[1:], "question": "Q", "question_decomposition": [], "answer": "X",
         "answer_aliases": [], "answerable": False},
    ]  # fmt: skip
    name = "musique_full/dev.jsonl"
    write(name, "\n".join(json.dumps(r) for r in records))
    files = pin(name)
    fr = materialize(
        Benchmark(
            corpus=wiki_multihop.Corpus("musique_full", settings, files),
            qa=wiki_multihop.Questions("musique_full", settings, files),
        )
    )
    assert fr.qa is not None
    a, u = fr.qa.iter_rows(named=True)
    assert a["id"] == "2hop__1_2" and a["gold_chunk_ids"] == [_cid("T", "one")]
    assert a["aliases"] == ["X", "Y"]
    assert (
        u["id"] == "2hop__1_2__unanswerable" and not u["answerable"] and u["gold_chunk_ids"] == []
    )
    assert u["answer"] == "unanswerable" and _meta(fr, 1)["answer_if_answerable"] == "X"


def test_morehopqa_symbolic_steps_are_not_gold(settings, pin, write):
    rec = {
        "_id": "m1", "question": "Q", "answer": 4, "previous_question": "P", "previous_answer": "A",
        "question_decomposition": [
            {"sub_id": "1", "question": "s1", "answer": "a1", "paragraph_support_title": "A"},
            {"sub_id": "2", "question": "s2", "answer": "4", "paragraph_support_title": ""},
        ],
        "context": [["A", ["a."]], ["B", ["b."]]],
        "no_of_hops": 2, "reasoning_type": "count", "answer_type": "number",
    }  # fmt: skip
    name = "morehopqa/v.json"
    write(name, [rec])
    files = pin(name)
    fr = materialize(
        Benchmark(
            corpus=wiki_multihop.Corpus("morehopqa", settings, files),
            qa=wiki_multihop.Questions("morehopqa", settings, files),
        )
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["answer"] == "4" and q["gold_chunk_ids"] == [_cid("A", "a.")] and q["qtype"] == "count"
    assert len(_meta(fr)["decomposition"]) == 2


def test_multihoprag_null_query_and_published_at(settings, pin, write):
    corpus = [
        {"title": "T1", "author": None, "source": "S", "published_at": "2023-09-28T12:00:00+00:00",
         "category": "tech", "url": "http://a", "body": "body a"},
        {"title": "T2", "author": "X", "source": "S", "published_at": "2023-10-01T14:00:29+00:00",
         "category": "tech", "url": "http://b", "body": "body b"},
    ]  # fmt: skip
    questions = [
        {"query": "Q1", "answer": "A", "question_type": "inference_query",
         "evidence_list": [{"url": "http://a", "fact": "f"}, {"url": "http://b", "fact": "g"}]},
        {"query": "Q2", "answer": "Insufficient information.", "question_type": "null_query", "evidence_list": []},
    ]  # fmt: skip
    write("multihoprag/MultiHopRAG.json", questions)
    write("multihoprag/corpus.json", corpus)
    files = pin("multihoprag/MultiHopRAG.json", "multihoprag/corpus.json")
    fr = materialize(
        Benchmark(
            corpus=multihoprag.Corpus(settings, files), qa=multihoprag.Questions(settings, files)
        )
    )
    assert fr.qa is not None
    a = chunk_id(multihoprag.document_id("http://a"), 0)
    b = chunk_id(multihoprag.document_id("http://b"), 0)
    assert fr.qa["gold_chunk_ids"].to_list() == [sorted([a, b]), []]
    assert fr.qa["answerable"].to_list() == [True, False]
    assert fr.corpus.documents["observed_at"][0] == base.utc_us("2023-09-28T12:00:00+00:00") > 0
    assert fr.corpus.documents["uri"][1] == "http://b"


def test_ectqa_transcripts_and_unanswerable(settings, pin, write):
    t = {"company_name": "ACME", "stock_code": "ACM", "sector": "energy", "year": "2021", "quarter": "q4",
         "URL": "http://x", "raw_content": "raw", "cleaned_content": "Operator: hello", "token_count": 2}  # fmt: skip
    local_old = [
        {"question": "Q1", "answer": "$2b", "reasoning_type": "enumeration", "question_type": "multi-time query",
         "num_hops": 1, "evidence_list": [{"ect_filename": "energy-ACM-2021-q4.json", "evidence": "e"}]},
        {"question": "Q2", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope",
         "question_type": "relative-time query", "num_hops": 0, "evidence_list": []},
    ]  # fmt: skip
    names = {
        "ectqa/data/old/energy-ACM-2021-q4.json": t,
        "ectqa/questions/local_questions_old.json": local_old,
        "ectqa/questions/local_questions_new.json": [],
        "ectqa/questions/global_questions_old.json": [{}],
    }
    for name, content in names.items():
        write(name, content)
    files = pin(*names)
    fr = materialize(
        Benchmark(corpus=ectqa.Corpus(settings, files), qa=ectqa.Questions(settings, files))
    )
    assert (
        fr.corpus.documents["id"][0] == "ectqa:energy-ACM-2021-q4.json"
        and fr.corpus.documents["observed_at"][0] == 0
    )
    assert json.loads(fr.corpus.documents["metadata"][0])["split"] == "old"
    assert fr.qa is not None
    gold = chunk_id(ectqa.document_id("energy-ACM-2021-q4.json"), 0)
    assert fr.qa["gold_chunk_ids"].to_list() == [[gold], []]
    assert fr.qa["answerable"].to_list() == [True, False]
    assert fr.corpus.chunks["text"][0].startswith("ACME 2021 Q4 earnings call\n")


def test_popqa_and_entityquestions_have_no_corpus(settings, pin, write):
    header = "id\tsubj\tprop\tobj\tsubj_id\tprop_id\tobj_id\ts_aliases\to_aliases\ts_uri\to_uri\ts_wiki_title\to_wiki_title\ts_pop\to_pop\tquestion\tpossible_answers"
    row = '7\tParis\tcountry\tFrance\t1\t2\t3\t[]\t[]\tu\tv\tParis\tFrance\t100\t200\tIn what country is Paris?\t["France", "French Republic"]'
    write("popqa/test.tsv", header + "\n" + row + "\n")
    fr = materialize(
        Benchmark(qa=question_only.Questions("popqa", settings, pin("popqa/test.tsv")))
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert (
        q["aliases"] == ["France", "French Republic"]
        and q["qtype"] == "country"
        and q["gold_chunk_ids"] == []
    )
    assert fr.corpus.chunks.height == 0 and _meta(fr)["s_pop"] == "100"
    zpath = write("entityquestions/dataset.zip", b"")
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(
            "dataset/test/P19.test.json",
            json.dumps([{"question": "Where was X born?", "answers": ["Y", "Z"]}]),
        )
        zf.writestr(
            "dataset/dev/P19.dev.json", json.dumps([{"question": "ignored", "answers": ["n"]}])
        )
    source = question_only.Questions(
        "entityquestions", settings, pin("entityquestions/dataset.zip")
    )
    fr = materialize(Benchmark(qa=source))
    assert fr.qa is not None
    assert fr.qa["id"].to_list() == ["P19:0"] and fr.qa["aliases"][0].to_list() == ["Y", "Z"]


def test_mquake_pre_edit_triples_and_post_edit_metadata(settings, pin, write):
    case = {
        "case_id": 1, "requested_rewrite": [{"prompt": "p"}], "questions": ["Q a", "Q b", "Q c"],
        "answer": "Old", "answer_alias": ["O"], "new_answer": "New", "new_answer_alias": [],
        "single_hops": [{}, {}], "new_single_hops": [{}, {}],
        "orig": {"triples_labeled": [["S", "P", "Old"]], "new_triples_labeled": [["S", "P", "New"]]},
    }  # fmt: skip
    write("mquake/MQuAKE-T.json", [case])
    files = pin("mquake/MQuAKE-T.json")
    fr = materialize(
        Benchmark(
            qa=mquake.Questions("mquake_t", settings, files),
            extraction=mquake.Triples("mquake_t", settings, files),
        )
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert (
        q["id"] == "mquake_t:1"
        and q["question"] == "Q a"
        and q["aliases"] == ["Old", "O"]
        and q["qtype"] == "2-hop"
    )
    assert fr.extraction is not None
    assert fr.extraction["object"].to_list() == ["Old"] and _meta(fr)["new_answer"] == "New"
    assert all(e.needs for e in mquake.ENTRIES)


def test_gatemem_turns_are_speaker_scoped_documents(settings, pin, write):
    episode = {"episode_id": "e1", "domain": "office", "entities": {}, "turns": [
        {"turn_id": "t001", "timestamp": "2026-04-08T09:00", "speaker": {"principal_id": "alice", "role": "lead"},
         "turn_kind": "dialogue", "text": "hello"},
        {"turn_id": "t002", "timestamp": "2026-04-08T09:03", "speaker": {"principal_id": "bob", "role": "dev"},
         "turn_kind": "dialogue", "text": "hi"},
        {"turn_id": "t003", "speaker": {"principal_id": "bob", "role": "dev"}, "text": "no stamp"},
    ]}  # fmt: skip
    checkpoint = {"checkpoint_id": "c1", "episode_id": "e1", "as_of_turn_id": "t002",
                  "asker": {"principal_id": "bob", "role": "dev"}, "query_type": "utility", "query_text": "What?",
                  "expected_action": "refuse", "judge_spec": {"expected_action": "refuse"}}  # fmt: skip
    write("gatemem/gatemem/data/office/episodes.jsonl", json.dumps(episode))
    write("gatemem/gatemem/data/office/checkpoints.jsonl", json.dumps(checkpoint))
    files = pin(
        "gatemem/gatemem/data/office/episodes.jsonl",
        "gatemem/gatemem/data/office/checkpoints.jsonl",
    )
    fr = materialize(
        Benchmark(corpus=gatemem.Corpus(settings, files), qa=gatemem.Questions(settings, files))
    )
    assert fr.corpus.grants["principal"].to_list() == ["alice", "bob", "bob"]
    assert fr.corpus.documents["observed_at"][2] == 0
    assert (
        fr.corpus.documents["observed_at"][1] - fr.corpus.documents["observed_at"][0]
        == 3 * 60 * 1_000_000
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert not q["answerable"] and q["answer"] == "refuse"
    assert _meta(fr)["as_of_chunk_id"] == chunk_id(gatemem.document_id("e1", "t002"), 0)
    assert _meta(fr)["leak_targets"] == []
    assert gatemem.ENTRIES[0].needs


def test_longmemeval_sessions_dates_and_abstention(settings, pin, write):
    turns = [
        {"role": "user", "content": "I graduated in BA", "has_answer": True},
        {"role": "assistant", "content": "nice"},
    ]
    records = [
        {"question_id": "q1", "question_type": "single-session-user", "question": "Degree?",
         "question_date": "2023/05/30 (Tue) 23:40", "answer": "BA", "answer_session_ids": ["s2"],
         "haystack_dates": ["2023/05/20 (Sat) 02:21", "2023/05/21 (Sun) 03:24"], "haystack_session_ids": ["s1", "s2"],
         "haystack_sessions": [[{"role": "user", "content": "puzzle"}], turns]},
        {"question_id": "q2_abs", "question_type": "single-session-user", "question": "Car?",
         "question_date": "2023/05/30 (Tue) 23:40", "answer": "No car mentioned", "answer_session_ids": [],
         "haystack_dates": ["2023/05/20 (Sat) 02:21"], "haystack_session_ids": ["s1"],
         "haystack_sessions": [[{"role": "user", "content": "puzzle"}]]},
    ]  # fmt: skip
    write("longmemeval_s/s.json", records)
    files = pin("longmemeval_s/s.json")
    fr = materialize(
        Benchmark(
            corpus=longmemeval.Corpus(settings, files), qa=longmemeval.Questions(settings, files)
        )
    )
    assert fr.corpus.chunks.height == 3 and fr.corpus.documents["id"][1] == "longmemeval_s:q1/1"
    assert fr.qa is not None
    assert fr.qa["gold_chunk_ids"].to_list() == [[chunk_id("longmemeval_s:q1/1", 0)], []]
    assert fr.qa["answerable"].to_list() == [True, False]
    assert (
        fr.qa["as_of"][0]
        > fr.corpus.documents["observed_at"][1]
        > fr.corpus.documents["observed_at"][0]
    )
    assert json.loads(fr.corpus.documents["metadata"][1])["answer_turns"] == [0]
    bad = [{**records[0], "answer_session_ids": ["nope"]}]
    write("longmemeval_s/s.json", bad)
    with pytest.raises(GoldMappingError, match="not in haystack"):
        longmemeval.Questions(settings, pin("longmemeval_s/s.json"))[0]


def test_tempo_gold_ids_and_step_metadata(settings, pin, write):
    names = []
    for domain in tempo.DOMAINS:
        for kind in ("documents", "examples", "steps"):
            names.append(f"tempo/{kind}/{domain}.parquet")
            write(names[-1], b"")
        pl.DataFrame({"id": [f"{domain}/d1.txt"], "content": [f"{domain} doc"]}).write_parquet(
            settings.data / f"tempo/documents/{domain}.parquet"
        )
        pl.DataFrame(
            {"id": [f"{domain}_0"], "query": ["Q"], "gold_ids": [[f"{domain}/d1.txt"]],
             "gold_answers": [["<p>A</p>"]], "negative_ids": [[]]},
            schema={"id": pl.Utf8, "query": pl.Utf8, "gold_ids": pl.List(pl.Utf8), "gold_answers": pl.List(pl.Utf8),
                    "negative_ids": pl.List(pl.Utf8)},
        ).write_parquet(settings.data / f"tempo/examples/{domain}.parquet")  # fmt: skip
        pl.DataFrame({"id": [f"{domain}_0"], "query_guidance": [{"is_temporal_query": True}],
                      "gold_passage_annotations": [[{"doc_id": f"{domain}/d1.txt"}]]}).write_parquet(
            settings.data / f"tempo/steps/{domain}.parquet"
        )  # fmt: skip
    files = pin(*names)
    corpus = tempo.Corpus(settings, files)
    from triplum.utils.data import Take

    fr = materialize(Benchmark(corpus=corpus, qa=Take(tempo.Questions(settings, files), 2)))
    assert fr.qa is not None
    assert fr.corpus.chunks.height == len(tempo.DOMAINS) and fr.qa.height == 2
    assert fr.qa["gold_chunk_ids"].to_list() == [
        [chunk_id(tempo.document_id(f"{d}/d1.txt"), 0)] for d in tempo.DOMAINS[:2]
    ]
    assert _meta(fr)["query_guidance"]["is_temporal_query"] is True
    assert not tempo.ENTRIES[0].fixture


def test_graphjudge_lines_json_or_python_literal(settings, pin, write):
    names = {
        "g/test.source": '[["A", "rel", "B"]]\n',
        "g/test.target": "A rel B.\n",
        "g/train.source": "[['C', 'r', 'D'], ['C', 'q', 'E']]\n",
        "g/train.target": "C r D and q E.\n",
    }
    for name, content in names.items():
        write(name, content)
    files = pin(*names)
    fr = materialize(
        Benchmark(
            corpus=extraction.Corpus("graphjudge_genwiki", settings, files),
            extraction=extraction.Triples("graphjudge_genwiki", settings, files),
        )
    )
    assert fr.extraction is not None
    assert fr.qa is None and fr.corpus.documents.height == 2 and fr.extraction.height == 3
    assert fr.extraction["document_id"].to_list() == [
        "graphjudge_genwiki:test:0",
        "graphjudge_genwiki:train:0",
        "graphjudge_genwiki:train:0",
    ]
    write("g/train.target", "one\ntwo\n")
    with pytest.raises(GoldMappingError):
        len(extraction.Corpus("graphjudge_genwiki", settings, pin(*names)))


def test_genwiki_unmasks_entities(settings, pin, write):
    rec = {"text": "<ENT_0> is a <ENT_1> .", "entities": ["White Coppice", "hamlet"],
           "graph": [["White Coppice", "settlementType", "hamlet"]],
           "id_long": {"wikipage": "White_Coppice"}, "id_short": "x"}  # fmt: skip
    zpath = write("genwiki/genwiki.zip", b"")
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("genwiki/test/test.json", json.dumps([rec]))
        zf.writestr("genwiki/train/fine/part_1.json", json.dumps([rec, rec]))
    files = pin("genwiki/genwiki.zip")
    fr = materialize(
        Benchmark(
            corpus=extraction.Corpus("genwiki", settings, files),
            extraction=extraction.Triples("genwiki", settings, files),
        )
    )
    assert fr.extraction is not None
    assert (
        fr.corpus.chunks["text"][0] == "White Coppice\nWhite Coppice is a hamlet ."
        and fr.extraction.height == 1
    )
    fine = materialize(Benchmark(corpus=extraction.Corpus("genwiki_fine", settings, files)))
    assert (
        fine.corpus.documents.height == 2
        and json.loads(fine.corpus.documents["metadata"][0])["masked_text"] == rec["text"]
    )


def test_carb_groups_tuples_by_sentence(settings, pin, write):
    dev = "S1 .\tmade\tBush\tan offer\tthis year\nS1 .\tsaid\tBush\tno\nS2 .\tis\tX\n"
    write("carb/data/gold/dev.tsv", dev)
    write("carb/data/gold/test.tsv", "")
    files = pin("carb/data/gold/dev.tsv", "carb/data/gold/test.tsv")
    fr = materialize(
        Benchmark(
            corpus=extraction.Corpus("carb", settings, files),
            extraction=extraction.Triples("carb", settings, files),
        )
    )
    assert fr.extraction is not None
    assert fr.corpus.documents.height == 2 and fr.extraction.height == 3
    assert fr.extraction.row(0) == (None, "carb:dev:0", "Bush", "made", "an offer this year")
    assert fr.extraction.row(2) == (None, "carb:dev:1", "X", "is", "")


def test_conll04_and_scierc_spans(settings, pin, write):
    rec = {"tokens": ["John", "Booth", "killed", "Lincoln", "."],
           "entities": [{"start": 0, "end": 2, "type": "Peop"}, {"start": 3, "end": 4, "type": "Peop"}],
           "relations": [{"head": 0, "tail": 1, "type": "Kill"}], "orig_id": 5}  # fmt: skip
    names = []
    for split in ("train", "validation", "test"):
        names.append(f"conll04/data/{split}-00000-of-00001.parquet")
        write(names[-1], b"")
        pl.DataFrame([rec]).write_parquet(settings.data / names[-1])
    files = pin(*names)
    fr = materialize(
        Benchmark(
            corpus=extraction.Corpus("conll04", settings, files),
            extraction=extraction.Triples("conll04", settings, files),
        )
    )
    assert fr.extraction is not None
    assert fr.corpus.documents.height == 3 and fr.extraction.row(0)[2:] == (
        "John Booth",
        "Kill",
        "Lincoln",
    )
    assert json.loads(fr.corpus.documents["metadata"][0])["entities"][0]["text"] == "John Booth"
    snames = [f"scierc/spert/scierc_{s}.json" for s in ("train", "dev", "test")]
    for name in snames:
        write(name, [rec])
    scierc = materialize(Benchmark(extraction=extraction.Triples("scierc", settings, pin(*snames))))
    assert scierc.extraction is not None and scierc.extraction.height == 3


def _encode(text: str) -> str:
    key = hashlib.sha256(browsecomp_plus.CANARY.encode()).digest()
    raw = text.encode()
    key = key * (len(raw) // len(key)) + key[: len(raw) % len(key)]
    return base64.b64encode(bytes(a ^ b for a, b in zip(raw, key))).decode()


def test_browsecomp_plus_decodes_queries_and_docids(settings, pin, write):
    corpus = write("browsecomp_plus/corpus/data/train-0.parquet", b"")
    pl.DataFrame(
        {"docid": ["5412", "26215"], "text": ["gold text", "neg text"], "url": ["u1", "u2"]}
    ).write_parquet(corpus)
    query = write("browsecomp_plus/data/test-0.parquet", b"")
    doc = lambda d: {"docid": _encode(d), "text": _encode("t"), "url": _encode("u")}
    pl.DataFrame(
        {"query_id": ["769"], "query": [_encode("Which university?")], "answer": [_encode("Queen Arwa University")],
         "gold_docs": [[doc("5412")]], "evidence_docs": [[doc("5412")]], "negative_docs": [[doc("26215")]]}
    ).write_parquet(query)  # fmt: skip
    fr = materialize(
        Benchmark(
            corpus=browsecomp_plus.Corpus(
                settings, pin("browsecomp_plus/corpus/data/train-0.parquet")
            ),
            qa=browsecomp_plus.Questions(settings, pin("browsecomp_plus/data/test-0.parquet")),
        )
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["question"] == "Which university?" and q["answer"] == "Queen Arwa University"
    gold, neg = (chunk_id(browsecomp_plus.document_id(d), 0) for d in ("5412", "26215"))
    assert q["gold_chunk_ids"] == [gold] and _meta(fr)["candidate_chunk_ids"] == sorted([gold, neg])
    assert browsecomp_plus.decode(_encode("round trip")) == "round trip"


def test_question_only_sets(settings, pin, write):
    pq = write("bamboogle/b.parquet", b"")
    pl.DataFrame({"Question": ["q?"], "Answer": ["a"]}).write_parquet(pq)
    fr = materialize(
        Benchmark(qa=question_only.Questions("bamboogle", settings, pin("bamboogle/b.parquet")))
    )
    assert fr.qa is not None and fr.qa["qtype"][0] == "multihop"
    pq = write("nq_open/v.parquet", b"")
    pl.DataFrame({"question": ["q"], "answer": [["a1", "a2"]]}).write_parquet(pq)
    fr = materialize(
        Benchmark(qa=question_only.Questions("nq_open", settings, pin("nq_open/v.parquet")))
    )
    assert fr.qa is not None
    assert fr.qa["aliases"][0].to_list() == ["a1", "a2"] and fr.corpus.chunks.height == 0
    pq = write("arc_easy/t.parquet", b"")
    pl.DataFrame(
        {
            "id": ["M_1"],
            "question": ["Which?"],
            "choices": [{"text": ["one", "two"], "label": ["A", "B"]}],
            "answerKey": ["B"],
        }
    ).write_parquet(pq)
    fr = materialize(
        Benchmark(qa=question_only.Questions("arc_easy", settings, pin("arc_easy/t.parquet")))
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["answer"] == "two" and q["aliases"] == ["two", "B"]
    zpath = write("ambigqa/ambignq_light.zip", b"")
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(
            "dev_light.json",
            json.dumps(
                [
                    {
                        "id": "1",
                        "question": "who?",
                        "annotations": [
                            {
                                "type": "multipleQAs",
                                "qaPairs": [
                                    {"question": "who 1?", "answer": ["A", "A2"]},
                                    {"question": "who 2?", "answer": ["B"]},
                                ],
                            }
                        ],
                    }
                ]
            ),
        )
    fr = materialize(
        Benchmark(qa=question_only.Questions("ambigqa", settings, pin("ambigqa/ambignq_light.zip")))
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["answer"] == "A" and q["aliases"] == ["A", "A2", "B"] and q["qtype"] == "multipleQAs"
    header = ",".join(
        ["id", "split", "question", "effective_year", "next_review", "false_premise", "num_hops"]
        + ["fact_type", "source"]
        + [f"answer_{i}" for i in range(10)]
        + ["note"]
    )
    csv_text = "Warning,,,\n,,,\n" + header + "\n"
    csv_text += "3,TEST,q?,2024,daily,TRUE,one-hop,fast-changing,http://s,x,y,,,,,,,,,n\n"
    write("freshqa/f.csv", csv_text)
    fr = materialize(
        Benchmark(qa=question_only.Questions("freshqa", settings, pin("freshqa/f.csv")))
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["id"] == "freshqa:3" and q["aliases"] == ["x", "y"] and q["qtype"] == "fast-changing"
    assert _meta(fr)["false_premise"] is True


def test_reading_sets_use_the_passage_as_gold(settings, pin, write):
    pq = write("squad_v2/v.parquet", b"")
    pl.DataFrame(
        {
            "id": ["1", "2", "3"],
            "title": ["Super_Bowl", "Super_Bowl", "Normans"],
            "context": ["c1", "c1", "c2"],
            "question": ["q1", "q2", "q3"],
            "answers": [
                {"text": ["a", "a", "b"], "answer_start": [0, 0, 1]},
                {"text": [], "answer_start": []},
                {"text": ["c"], "answer_start": [0]},
            ],
        }
    ).write_parquet(pq)
    files = pin("squad_v2/v.parquet")
    fr = materialize(
        Benchmark(
            corpus=reading.Corpus("squad_v2", settings, files),
            qa=reading.Questions("squad_v2", settings, files),
        )
    )
    assert fr.corpus.chunks.height == 2 and fr.corpus.chunks["text"][0] == "Super Bowl\nc1"
    assert fr.qa is not None
    q1, q2, q3 = fr.qa.iter_rows(named=True)
    c1, c2 = _cid("Super Bowl", "c1"), _cid("Normans", "c2")
    assert q1["aliases"] == ["a", "b"] and q1["gold_chunk_ids"] == [c1]
    assert q2["answerable"] is False and q2["gold_chunk_ids"] == []
    assert _meta(fr, 1)["candidate_chunk_ids"] == [c1] and q3["gold_chunk_ids"] == [c2]
    pq = write("boolq/v.parquet", b"")
    pl.DataFrame({"question": ["is it"], "answer": [True], "passage": ["p"]}).write_parquet(pq)
    files = pin("boolq/v.parquet")
    fr = materialize(
        Benchmark(
            corpus=reading.Corpus("boolq", settings, files),
            qa=reading.Questions("boolq", settings, files),
        )
    )
    assert fr.qa is not None
    assert fr.qa["answer"][0] == "yes" and fr.corpus.chunks["text"][0] == "p"


def test_quality_scores_the_gold_option(settings, pin, write):
    article = {
        "article_id": "a1",
        "set_unique_id": "s1",
        "title": "T",
        "article": "long text",
        "source": "gutenberg",
        "year": 1950,
        "author": "A",
        "topic": "x",
        "license": "L",
        "questions": [
            {
                "question": "q?",
                "question_unique_id": "a1_s1_1",
                "options": ["w", "x", "y", "z"],
                "gold_label": 3,
                "difficult": 1,
            }
        ],
    }
    zpath = write("quality/q.zip", b"")
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(long_document.QUALITY_MEMBER, json.dumps(article) + "\n" + json.dumps(article))
    files = pin("quality/q.zip")
    fr = materialize(
        Benchmark(
            corpus=long_document.QualityCorpus(settings, files),
            qa=long_document.QualityQuestions(settings, files),
        )
    )
    assert fr.qa is not None
    assert fr.corpus.chunks.height == 1 and fr.qa.height == 2
    q = fr.qa.row(0, named=True)
    assert q["answer"] == "y" and q["aliases"] == ["y", "3"] and q["qtype"] == "hard"
    assert json.loads(fr.corpus.documents["metadata"][0])["license"] == "L"


def test_qasper_gold_is_the_evidence_paragraph(settings, pin, write):
    def answer(**kw):
        a = {
            "unanswerable": False,
            "extractive_spans": [],
            "yes_no": None,
            "free_form_answer": "",
            "evidence": [],
            "highlighted_evidence": [],
        }
        return {"answer": a | kw, "annotation_id": "x", "worker_id": "w"}

    paper = {
        "title": "Paper",
        "abstract": "Abs.",
        "full_text": [{"section_name": "Intro", "paragraphs": ["p1", "p2"]}],
        "figures_and_tables": [{"file": "f.png", "caption": "Figure 1: cap"}],
        "qas": [
            {
                "question": "q1",
                "question_id": "q1",
                "answers": [
                    answer(extractive_spans=[" s1 ", "s2"], evidence=["p2", "table only"]),
                    answer(free_form_answer="ff", evidence=["Figure 1: cap"]),
                ],
            },
            {"question": "q2", "question_id": "q2", "answers": [answer(unanswerable=True)]},
            {"question": "q3", "question_id": "q3", "answers": [answer(yes_no=True)]},
        ],
    }
    tpath = write("qasper/q.tgz", b"")
    data = json.dumps({"pid": paper}).encode()
    with tarfile.open(tpath, "w:gz") as tf:
        info = tarfile.TarInfo(long_document.QASPER_MEMBER)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    files = pin("qasper/q.tgz")
    fr = materialize(
        Benchmark(
            corpus=long_document.QasperCorpus(settings, files),
            qa=long_document.QasperQuestions(settings, files),
        )
    )
    assert fr.corpus.documents.height == 1 and fr.corpus.chunks["text"].to_list() == [
        "Paper\nAbs.",
        "Intro\np1",
        "Intro\np2",
        "Figure 1: cap",
    ]
    assert fr.qa is not None
    assert fr.qa["id"].to_list() == ["q1", "q2"]  # q3 has no matching evidence
    q1, q2 = fr.qa.iter_rows(named=True)
    assert q1["answer"] == "s1, s2" and q1["aliases"] == ["s1, s2", "ff", "s1", "s2"]
    assert q1["gold_chunk_ids"] == sorted(chunk_id("qasper:pid", i) for i in (2, 3))
    assert q1["qtype"] == "free_form"
    assert q2["answerable"] is False and q2["answer"] == "unanswerable"


def test_metaqa_verbalises_the_kb_and_interleaves_hops(settings, pin, write):
    names = {
        "metaqa/kb.txt": "Kismet|directed_by|William Dieterle\nKismet|release_year|1944\n",
        "metaqa/1hop_qa_test.txt": "who directed [Kismet]\tWilliam Dieterle\n",
        "metaqa/2hop_qa_test.txt": "when were films by [William Dieterle] released\t1944\n",
        "metaqa/3hop_qa_test.txt": "",
    }
    for name, content in names.items():
        write(name, content)
    files = pin(*names)
    fr = materialize(
        Benchmark(
            corpus=metaqa.Corpus(settings, files),
            qa=metaqa.Questions(settings, files),
            extraction=metaqa.Triples(settings, files),
        )
    )
    assert fr.corpus.chunks["text"].to_list() == [
        "Kismet\nKismet was directed by William Dieterle. Kismet was released in 1944.",
        "William Dieterle\nWilliam Dieterle directed Kismet.",
        "1944\nKismet was released in 1944.",
    ]
    assert fr.extraction is not None
    assert fr.extraction.select("document_id", "predicate").rows() == [
        ("metaqa:Kismet", "directed_by"),
        ("metaqa:Kismet", "release_year"),
    ]
    assert fr.qa is not None
    q1, q2 = fr.qa.iter_rows(named=True)
    assert q1["id"] == "metaqa:1hop:0" and q2["id"] == "metaqa:2hop:0"
    assert q1["question"] == "who directed Kismet" and _meta(fr)["topic"] == "Kismet"
    ids = {e: chunk_id(metaqa.document_id(e), 0) for e in ("Kismet", "William Dieterle", "1944")}
    assert q1["gold_chunk_ids"] == sorted([ids["Kismet"], ids["William Dieterle"]])
    assert q2["gold_chunk_ids"] == sorted([ids["William Dieterle"], ids["1944"]])
