"""Text-to-triple gold for the KG-construction variants; no questions, so `bench run` refuses them
and the triple-recall metric is still to come. Documents are keyed `<name>:<split>:<index>` on
line-aligned or record-aligned files; each set's corpus and triples decode the same files on
their own first use.

- GraphJudge corpora (repo MIT): GenWiki-Hard (CC0), SciERC (no licence declared) and a REBEL
  subset (upstream CC BY-NC-SA 4.0, research only), each a passage per line paired with its gold
  triples; test and train splits.
- GenWiki (CC0): entity-masked Wikipedia sentences with DBpedia-label triples; `genwiki` is the
  1,000-record test set and `genwiki_fine` the 757k fine-grained training set, both from one zip.
- CaRB (MIT): open-IE tuples per sentence, loaded as (first argument, predicate, remaining
  arguments).
- CoNLL04 (no licence declared on the HF card) and SciERC SpERT files (no licence declared):
  typed entity spans and typed relations between them; entity spans stay in `documents.metadata`.
"""

from __future__ import annotations

import ast
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import Document
from triplum.datasets import base
from triplum.datasets.base import Entry, ListSource, passage
from triplum.datasets.files import File, manifest_files
from triplum.eval.inputs import GoldMappingError, Triple
from triplum.settings import Settings

# A raw record: (document id, title, text, metadata, triples as (s, p, o))
Record = tuple[str, str, str, dict[str, Any], list[tuple[str, str, str]]]


def _triples_line(line: str) -> list:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return ast.literal_eval(line)


def _graphjudge(name: str, paths: dict[str, Path]) -> list[Record]:
    records: list[Record] = []
    for split in ("test", "train"):
        source = next(p for k, p in paths.items() if k.endswith(f"{split}.source"))
        target = next(p for k, p in paths.items() if k.endswith(f"{split}.target"))
        graphs = source.read_text(encoding="utf-8").splitlines()
        texts = target.read_text(encoding="utf-8").splitlines()
        if len(graphs) != len(texts):
            raise GoldMappingError(
                f"{name}: {split} has {len(graphs)} graphs for {len(texts)} passages"
            )
        for i, (graph, text) in enumerate(zip(graphs, texts)):
            tuples = _triples_line(graph)
            # GenWiki-Hard has a few hundred 1-, 2-, 4- and 5-tuples; they stay in metadata.
            odd = [t for t in tuples if len(t) != 3]
            meta = {"split": split, **({"non_triples": odd} if odd else {})}
            triples = [(s, p, o) for s, p, o in (t for t in tuples if len(t) == 3)]
            records.append((f"{name}:{split}:{i}", "", text, meta, triples))
    return records


def _genwiki(name: str, prefix: str, paths: dict[str, Path]) -> list[Record]:
    (path,) = paths.values()
    records: list[Record] = []
    with zipfile.ZipFile(path) as zf:
        members = sorted(m for m in zf.namelist() if m.startswith(prefix) and m.endswith(".json"))
        i = 0
        for member in members:
            for r in json.loads(zf.read(member).decode("utf-8")):
                text = r["text"]
                for j, entity in enumerate(r["entities"]):
                    text = text.replace(f"<ENT_{j}>", entity)
                meta = {
                    "masked_text": r["text"],
                    "entities": r["entities"],
                    "id_long": r["id_long"],
                }
                title = r["id_long"]["wikipage"].replace("_", " ")
                records.append((f"{name}:{i}", title, text, meta, [tuple(t) for t in r["graph"]]))
                i += 1
    return records


def _carb(paths: dict[str, Path]) -> list[Record]:
    by_key: dict[tuple[str, str], Record] = {}
    for split in ("dev", "test"):
        path = next(p for k, p in paths.items() if k.endswith(f"{split}.tsv"))
        for line in path.read_text(encoding="utf-8").splitlines():
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            sentence, predicate, args = cols[0], cols[1], cols[2:]
            key = (split, sentence)
            if key not in by_key:
                by_key[key] = (f"carb:{split}:{len(by_key)}", "", sentence, {"split": split}, [])
            by_key[key][4].append((args[0], predicate, " ".join(args[1:])))
    return list(by_key.values())


def _spans(name: str, split: str, rows) -> list[Record]:
    records: list[Record] = []
    for i, r in enumerate(rows):
        tokens = list(r["tokens"])
        entities = [
            {
                "text": " ".join(tokens[e["start"] : e["end"]]),
                "type": e["type"],
                "start": e["start"],
                "end": e["end"],
            }
            for e in r["entities"]
        ]
        triples = [
            (entities[rel["head"]]["text"], rel["type"], entities[rel["tail"]]["text"])
            for rel in r["relations"]
        ]
        meta = {"split": split, "entities": entities, "orig_id": r["orig_id"]}
        records.append((f"{name}:{split}:{i}", "", " ".join(tokens), meta, triples))
    return records


def _conll04(paths: dict[str, Path]) -> list[Record]:
    records = []
    for split in ("train", "validation", "test"):
        path = next(p for k, p in paths.items() if k.endswith(f"{split}-00000-of-00001.parquet"))
        records += _spans("conll04", split, base.parquet_rows(path))
    return records


def _scierc(paths: dict[str, Path]) -> list[Record]:
    records = []
    for split in ("train", "dev", "test"):
        path = next(p for k, p in paths.items() if k.endswith(f"scierc_{split}.json"))
        records += _spans("scierc", split, base.read_json(path))
    return records


READERS: dict[str, Callable[[dict[str, Path]], list[Record]]] = {
    "graphjudge_genwiki": lambda p: _graphjudge("graphjudge_genwiki", p),
    "graphjudge_scierc": lambda p: _graphjudge("graphjudge_scierc", p),
    "graphjudge_rebel": lambda p: _graphjudge("graphjudge_rebel", p),
    "genwiki": lambda p: _genwiki("genwiki", "genwiki/test/", p),
    "genwiki_fine": lambda p: _genwiki("genwiki_fine", "genwiki/train/fine/", p),
    "carb": _carb,
    "conll04": _conll04,
    "scierc": _scierc,
}


def pinned(name: str) -> tuple[File, ...]:
    if name.startswith("graphjudge_"):
        folder = {"genwiki": "GenWiki-Hard", "scierc": "SCIERC", "rebel": "rebel_sub"}[
            name.split("_", 1)[1]
        ]
        return tuple(f for f in manifest_files("graphjudge") if folder in f.name)
    if name.startswith("genwiki"):
        return manifest_files("genwiki")
    return manifest_files(name)


class Corpus(ListSource[Record, Document]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or pinned(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[Record]:
        return READERS[self.name](paths)

    def record(self, raw: Record, index: int) -> Document:
        did, title, text, meta, _ = raw
        return passage(did, self.name, title, text, metadata=meta)


class Triples(ListSource[tuple[str, str, str, str], Triple]):
    def __init__(
        self, name: str, settings: Settings | None = None, files: tuple[File, ...] | None = None
    ) -> None:
        self.name = name
        super().__init__(files or pinned(name), settings, {"name": name})

    def read(self, paths: dict[str, Path]) -> list[tuple[str, str, str, str]]:
        return [(did, s, p, o) for did, _, _, _, ts in READERS[self.name](paths) for s, p, o in ts]

    def record(self, raw: tuple[str, str, str, str], index: int) -> Triple:
        did, s, p, o = raw
        return Triple(subject=s, predicate=p, object=o, document_id=did)


def _entry(name: str, licence: str, fixture: bool = True) -> Entry:
    return Entry(
        name=name,
        family="extraction",
        licence=licence,
        fixture=fixture,
        build=lambda s: Benchmark(name=name, corpus=Corpus(name, s), extraction=Triples(name, s)),
    )


ENTRIES = (
    _entry("graphjudge_genwiki", "MIT repo; GenWiki CC0 1.0"),
    _entry("graphjudge_scierc", "MIT repo; SciERC none declared"),
    _entry("graphjudge_rebel", "MIT repo; REBEL CC BY-NC-SA 4.0 (research only)"),
    _entry("genwiki", "CC0 1.0"),
    _entry("genwiki_fine", "CC0 1.0", fixture=False),
    _entry("carb", "MIT"),
    _entry("conll04", "none declared (HF DFKI-SLT/conll04)"),
    _entry("scierc", "none declared (SpERT release)"),
)
