"""The two extraction stages, plain callables over frames (design D5).

`extract` grounds an extractor's claims into the canonical graph frames; `resolve` adds
`same_as` facts between entities of different documents. Both are deterministic in their inputs
and the `recorded_at` they are given.
"""

from __future__ import annotations

import re

import polars as pl

from triplum.data.schema import TS_MAX
from triplum.extract import resolvers
from triplum.extract.protocol import (
    CLAIM_SCHEMA,
    ENTITY_SCHEMA,
    FACT_SCHEMA,
    MENTION_SCHEMA,
    SUPPORT_SCHEMA,
    Extraction,
    Extractor,
    ResolverSpec,
    entity_id,
    fact_id,
    proposition_id,
)


def _fact_row(
    fid: int,
    prop: str,
    subject: str,
    predicate: str,
    object_id: str | None,
    literal: str | None,
    datatype: str | None,
    valid_from: int,
    recorded_at: int,
) -> tuple:
    return (
        fid,
        prop,
        subject,
        predicate,
        object_id,
        literal,
        datatype,
        None,
        valid_from,
        TS_MAX,
        recorded_at,
        None,
        None,
        None,
    )


def extract(
    chunks: pl.DataFrame, documents: pl.DataFrame, extractor: Extractor, recorded_at: int
) -> Extraction:
    """Run the extractor and ground its output. Every entity span becomes a mention and a
    `label` fact (plus a `type` fact when the extractor typed it); every accepted claim whose
    subject is an entity span and whose object is any span becomes one fact with one
    single-chunk support group. Claims that cannot be grounded are kept with status
    `ungrounded`. `valid_from` is the document's `observed_at`; `valid_to` is open."""
    spans, claims = extractor.run(chunks)
    doc_of = dict(zip(chunks["id"].to_list(), chunks["document_id"].to_list()))
    observed = dict(zip(documents["id"].to_list(), documents["observed_at"].to_list()))
    xh = extractor.spec.hash()
    span_at: dict[tuple[int, int, int], dict] = {}
    entities: dict[str, None] = {}
    mentions: dict[tuple[str, int, int], tuple] = {}
    facts: dict[int, tuple] = {}
    support: list[tuple] = []

    def add_fact(
        subject: str,
        predicate: str,
        object_id: str | None,
        literal: str | None,
        datatype: str | None,
        chunk_id: int,
        sent: tuple[int, int],
    ) -> None:
        prop = proposition_id(subject, predicate, object_id, literal, datatype)
        fid = fact_id(xh, chunk_id, sent[0], sent[1], prop)
        if fid in facts:
            return
        facts[fid] = _fact_row(
            fid,
            prop,
            subject,
            predicate,
            object_id,
            literal,
            datatype,
            int(observed[doc_of[chunk_id]]),
            recorded_at,
        )
        support.append((fid, 0, chunk_id, xh, recorded_at))

    for s in spans.iter_rows(named=True):
        cid, start, end = int(s["chunk_id"]), int(s["start"]), int(s["end"])
        span_at[(cid, start, end)] = s
        if s["kind"] != "entity":
            continue
        eid = entity_id(doc_of[cid], s["text"])
        s["entity_id"] = eid
        entities[eid] = None
        mentions.setdefault((eid, cid, start), (eid, cid, start, end, None))
        label = re.sub(r"\s+", " ", s["text"]).strip()
        add_fact(eid, "label", None, label, "string", cid, (start, end))
        if s["label"]:
            add_fact(eid, "type", None, s["label"], "string", cid, (start, end))

    out_claims: list[tuple] = []
    for c in claims.iter_rows(named=True):
        cid = int(c["chunk_id"])
        status, reason = c["status"], c["reason"]
        subj = span_at.get((cid, int(c["subj_start"]), int(c["subj_end"])))
        obj = span_at.get((cid, int(c["obj_start"]), int(c["obj_end"])))
        if status == "accepted":
            if subj is None or obj is None:
                status, reason = "ungrounded", "argument is not a span"
            elif subj["kind"] != "entity":
                status, reason = "ungrounded", "subject is a literal"
            elif subj is obj:
                status, reason = "ungrounded", "subject and object are one span"
        if status == "accepted":
            assert subj is not None and obj is not None
            sent = (int(c["sent_start"]), int(c["sent_end"]))
            if obj["kind"] == "entity":
                add_fact(subj["entity_id"], c["predicate"], obj["entity_id"], None, None, cid, sent)
            else:
                add_fact(
                    subj["entity_id"],
                    c["predicate"],
                    None,
                    obj["value"] if obj["value"] is not None else obj["text"],
                    obj["datatype"] or "string",
                    cid,
                    sent,
                )
        out_claims.append(
            (
                cid,
                c["sent_start"],
                c["sent_end"],
                c["subj_start"],
                c["subj_end"],
                c["predicate"],
                c["obj_start"],
                c["obj_end"],
                status,
                reason,
            )
        )

    return Extraction(
        entities=pl.DataFrame([(e, None) for e in entities], schema=ENTITY_SCHEMA, orient="row"),
        facts=pl.DataFrame(list(facts.values()), schema=FACT_SCHEMA, orient="row"),
        fact_support=pl.DataFrame(support, schema=SUPPORT_SCHEMA, orient="row"),
        mentions=pl.DataFrame(list(mentions.values()), schema=MENTION_SCHEMA, orient="row"),
        claims=pl.DataFrame(out_claims, schema=CLAIM_SCHEMA, orient="row"),
    )


def resolve(
    extraction: Extraction, chunks: pl.DataFrame, resolver: ResolverSpec, recorded_at: int
) -> Extraction:
    """Add one `same_as` fact per pair of entities the resolver links, each supported by one
    group holding a mention chunk of both sides (a merge a viewer cannot see both sides of does
    not exist for that viewer), and fill `canonical_id` from the union of all links, for
    reporting only. `chunks` maps mentions to documents; entities are never linked within one
    document, where the id already merges equal surfaces."""
    if resolver.name == "none":
        return extraction
    pairs = resolvers.pairs(extraction, chunks, resolver)
    xh = "resolver:" + resolver.hash()
    facts = extraction.facts.to_dicts()
    have = {f["id"] for f in facts}
    support = extraction.fact_support.to_dicts()
    parent: dict[str, str] = {e: e for e in extraction.entities["id"].to_list()}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for f in facts:  # links already in the graph stay in the union
        if f["predicate"] == "same_as":
            union(f["subject_id"], f["object_id"])
    for a, b, chunk_a, chunk_b in pairs:
        prop = proposition_id(a, "same_as", b, None, None)
        fid = fact_id(xh, min(chunk_a, chunk_b), 0, 0, prop)
        if fid in have:
            continue
        have.add(fid)
        facts.append(
            dict(
                zip(FACT_SCHEMA, _fact_row(fid, prop, a, "same_as", b, None, None, 0, recorded_at))
            )
        )
        for cid in sorted({chunk_a, chunk_b}):
            support.append(dict(zip(SUPPORT_SCHEMA, (fid, 0, cid, xh, recorded_at))))
        union(a, b)

    entities = [(e, None if find(e) == e else find(e)) for e in parent]
    return Extraction(
        entities=pl.DataFrame(entities, schema=ENTITY_SCHEMA, orient="row"),
        facts=pl.DataFrame(facts, schema=FACT_SCHEMA),
        fact_support=pl.DataFrame(support, schema=SUPPORT_SCHEMA),
        mentions=extraction.mentions,
        claims=extraction.claims,
    )


def build(
    chunks: pl.DataFrame,
    documents: pl.DataFrame,
    extractor: Extractor,
    resolver: ResolverSpec,
    recorded_at: int,
) -> Extraction:
    """The whole graph for a corpus: `extract`, then `resolve`. The bench calls this and
    nothing else, so the composition is part of the graph's code fingerprint."""
    return resolve(
        extract(chunks, documents, extractor, recorded_at), chunks, resolver, recorded_at
    )
