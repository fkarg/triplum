"""Each parser on small source-shaped records: gold resolution, abstention labels, timestamps,
triples and metadata, without the real downloads."""

import base64
import hashlib
import json
import zipfile

import polars as pl
import pytest
from triplum.bench.inputs import materialize
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


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _meta(frames, i=0):
    assert frames.qa is not None
    return json.loads(frames.qa["metadata"][i])


def test_hotpotqa_full_parquet_structs(tmp_path):
    path = tmp_path / "v.parquet"
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
    ).write_parquet(path)
    fr = materialize(wiki_multihop.parse_hotpotqa_full({"x": path}, None))
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["gold_chunk_ids"] == [1, 2] and fr.corpus.chunks.height == 3
    assert fr.corpus.chunks["text"][0] == "A\nAlice met Bob."
    assert _meta(fr)["candidate_chunk_ids"] == [1, 2, 3]


def test_twowiki_full_json_strings_and_evidence_triples(tmp_path):
    path = tmp_path / "dev.parquet"
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
    ).write_parquet(path)
    fr = materialize(wiki_multihop.parse_twowiki_full({"x": path}, None))
    assert fr.corpus.chunks.height == 3  # A shared across questions
    assert fr.qa is not None
    assert fr.qa["gold_chunk_ids"].to_list() == [[1, 2], [3]]
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


def test_musique_full_twins(tmp_path):
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
    path = _write(tmp_path, "dev.jsonl", "\n".join(json.dumps(r) for r in records))
    fr = materialize(wiki_multihop.parse_musique_full({"x": path}, None))
    assert fr.qa is not None
    a, u = fr.qa.iter_rows(named=True)
    assert a["id"] == "2hop__1_2" and a["gold_chunk_ids"] == [1] and a["aliases"] == ["X", "Y"]
    assert (
        u["id"] == "2hop__1_2__unanswerable" and not u["answerable"] and u["gold_chunk_ids"] == []
    )
    assert u["answer"] == "unanswerable" and _meta(fr, 1)["answer_if_answerable"] == "X"


def test_morehopqa_symbolic_steps_are_not_gold(tmp_path):
    rec = {
        "_id": "m1", "question": "Q", "answer": 4, "previous_question": "P", "previous_answer": "A",
        "question_decomposition": [
            {"sub_id": "1", "question": "s1", "answer": "a1", "paragraph_support_title": "A"},
            {"sub_id": "2", "question": "s2", "answer": "4", "paragraph_support_title": ""},
        ],
        "context": [["A", ["a."]], ["B", ["b."]]],
        "no_of_hops": 2, "reasoning_type": "count", "answer_type": "number",
    }  # fmt: skip
    path = _write(tmp_path, "v.json", [rec])
    fr = materialize(wiki_multihop.parse_morehopqa({"x": path}, None))
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["answer"] == "4" and q["gold_chunk_ids"] == [1] and q["qtype"] == "count"
    assert len(_meta(fr)["decomposition"]) == 2


def test_multihoprag_null_query_and_published_at(tmp_path):
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
    paths = {"multihoprag/MultiHopRAG.json": _write(tmp_path, "MultiHopRAG.json", questions),
             "multihoprag/corpus.json": _write(tmp_path, "corpus.json", corpus)}  # fmt: skip
    fr = materialize(multihoprag.parse(paths, None))
    assert fr.qa is not None
    assert fr.qa["gold_chunk_ids"].to_list() == [[1, 2], []]
    assert fr.qa["answerable"].to_list() == [True, False]
    assert fr.corpus.documents["observed_at"][0] == base.utc_us("2023-09-28T12:00:00+00:00") > 0
    assert fr.corpus.documents["uri"][1] == "http://b"


def test_ectqa_transcripts_and_unanswerable(tmp_path):
    t = {"company_name": "ACME", "stock_code": "ACM", "sector": "energy", "year": "2021", "quarter": "q4",
         "URL": "http://x", "raw_content": "raw", "cleaned_content": "Operator: hello", "token_count": 2}  # fmt: skip
    local_old = [
        {"question": "Q1", "answer": "$2b", "reasoning_type": "enumeration", "question_type": "multi-time query",
         "num_hops": 1, "evidence_list": [{"ect_filename": "energy-ACM-2021-q4.json", "evidence": "e"}]},
        {"question": "Q2", "answer": "unanswerable", "reasoning_type": "unanswerable|out-of-scope",
         "question_type": "relative-time query", "num_hops": 0, "evidence_list": []},
    ]  # fmt: skip
    paths = {
        "ectqa/data/old/energy-ACM-2021-q4.json": _write(
            tmp_path, "data/old/energy-ACM-2021-q4.json", t
        ),
        "ectqa/questions/local_questions_old.json": _write(
            tmp_path, "q/local_questions_old.json", local_old
        ),
        "ectqa/questions/local_questions_new.json": _write(
            tmp_path, "q/local_questions_new.json", []
        ),
        "ectqa/questions/global_questions_old.json": _write(
            tmp_path, "q/global_questions_old.json", [{}]
        ),
    }
    fr = materialize(ectqa.parse(paths, None))
    assert (
        fr.corpus.documents["id"][0] == "ectqa:energy-ACM-2021-q4.json"
        and fr.corpus.documents["observed_at"][0] == 0
    )
    assert json.loads(fr.corpus.documents["metadata"][0])["split"] == "old"
    assert fr.qa is not None
    assert fr.qa["gold_chunk_ids"].to_list() == [[1], []]
    assert fr.qa["answerable"].to_list() == [True, False]
    assert fr.corpus.chunks["text"][0].startswith("ACME 2021 Q4 earnings call\n")


def test_popqa_and_entityquestions_have_no_corpus(tmp_path):
    header = "id\tsubj\tprop\tobj\tsubj_id\tprop_id\tobj_id\ts_aliases\to_aliases\ts_uri\to_uri\ts_wiki_title\to_wiki_title\ts_pop\to_pop\tquestion\tpossible_answers"
    row = '7\tParis\tcountry\tFrance\t1\t2\t3\t[]\t[]\tu\tv\tParis\tFrance\t100\t200\tIn what country is Paris?\t["France", "French Republic"]'
    tsv = _write(tmp_path, "test.tsv", header + "\n" + row + "\n")
    fr = materialize(question_only.parse_popqa({"x": tsv}, None))
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert (
        q["aliases"] == ["France", "French Republic"]
        and q["qtype"] == "country"
        and q["gold_chunk_ids"] == []
    )
    assert fr.corpus.chunks.height == 0 and _meta(fr)["s_pop"] == "100"
    zpath = tmp_path / "dataset.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(
            "dataset/test/P19.test.json",
            json.dumps([{"question": "Where was X born?", "answers": ["Y", "Z"]}]),
        )
        zf.writestr(
            "dataset/dev/P19.dev.json", json.dumps([{"question": "ignored", "answers": ["n"]}])
        )
    fr = materialize(question_only.parse_entityquestions({"x": zpath}, None))
    assert fr.qa is not None
    assert fr.qa["id"].to_list() == ["P19:0"] and fr.qa["aliases"][0].to_list() == [
        "Y",
        "Z",
    ]


def test_mquake_pre_edit_triples_and_post_edit_metadata(tmp_path):
    case = {
        "case_id": 1, "requested_rewrite": [{"prompt": "p"}], "questions": ["Q a", "Q b", "Q c"],
        "answer": "Old", "answer_alias": ["O"], "new_answer": "New", "new_answer_alias": [],
        "single_hops": [{}, {}], "new_single_hops": [{}, {}],
        "orig": {"triples_labeled": [["S", "P", "Old"]], "new_triples_labeled": [["S", "P", "New"]]},
    }  # fmt: skip
    path = _write(tmp_path, "MQuAKE-T.json", [case])
    fr = materialize(mquake._parse("mquake_t", {"x": path}, None))
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
    assert all(s.needs for s in mquake.SPECS)


def test_gatemem_turns_are_speaker_scoped_documents(tmp_path):
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
    paths = {
        "gatemem/gatemem/data/office/episodes.jsonl": _write(
            tmp_path, "episodes.jsonl", json.dumps(episode)
        ),
        "gatemem/gatemem/data/office/checkpoints.jsonl": _write(
            tmp_path, "checkpoints.jsonl", json.dumps(checkpoint)
        ),
    }
    fr = materialize(gatemem.parse(paths, None))
    assert fr.corpus.grants["principal"].to_list() == ["alice", "bob", "bob"]
    assert fr.corpus.documents["observed_at"][2] == 0
    assert (
        fr.corpus.documents["observed_at"][1] - fr.corpus.documents["observed_at"][0]
        == 3 * 60 * 1_000_000
    )
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert not q["answerable"] and q["answer"] == "refuse" and _meta(fr)["as_of_chunk_id"] == 2
    assert _meta(fr)["leak_targets"] == []
    assert gatemem.SPECS[0].needs


def test_longmemeval_sessions_dates_and_abstention(tmp_path):
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
    path = _write(tmp_path, "s.json", records)
    fr = materialize(longmemeval.parse({"x": path}, None))
    assert fr.corpus.chunks.height == 3 and fr.corpus.documents["id"][1] == "longmemeval_s:q1/1"
    assert fr.qa is not None
    assert fr.qa["gold_chunk_ids"].to_list() == [[2], []]
    assert fr.qa["answerable"].to_list() == [True, False]
    assert (
        fr.qa["as_of"][0]
        > fr.corpus.documents["observed_at"][1]
        > fr.corpus.documents["observed_at"][0]
    )
    assert json.loads(fr.corpus.documents["metadata"][1])["answer_turns"] == [0]


def test_tempo_gold_ids_and_step_metadata(tmp_path):
    paths = {}
    for domain in tempo.DOMAINS:
        docs = pl.DataFrame({"id": [f"{domain}/d1.txt"], "content": [f"{domain} doc"]})
        docs.write_parquet(tmp_path / f"d-{domain}.parquet")
        paths[f"tempo/documents/{domain}.parquet"] = tmp_path / f"d-{domain}.parquet"
        examples = pl.DataFrame(
            {"id": [f"{domain}_0"], "query": ["Q"], "gold_ids": [[f"{domain}/d1.txt"]],
             "gold_answers": [["<p>A</p>"]], "negative_ids": [[]]},
            schema={"id": pl.Utf8, "query": pl.Utf8, "gold_ids": pl.List(pl.Utf8), "gold_answers": pl.List(pl.Utf8),
                    "negative_ids": pl.List(pl.Utf8)},
        )  # fmt: skip
        examples.write_parquet(tmp_path / f"e-{domain}.parquet")
        paths[f"tempo/examples/{domain}.parquet"] = tmp_path / f"e-{domain}.parquet"
        steps = pl.DataFrame({"id": [f"{domain}_0"], "query_guidance": [{"is_temporal_query": True}],
                              "gold_passage_annotations": [[{"doc_id": f"{domain}/d1.txt"}]]})  # fmt: skip
        steps.write_parquet(tmp_path / f"s-{domain}.parquet")
        paths[f"tempo/steps/{domain}.parquet"] = tmp_path / f"s-{domain}.parquet"
    fr = materialize(tempo.parse(paths, n=2))
    assert fr.qa is not None
    assert fr.corpus.chunks.height == len(tempo.DOMAINS) and fr.qa.height == 2
    assert fr.qa["gold_chunk_ids"].to_list() == [[1], [2]]
    assert _meta(fr)["query_guidance"]["is_temporal_query"] is True
    assert not tempo.SPECS[0].fixture and tempo.SPECS[0].large


def test_graphjudge_lines_json_or_python_literal(tmp_path):
    paths = {
        "g/test.source": _write(tmp_path, "test.source", '[["A", "rel", "B"]]\n'),
        "g/test.target": _write(tmp_path, "test.target", "A rel B.\n"),
        "g/train.source": _write(tmp_path, "train.source", "[['C', 'r', 'D'], ['C', 'q', 'E']]\n"),
        "g/train.target": _write(tmp_path, "train.target", "C r D and q E.\n"),
    }
    fr = materialize(extraction.parse_graphjudge("graphjudge_x", paths, None))
    assert fr.extraction is not None
    assert fr.qa is None and fr.corpus.documents.height == 2 and fr.extraction.height == 3
    assert fr.extraction["document_id"].to_list() == [
        "graphjudge_x:test:0",
        "graphjudge_x:train:0",
        "graphjudge_x:train:0",
    ]
    with pytest.raises(base.GoldMappingError):
        paths["g/train.target"] = _write(tmp_path, "bad.target", "one\ntwo\n")
        materialize(extraction.parse_graphjudge("graphjudge_x", paths, None))


def test_genwiki_unmasks_entities(tmp_path):
    rec = {"text": "<ENT_0> is a <ENT_1> .", "entities": ["White Coppice", "hamlet"],
           "graph": [["White Coppice", "settlementType", "hamlet"]],
           "id_long": {"wikipage": "White_Coppice"}, "id_short": "x"}  # fmt: skip
    zpath = tmp_path / "genwiki.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("genwiki/test/test.json", json.dumps([rec]))
        zf.writestr("genwiki/train/fine/part_1.json", json.dumps([rec, rec]))
    fr = materialize(extraction.parse_genwiki("genwiki", "genwiki/test/", {"x": zpath}, None))
    assert fr.extraction is not None
    assert (
        fr.corpus.chunks["text"][0] == "White Coppice\nWhite Coppice is a hamlet ."
        and fr.extraction.height == 1
    )
    fine = materialize(
        extraction.parse_genwiki("genwiki_fine", "genwiki/train/fine/", {"x": zpath}, None)
    )
    assert (
        fine.corpus.documents.height == 2
        and json.loads(fine.corpus.documents["metadata"][0])["masked_text"] == rec["text"]
    )


def test_carb_groups_tuples_by_sentence(tmp_path):
    dev = "S1 .\tmade\tBush\tan offer\tthis year\nS1 .\tsaid\tBush\tno\nS2 .\tis\tX\n"
    paths = {
        "carb/data/gold/dev.tsv": _write(tmp_path, "dev.tsv", dev),
        "carb/data/gold/test.tsv": _write(tmp_path, "test.tsv", ""),
    }
    fr = materialize(extraction.parse_carb(paths, None))
    assert fr.extraction is not None
    assert fr.corpus.documents.height == 2 and fr.extraction.height == 3
    assert fr.extraction.row(0) == (None, "carb:dev:0", "Bush", "made", "an offer this year")
    assert fr.extraction.row(2) == (None, "carb:dev:1", "X", "is", "")


def test_conll04_and_scierc_spans(tmp_path):
    rec = {"tokens": ["John", "Booth", "killed", "Lincoln", "."],
           "entities": [{"start": 0, "end": 2, "type": "Peop"}, {"start": 3, "end": 4, "type": "Peop"}],
           "relations": [{"head": 0, "tail": 1, "type": "Kill"}], "orig_id": 5}  # fmt: skip
    paths = {}
    for split in ("train", "validation", "test"):
        p = tmp_path / f"{split}-00000-of-00001.parquet"
        pl.DataFrame([rec]).write_parquet(p)
        paths[f"conll04/data/{split}-00000-of-00001.parquet"] = p
    fr = materialize(extraction.parse_conll04(paths, None))
    assert fr.extraction is not None
    assert fr.corpus.documents.height == 3 and fr.extraction.row(0)[2:] == (
        "John Booth",
        "Kill",
        "Lincoln",
    )
    assert json.loads(fr.corpus.documents["metadata"][0])["entities"][0]["text"] == "John Booth"
    spaths = {
        f"scierc/spert/scierc_{s}.json": _write(tmp_path, f"scierc_{s}.json", [rec])
        for s in ("train", "dev", "test")
    }
    scierc = materialize(extraction.parse_scierc(spaths, None))
    assert scierc.extraction is not None and scierc.extraction.height == 3


def _encode(text: str) -> str:
    key = hashlib.sha256(browsecomp_plus.CANARY.encode()).digest()
    raw = text.encode()
    key = key * (len(raw) // len(key)) + key[: len(raw) % len(key)]
    return base64.b64encode(bytes(a ^ b for a, b in zip(raw, key))).decode()


def test_browsecomp_plus_decodes_queries_and_docids(tmp_path):
    corpus = tmp_path / "corpus.parquet"
    pl.DataFrame(
        {"docid": ["5412", "26215"], "text": ["gold text", "neg text"], "url": ["u1", "u2"]}
    ).write_parquet(corpus)
    query = tmp_path / "test-0.parquet"
    doc = lambda d: {"docid": _encode(d), "text": _encode("t"), "url": _encode("u")}
    pl.DataFrame(
        {"query_id": ["769"], "query": [_encode("Which university?")], "answer": [_encode("Queen Arwa University")],
         "gold_docs": [[doc("5412")]], "evidence_docs": [[doc("5412")]], "negative_docs": [[doc("26215")]]}
    ).write_parquet(query)  # fmt: skip
    paths = {
        "browsecomp_plus/data/test-0.parquet": query,
        "browsecomp_plus/corpus/data/train-0.parquet": corpus,
    }
    fr = materialize(browsecomp_plus.parse(paths, None))
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["question"] == "Which university?" and q["answer"] == "Queen Arwa University"
    assert q["gold_chunk_ids"] == [1] and _meta(fr)["candidate_chunk_ids"] == [1, 2]
    assert browsecomp_plus.decode(_encode("round trip")) == "round trip"


def test_document_frames_numbers_chunks_across_documents():
    docs, grants, chunks = base.document_frames(
        "src", [("d1", ["ab", "cde"], 0, {"title": "t"}), ("d2", ["f"], 7, None)]
    )
    assert docs["id"].to_list() == ["d1", "d2"] and docs["observed_at"].to_list() == [0, 7]
    assert grants["principal"].to_list() == ["public", "public"]
    assert chunks["id"].to_list() == [1, 2, 3]
    assert chunks["document_id"].to_list() == ["d1", "d1", "d2"]
    assert chunks.select("span_start", "span_end").rows() == [(0, 2), (4, 7), (0, 1)]


def test_question_only_sets(tmp_path):
    pq = tmp_path / "b.parquet"
    pl.DataFrame({"Question": ["q?"], "Answer": ["a"]}).write_parquet(pq)
    fr = materialize(question_only.parse_bamboogle({"x": pq}, None))
    assert fr.qa is not None and fr.qa["qtype"][0] == "multihop"
    pl.DataFrame({"question": ["q"], "answer": [["a1", "a2"]]}).write_parquet(pq)
    fr = materialize(question_only.parse_nq_open({"x": pq}, None))
    assert fr.qa is not None
    assert fr.qa["aliases"][0].to_list() == ["a1", "a2"] and fr.corpus.chunks.height == 0
    pl.DataFrame(
        {
            "id": ["M_1"],
            "question": ["Which?"],
            "choices": [{"text": ["one", "two"], "label": ["A", "B"]}],
            "answerKey": ["B"],
        }
    ).write_parquet(pq)
    fr = materialize(question_only.parse_arc({"x": pq}, None))
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["answer"] == "two" and q["aliases"] == ["two", "B"]
    zpath = tmp_path / "ambignq_light.zip"
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
    fr = materialize(question_only.parse_ambigqa({"x": zpath}, None))
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
    fr = materialize(question_only.parse_freshqa({"x": _write(tmp_path, "f.csv", csv_text)}, None))
    assert fr.qa is not None
    q = fr.qa.row(0, named=True)
    assert q["id"] == "freshqa:3" and q["aliases"] == ["x", "y"] and q["qtype"] == "fast-changing"
    assert _meta(fr)["false_premise"] is True


def test_reading_sets_use_the_passage_as_gold(tmp_path):
    pq = tmp_path / "v.parquet"
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
    fr = materialize(reading.parse_squad_v2({"x": pq}, None))
    assert fr.corpus.chunks.height == 2 and fr.corpus.chunks["text"][0] == "Super Bowl\nc1"
    assert fr.qa is not None
    q1, q2, q3 = fr.qa.iter_rows(named=True)
    assert q1["aliases"] == ["a", "b"] and q1["gold_chunk_ids"] == [1]
    assert q2["answerable"] is False and q2["gold_chunk_ids"] == []
    assert _meta(fr, 1)["candidate_chunk_ids"] == [1] and q3["gold_chunk_ids"] == [2]
    pl.DataFrame({"question": ["is it"], "answer": [True], "passage": ["p"]}).write_parquet(pq)
    fr = materialize(reading.parse_boolq({"x": pq}, None))
    assert fr.qa is not None
    assert fr.qa["answer"][0] == "yes" and fr.corpus.chunks["text"][0] == "p"


def test_quality_scores_the_gold_option(tmp_path):
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
    zpath = tmp_path / "q.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(long_document.QUALITY_MEMBER, json.dumps(article) + "\n" + json.dumps(article))
    fr = materialize(long_document.parse_quality({"x": zpath}, None))
    assert fr.qa is not None
    assert fr.corpus.chunks.height == 1 and fr.qa.height == 2
    q = fr.qa.row(0, named=True)
    assert q["answer"] == "y" and q["aliases"] == ["y", "3"] and q["qtype"] == "hard"
    assert json.loads(fr.corpus.documents["metadata"][0])["license"] == "L"


def test_qasper_gold_is_the_evidence_paragraph(tmp_path):
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
    tpath = tmp_path / "q.tgz"
    import io
    import tarfile

    data = json.dumps({"pid": paper}).encode()
    with tarfile.open(tpath, "w:gz") as tf:
        info = tarfile.TarInfo(long_document.QASPER_MEMBER)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    fr = materialize(long_document.parse_qasper({"x": tpath}, None))
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
    assert q1["gold_chunk_ids"] == [3, 4] and q1["qtype"] == "free_form"
    assert q2["answerable"] is False and q2["answer"] == "unanswerable"


def test_metaqa_verbalises_the_kb_and_interleaves_hops(tmp_path):
    kb = _write(
        tmp_path, "kb.txt", "Kismet|directed_by|William Dieterle\nKismet|release_year|1944\n"
    )
    h1 = _write(tmp_path, "1hop_qa_test.txt", "who directed [Kismet]\tWilliam Dieterle\n")
    h2 = _write(
        tmp_path, "2hop_qa_test.txt", "when were films by [William Dieterle] released\t1944\n"
    )
    h3 = _write(tmp_path, "3hop_qa_test.txt", "")
    fr = materialize(
        metaqa.parse(
            {"kb.txt": kb, "1hop_qa_test.txt": h1, "2hop_qa_test.txt": h2, "3hop_qa_test.txt": h3},
            None,
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
    assert q1["gold_chunk_ids"] == [1, 2] and q2["gold_chunk_ids"] == [2, 3]
