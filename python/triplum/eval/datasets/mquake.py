"""MQuAKE (MIT): multi-hop questions whose answer changes after a labelled fact edit. CF-3k-v2 has
3,000 counterfactual cases, T has 1,868 real temporal updates. Each case loads as one question
(the first of its three paraphrases) with the pre-edit answer; the pre-edit labelled triples go
into `triples`, and the edit, the post-edit answer and the post-edit triples into `metadata`.
There is no corpus. The runner cannot yet ingest the edit and re-ask, so both are declared
`needs` and refuse to run until it can.
"""

from __future__ import annotations

import json
from pathlib import Path

from triplum.eval.datasets import base
from triplum.eval.datasets.base import Frames, Spec

NEEDS = "fact invalidation: ingest the labelled edit, then re-ask and score the post-edit answer"


def _parse(name: str, paths: dict[str, Path], n: int | None) -> Frames:
    (path,) = paths.values()
    cases = json.loads(path.read_text(encoding="utf-8"))
    if n is not None:
        cases = cases[:n]
    rows, triples = [], []
    for c in cases:
        qid = f"{name}:{c['case_id']}"
        meta = {
            "paraphrases": c["questions"],
            "requested_rewrite": c["requested_rewrite"],
            "new_answer": c["new_answer"],
            "new_answer_alias": c["new_answer_alias"],
            "new_triples_labeled": c["orig"]["new_triples_labeled"],
            "single_hops": c["single_hops"],
            "new_single_hops": c["new_single_hops"],
        }
        rows.append(
            base.question_row(
                qid,
                c["questions"][0],
                c["answer"],
                c["answer_alias"],
                [],
                str(len(c["single_hops"])) + "-hop",
                metadata=meta,
            )
        )
        triples.extend((qid, None, s, p, o) for s, p, o in c["orig"]["triples_labeled"])
    return Frames(
        base.questions_frame(rows),
        base.empty(base.DOC_SCHEMA),
        base.empty(base.GRANT_SCHEMA),
        base.empty(base.CHUNK_SCHEMA),
        base.triples_frame(triples),
    )


def _spec(name: str, filename: str) -> Spec:
    files = tuple(f for f in base.manifest_files("mquake") if f.name.endswith(filename))
    return Spec(
        name, "temporal", files, "MIT", lambda paths, n: _parse(name, paths, n), needs=NEEDS
    )


SPECS = (_spec("mquake_cf", "MQuAKE-CF-3k-v2.json"), _spec("mquake_t", "MQuAKE-T.json"))
