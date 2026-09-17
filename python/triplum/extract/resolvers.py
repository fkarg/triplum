"""Entity resolvers: which pairs of entities from different documents are the same thing.

Each returns candidate pairs as `(entity_a, entity_b, chunk_a, chunk_b)` with `entity_a <
entity_b`; `stages.resolve` turns them into supported `same_as` facts. `exact` links equal
normalised surfaces; `fuzzy` adds RapidFuzz token-set similarity above the threshold between
entities of the same NER type.
"""

from __future__ import annotations

from collections import defaultdict

import polars as pl

from triplum.extract.protocol import Extraction, ResolverSpec, normalise

NAMES = ("none", "exact", "fuzzy")


def _profiles(extraction: Extraction, chunks: pl.DataFrame) -> dict[str, dict]:
    """Per entity: its document, first mention chunk, normalised surfaces and NER types."""
    doc_of = dict(zip(chunks["id"].to_list(), chunks["document_id"].to_list()))
    out: dict[str, dict] = {}
    first = (
        extraction.mentions.group_by("entity_id")
        .agg(pl.col("chunk_id").min())
        .iter_rows(named=True)
    )
    for m in first:
        out[m["entity_id"]] = {
            "document": doc_of[int(m["chunk_id"])],
            "chunk": int(m["chunk_id"]),
            "surfaces": set(),
            "types": set(),
        }
    literal = extraction.facts.filter(pl.col("predicate").is_in(["label", "type"]))
    for f in literal.iter_rows(named=True):
        p = out.get(f["subject_id"])
        if p is None:
            continue
        if f["predicate"] == "label":
            p["surfaces"].add(normalise(f["object_literal"]))
        else:
            p["types"].add(f["object_literal"])
    return out


def _cross_document(group: list[str], profiles: dict[str, dict]) -> list[tuple]:
    pairs = []
    ids = sorted(group)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if profiles[a]["document"] != profiles[b]["document"]:
                pairs.append((a, b, profiles[a]["chunk"], profiles[b]["chunk"]))
    return pairs


def exact(extraction: Extraction, chunks: pl.DataFrame) -> list[tuple]:
    profiles = _profiles(extraction, chunks)
    by_surface: dict[str, list[str]] = defaultdict(list)
    for eid, p in profiles.items():
        for s in p["surfaces"]:
            by_surface[s].append(eid)
    seen: set[tuple[str, str]] = set()
    pairs = []
    for group in by_surface.values():
        for pair in _cross_document(group, profiles):
            if pair[:2] not in seen:
                seen.add(pair[:2])
                pairs.append(pair)
    return sorted(pairs)


def fuzzy(extraction: Extraction, chunks: pl.DataFrame, threshold: float) -> list[tuple]:
    """`exact` plus pairs of same-typed entities whose best surface pair scores at least
    `threshold` (0..1) on RapidFuzz `token_set_ratio`."""
    from rapidfuzz import fuzz, process

    profiles = _profiles(extraction, chunks)
    pairs = {p[:2]: p for p in exact(extraction, chunks)}
    by_type: dict[str, list[str]] = defaultdict(list)
    for eid, p in profiles.items():
        for t in p["types"]:
            by_type[t].append(eid)
    for group in by_type.values():
        ids = sorted(set(group))
        surfaces = [sorted(profiles[e]["surfaces"]) for e in ids]
        flat = [(i, s) for i, ss in enumerate(surfaces) for s in ss]
        texts = [s for _, s in flat]
        scores = process.cdist(
            texts, texts, scorer=fuzz.token_set_ratio, score_cutoff=threshold * 100
        )
        for r, (i, _) in enumerate(flat):
            for c, (j, _) in enumerate(flat):
                if i >= j or scores[r][c] < threshold * 100:
                    continue
                a, b = ids[i], ids[j]
                if profiles[a]["document"] == profiles[b]["document"] or (a, b) in pairs:
                    continue
                pairs[(a, b)] = (a, b, profiles[a]["chunk"], profiles[b]["chunk"])
    return sorted(pairs.values())


def pairs(extraction: Extraction, chunks: pl.DataFrame, spec: ResolverSpec) -> list[tuple]:
    if spec.name == "exact":
        return exact(extraction, chunks)
    if spec.name == "fuzzy":
        return fuzzy(extraction, chunks, spec.threshold)
    raise ValueError(f"unknown resolver {spec.name!r}; one of {NAMES}")
