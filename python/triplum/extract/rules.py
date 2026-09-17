"""The `rules` extractor: spaCy `en_core_web_sm` spans and dependency rules, no model trained
for the task. Cheap, permissive and deterministic, so it is the comparator every other
extractor is measured against. The rule set is versioned in `VERSION`; a rule change is a new
extractor identity."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import polars as pl

from triplum.extract.protocol import CLAIM_SCHEMA, SPAN_SCHEMA, ExtractorSpec

MODEL = "en_core_web_sm"
VERSION = "1"
# spaCy NER labels that are values, not things, with the datatype they become.
LITERAL = {
    "DATE": "date",
    "TIME": "date",
    "CARDINAL": "number",
    "MONEY": "money",
    "PERCENT": "percent",
    "QUANTITY": "quantity",
    "ORDINAL": "string",
}
SUBJECT = ("nsubj", "nsubjpass")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
DATE_SETTINGS = {
    # Absolute dates only: relative ones ("yesterday", "next May") would need today's clock.
    "PARSERS": ["custom-formats", "absolute-time"],
    "REQUIRE_PARTS": ["year"],
    "PREFER_DAY_OF_MONTH": "first",
    "RELATIVE_BASE": EPOCH,
    "RETURN_AS_TIMEZONE_AWARE": False,
}


class RulesExtractor:
    def __init__(self, model: str = MODEL) -> None:
        import spacy

        self.nlp = spacy.load(model)
        self.spec = ExtractorSpec(
            name="rules", version=VERSION, model=model, revision=self.nlp.meta["version"]
        )

    def run(self, chunks: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
        spans: list[tuple] = []
        claims: list[tuple] = []
        ids = chunks["id"].to_list()
        for cid, doc in zip(ids, self.nlp.pipe(chunks["text"].to_list(), batch_size=64)):
            s, c = _chunk(int(cid), doc)
            spans += s
            claims += c
        return (
            pl.DataFrame(spans, schema=SPAN_SCHEMA, orient="row"),
            pl.DataFrame(claims, schema=CLAIM_SCHEMA, orient="row"),
        )


def literal_value(text: str, datatype: str) -> tuple[str, str]:
    """(datatype, value) for a literal surface: ISO date for parsed dates, a plain number for
    parsed numbers, the collapsed surface otherwise. Unparsed dates and numbers become
    strings rather than guesses."""
    surface = re.sub(r"\s+", " ", text).strip()
    if datatype == "date":
        import dateparser

        d = dateparser.parse(surface, languages=["en"], settings=DATE_SETTINGS)
        return ("date", d.date().isoformat()) if d else ("string", surface)
    if datatype == "number":
        try:
            n = float(surface.replace(",", ""))
        except ValueError:
            return "string", surface
        return "number", str(int(n)) if n.is_integer() else repr(n)
    return datatype, surface


def _conjuncts(tok) -> list:
    out = [tok]
    for c in tok.children:
        if c.dep_ == "conj":
            out += _conjuncts(c)
    return out


def _clause(verb) -> str:
    """`accepted` for a verb that is the sentence root or a conjunct of it; every other clause
    (marked, adverbial, complement, relative) is `subordinate` and only recorded."""
    t = verb
    while t.dep_ == "conj":
        t = t.head
    return "accepted" if t.dep_ == "ROOT" else "subordinate"


def _negated_modal(verb) -> tuple[bool, bool]:
    neg = any(c.dep_ == "neg" for c in verb.children)
    modal = any(c.dep_ == "aux" and c.tag_ == "MD" for c in verb.children)
    if verb.dep_ == "conj" and verb.head.pos_ in ("VERB", "AUX"):
        hn, hm = _negated_modal(verb.head)
        neg, modal = neg or hn, modal or hm
    return neg, modal


def _subjects(verb) -> list:
    subj = [c for c in verb.children if c.dep_ in SUBJECT]
    if not subj and verb.dep_ == "conj" and verb.head.pos_ in ("VERB", "AUX"):
        return _subjects(verb.head)
    return [t for s in subj for t in _conjuncts(s)]


def _predicate(verb) -> str:
    lemma = verb.lemma_.lower()
    for c in verb.children:
        if c.dep_ == "prt":
            return f"{lemma}_{c.text.lower()}"
    return lemma


def _chunk(cid: int, doc) -> tuple[list[tuple], list[tuple]]:
    spans: dict[tuple[int, int], tuple] = {}
    at: dict[int, tuple[int, int]] = {}  # token index -> span key

    def add(start_tok, end_tok, text, label, kind, datatype, value) -> tuple[int, int]:
        key = (doc[start_tok].idx, doc[end_tok - 1].idx + len(doc[end_tok - 1]))
        if key not in spans:
            spans[key] = (cid, key[0], key[1], text, label, kind, datatype, value)
            for i in range(start_tok, end_tok):
                at[i] = key
        return key

    for ent in doc.ents:
        if ent.label_ in LITERAL:
            dt, value = literal_value(ent.text, LITERAL[ent.label_])
            add(ent.start, ent.end, ent.text, ent.label_, "literal", dt, value)
        else:
            add(ent.start, ent.end, ent.text, ent.label_, "entity", None, None)
    for nc in doc.noun_chunks:
        if nc.root.pos_ == "PRON" or any(i in at for i in range(nc.start, nc.end)):
            continue
        add(nc.start, nc.end, nc.text, "", "entity", None, None)

    claims: list[tuple] = []

    def claim(sent, subj, predicate, obj, status, reason, obj_key=None) -> None:
        s_key = at.get(subj.i)
        o_key = obj_key or at.get(obj.i)
        if status == "accepted" and (s_key is None or o_key is None):
            missing = subj if s_key is None else obj
            status = "ungrounded"
            reason = "pronoun" if missing.pos_ == "PRON" else "no span"
        s_key = s_key or (subj.idx, subj.idx + len(subj))
        o_key = o_key or (obj.idx, obj.idx + len(obj))
        claims.append(
            (cid, sent.start_char, sent.end_char, *s_key, predicate, *o_key, status, reason)
        )

    for sent in doc.sents:
        for tok in sent:
            for app in tok.children:
                if app.dep_ == "appos":
                    for o in _conjuncts(app):
                        claim(sent, tok, "be", o, "accepted", "apposition")
            if tok.pos_ not in ("VERB", "AUX"):
                continue
            status = _clause(tok)
            neg, modal = _negated_modal(tok)
            if status == "accepted" and neg:
                status = "negated"
            elif status == "accepted" and modal:
                status = "modal"
            subjects = _subjects(tok)
            pred = _predicate(tok)
            passive = [c for c in tok.children if c.dep_ == "nsubjpass"]
            for c in tok.children:
                if c.dep_ == "agent":
                    for agent in (o for p in c.children if p.dep_ == "pobj" for o in _conjuncts(p)):
                        for patient in (t for p in passive for t in _conjuncts(p)):
                            claim(sent, agent, pred, patient, status, "passive")
                elif c.dep_ == "dobj":
                    for s in subjects:
                        for o in _conjuncts(c):
                            claim(sent, s, pred, o, status, "active")
                elif c.dep_ == "prep":
                    for p in c.children:
                        if p.dep_ == "pobj":
                            for s in subjects:
                                for o in _conjuncts(p):
                                    claim(sent, s, f"{pred}_{c.text.lower()}", o, status, "prep")
                elif c.dep_ == "attr" and tok.lemma_ == "be":
                    for s in subjects:
                        for o in _conjuncts(c):
                            claim(sent, s, "be", o, status, "copula")
                elif c.dep_ == "acomp" and tok.lemma_ == "be":
                    key = add(c.i, c.i + 1, c.text, "", "literal", "string", c.text.lower())
                    for s in subjects:
                        claim(sent, s, "be", c, status, "copula", obj_key=key)
    return list(spans.values()), claims
