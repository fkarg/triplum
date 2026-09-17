"""GateMem (CC BY 4.0): 91 multi-principal conversation episodes across four domains and 2,218
checkpoint questions, each asked by a named principal at a turn cut, with an expected action of
answer, answer_redacted, refuse or no_memory. Every turn is one document granted to its speaker's
principal, keyed by episode and turn id; the turn timestamp (no zone in the data, read as UTC; a
quarter of the turns have none and keep 0) is `observed_at`. Whether other participants may see
a turn is GateMem's gating rule, not a per-turn label, so the grants here are the speaker only
and the dataset is declared `needs` until the runner takes a viewer and an as-of turn per
question.
"""

from __future__ import annotations

from pathlib import Path

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document, chunk_id
from triplum.datasets import base
from triplum.datasets.base import Entry, ListSource
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import Question
from triplum.settings import Settings

NEEDS = "a viewer per question (the asker) and an as-of turn cut per question"


def document_id(episode_id: str, turn_id: str) -> str:
    return f"gatemem:{episode_id}/{turn_id}"


class Corpus(ListSource[tuple[dict, dict], Document]):
    """One document per turn across the per-domain episode files, in file then turn order."""

    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("gatemem"), settings)

    def read(self, paths: dict[str, Path]) -> list[tuple[dict, dict]]:
        return [
            (ep, turn)
            for name in sorted(k for k in paths if k.endswith("episodes.jsonl"))
            for ep in base.jsonl_rows(paths[name])
            for turn in ep["turns"]
        ]

    def record(self, raw: tuple[dict, dict], index: int) -> Document:
        ep, turn = raw
        speaker = turn["speaker"]
        meta = {
            "episode_id": ep["episode_id"],
            "domain": ep["domain"],
            "turn_id": turn["turn_id"],
            "speaker": speaker,
            "turn_kind": turn.get("turn_kind"),
            "timestamp": turn.get("timestamp"),
        }
        return Document(
            id=document_id(ep["episode_id"], turn["turn_id"]),
            source="gatemem",
            text=f"{speaker['principal_id']} ({speaker['role']}): {turn['text']}",
            observed_at=base.utc_us(turn["timestamp"]) if turn.get("timestamp") else 0,
            grants=(speaker["principal_id"],),
            metadata=meta,
        )


class Questions(ListSource[dict, Question]):
    def __init__(
        self, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        super().__init__(files or manifest_files("gatemem"), settings)

    def read(self, paths: dict[str, Path]) -> list[dict]:
        return [
            c
            for name in sorted(k for k in paths if k.endswith("checkpoints.jsonl"))
            for c in base.jsonl_rows(paths[name])
        ]

    def record(self, raw: dict, index: int) -> Question:
        c = raw
        include = c["judge_spec"].get("include") or []
        meta = {
            "episode_id": c["episode_id"],
            "as_of_turn_id": c["as_of_turn_id"],
            "as_of_chunk_id": chunk_id(document_id(c["episode_id"], c["as_of_turn_id"]), 0),
            "asker": c["asker"],
            "expected_action": c["expected_action"],
            "judge_spec": c["judge_spec"],
            "leak_targets": c.get("leak_targets", []),
            "attack_type": c.get("attack_type"),
        }
        return Question(
            id=c["checkpoint_id"],
            question=c["query_text"],
            answer="; ".join(include) if include else c["expected_action"],
            qtype=f"{c['query_type']}/{c['expected_action']}",
            answerable=c["expected_action"] in ("answer", "answer_redacted"),
            metadata=meta,
        )


ENTRIES = (
    Entry(
        name="gatemem",
        family="acl",
        licence="CC BY 4.0",
        needs=NEEDS,
        build=lambda s: Benchmark(name="gatemem", corpus=Corpus(s), qa=Questions(s)),
    ),
)
