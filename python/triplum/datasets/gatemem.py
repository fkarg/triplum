"""GateMem (CC BY 4.0): 91 multi-principal conversation episodes across four domains and 2,218
checkpoint questions, each asked by a named principal at a turn cut, with an expected action of
answer, answer_redacted, refuse or no_memory. Every turn is one document granted to its speaker's
principal; the turn timestamp (no zone in the data, read as UTC; a quarter of the turns
have none and keep 0) is `observed_at`. Whether other
participants may see a turn is GateMem's gating rule, not a per-turn label, so the grants here are
the speaker only and the dataset is declared `needs` until the runner takes a viewer and an as-of
turn per question.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import QAEvaluation

NEEDS = "a viewer per question (the asker) and an as-of turn cut per question"


def parse(paths: dict[str, Path], n: int | None) -> Benchmark:
    doc_rows, grant_rows, chunk_rows, rows = [], [], [], []
    turn_ids: dict[tuple[str, str], int] = {}
    for name in sorted(k for k in paths if k.endswith("episodes.jsonl")):
        for ep in base.read_jsonl(paths[name]):
            for turn in ep["turns"]:
                cid = len(chunk_rows) + 1
                doc_id = f"gatemem:{ep['episode_id']}/{turn['turn_id']}"
                turn_ids[(ep["episode_id"], turn["turn_id"])] = cid
                speaker = turn["speaker"]
                meta = {
                    "episode_id": ep["episode_id"],
                    "domain": ep["domain"],
                    "turn_id": turn["turn_id"],
                    "speaker": speaker,
                    "turn_kind": turn.get("turn_kind"),
                    "timestamp": turn.get("timestamp"),
                }
                text = f"{speaker['principal_id']} ({speaker['role']}): {turn['text']}"
                doc_rows.append(
                    (
                        doc_id,
                        "gatemem",
                        None,
                        base.utc_us(turn["timestamp"]) if turn.get("timestamp") else 0,
                        json.dumps(meta),
                    )
                )
                grant_rows.append((doc_id, speaker["principal_id"], 0, None))
                chunk_rows.append((cid, doc_id, None, 0, 0, len(text), text))
    for name in sorted(k for k in paths if k.endswith("checkpoints.jsonl")):
        for c in base.read_jsonl(paths[name]):
            cut = turn_ids.get((c["episode_id"], c["as_of_turn_id"]))
            if cut is None:
                raise base.GoldMappingError(
                    f"gatemem: checkpoint {c['checkpoint_id']} cuts at an unknown turn"
                )
            include = c["judge_spec"].get("include") or []
            answerable = c["expected_action"] in ("answer", "answer_redacted")
            meta = {
                "episode_id": c["episode_id"],
                "as_of_turn_id": c["as_of_turn_id"],
                "as_of_chunk_id": cut,
                "asker": c["asker"],
                "expected_action": c["expected_action"],
                "judge_spec": c["judge_spec"],
                "leak_targets": c.get("leak_targets", []),
                "attack_type": c.get("attack_type"),
            }
            rows.append(
                base.question_row(
                    c["checkpoint_id"],
                    c["query_text"],
                    "; ".join(include) if include else c["expected_action"],
                    [],
                    [],
                    f"{c['query_type']}/{c['expected_action']}",
                    answerable=answerable,
                    metadata=meta,
                )
            )
    if n is not None:
        rows = rows[:n]
    return Benchmark(
        corpus=CorpusDataset(
            CorpusBatch(
                pl.DataFrame(doc_rows, schema=base.DOC_SCHEMA, orient="row"),
                pl.DataFrame(grant_rows, schema=base.GRANT_SCHEMA, orient="row"),
                pl.DataFrame(chunk_rows, schema=base.CHUNK_SCHEMA, orient="row"),
            )
        ),
        qa=QAEvaluation(FrameDataset(base.questions_frame(rows))),
    )


SPECS = (Spec("gatemem", "acl", base.manifest_files("gatemem"), "CC BY 4.0", parse, needs=NEEDS),)
