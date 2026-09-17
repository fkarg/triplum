"""The `small_model` extractor: GLiNER spans over a supplied entity-type vocabulary and GLiREL
relations over a supplied relation vocabulary. Both are closed-vocabulary classifiers, so the
extractor refuses to run without vocabularies; the bench derives them from the dataset's gold
when the config leaves them empty. Around 3 GB of weights through the `extract-models` extra;
GLiREL's weights are research-only (see docs/licences.md)."""

from __future__ import annotations

import json
import re

import polars as pl

from triplum.extract.protocol import CLAIM_SCHEMA, SPAN_SCHEMA, ExtractorSpec

GLINER_MODEL = "gliner-community/gliner_small-v2.5"
GLINER_REVISION = "f227d3cd637bd4e6757ae143935316d062393341"
GLIREL_MODEL = "jackboyla/glirel-large-v0"
GLIREL_REVISION = "40a523e12a8432d6da364cf2a195a28755ff04d3"
VERSION = "1"
# GLiREL's own tokenisation, reproduced so character spans map onto its token positions.
TOKEN = re.compile(r"\w+(?:[-_]\w+)*|\S")


class SmallModelExtractor:
    def __init__(
        self,
        gliner_model: str | None = None,
        *,
        entity_types: list[str],
        relation_types: list[str],
        span_threshold: float = 0.5,
        relation_threshold: float = 0.5,
        glirel_model: str = GLIREL_MODEL,
    ) -> None:
        if not entity_types or not relation_types:
            raise ValueError("small_model needs an entity-type and a relation vocabulary")
        from gliner import GLiNER
        from glirel import GLiREL

        gliner_model = gliner_model or GLINER_MODEL
        pinned = gliner_model == GLINER_MODEL and glirel_model == GLIREL_MODEL
        self.ner = GLiNER.from_pretrained(
            gliner_model, revision=GLINER_REVISION if gliner_model == GLINER_MODEL else None
        )
        self.rel = GLiREL.from_pretrained(
            glirel_model, revision=GLIREL_REVISION if glirel_model == GLIREL_MODEL else None
        )
        self.entity_types = list(entity_types)
        self.relation_types = list(relation_types)
        self.span_threshold = span_threshold
        self.relation_threshold = relation_threshold
        self.spec = ExtractorSpec(
            name="small_model",
            version=VERSION,
            model=f"{gliner_model}+{glirel_model}",
            revision=f"{GLINER_REVISION[:8]}+{GLIREL_REVISION[:8]}" if pinned else "",
            params=(
                ("entity_types", json.dumps(self.entity_types)),
                ("relation_types", json.dumps(self.relation_types)),
                ("span_threshold", str(span_threshold)),
                ("relation_threshold", str(relation_threshold)),
            ),
        )

    def run(self, chunks: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
        spans: list[tuple] = []
        claims: list[tuple] = []
        ids = chunks["id"].to_list()
        texts = chunks["text"].to_list()
        for cid, text, ents in zip(
            ids,
            texts,
            self.ner.batch_predict_entities(
                texts, self.entity_types, threshold=self.span_threshold
            ),
        ):
            tokens = list(TOKEN.finditer(text))
            start_of = {m.start(): i for i, m in enumerate(tokens)}
            end_of = {m.end(): i for i, m in enumerate(tokens)}
            ner = []
            by_key: dict[tuple[int, int], tuple[int, int]] = {}  # token span -> char span
            seen: set[tuple[int, int]] = set()
            for e in sorted(ents, key=lambda e: (e["start"], e["end"])):
                if (e["start"], e["end"]) in seen:
                    continue
                seen.add((e["start"], e["end"]))
                spans.append(
                    (int(cid), e["start"], e["end"], e["text"], e["label"], "entity", None, None)
                )
                s, t = start_of.get(e["start"]), end_of.get(e["end"])
                if s is None or t is None:
                    continue  # a span cutting through a token cannot be handed to GLiREL
                by_key[(s, t + 1)] = (e["start"], e["end"])
                ner.append([s, t, e["label"], e["text"]])
            if len(ner) < 2:
                continue
            rels = self.rel.predict_relations(
                [m.group() for m in tokens],
                self.relation_types,
                threshold=self.relation_threshold,
                ner=ner,
                top_k=1,
            )
            for r in rels:
                head = by_key.get(tuple(r["head_pos"]))
                tail = by_key.get(tuple(r["tail_pos"]))
                if head is None or tail is None or head == tail:
                    continue
                claims.append(
                    (int(cid), 0, len(text), *head, r["label"], *tail, "accepted", "glirel")
                )
        return (
            pl.DataFrame(spans, schema=SPAN_SCHEMA, orient="row"),
            pl.DataFrame(claims, schema=CLAIM_SCHEMA, orient="row"),
        )
