"""Text-to-triple gold for the KG-construction variants; no questions, so `bench run` refuses them
and the triple-recall metric is still to come.

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
from pathlib import Path

import polars as pl

from triplum.bench.inputs import Benchmark
from triplum.data.corpus import CorpusBatch
from triplum.datasets import base
from triplum.datasets.base import Spec
from triplum.datasets.corpus import CorpusDataset
from triplum.datasets.frames import FrameDataset
from triplum.eval.inputs import ExtractionEvaluation


def _frames(source: str, passages: list, triples: list) -> Benchmark:
    return Benchmark(
        corpus=CorpusDataset(CorpusBatch(*base.corpus_frames(source, passages))),
        extraction=ExtractionEvaluation(FrameDataset(base.triples_frame(triples))),
    )


def _triples_line(line: str) -> list:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return ast.literal_eval(line)


def parse_graphjudge(name: str, paths: dict[str, Path], n: int | None) -> Benchmark:
    passages, triples = [], []
    for split in ("test", "train"):
        source = next(p for k, p in paths.items() if k.endswith(f"{split}.source"))
        target = next(p for k, p in paths.items() if k.endswith(f"{split}.target"))
        graphs = source.read_text(encoding="utf-8").splitlines()
        texts = target.read_text(encoding="utf-8").splitlines()
        if len(graphs) != len(texts):
            raise base.GoldMappingError(
                f"{name}: {split} has {len(graphs)} graphs for {len(texts)} passages"
            )
        for i, (graph, text) in enumerate(zip(graphs, texts)):
            doc_id = f"{name}:{split}:{i}"
            tuples = _triples_line(graph)
            # GenWiki-Hard has a few hundred 1-, 2-, 4- and 5-tuples; they stay in metadata.
            odd = [t for t in tuples if len(t) != 3]
            meta = {"split": split, **({"non_triples": odd} if odd else {})}
            passages.append((doc_id, "", text, 0, meta))
            triples.extend((None, doc_id, *t) for t in tuples if len(t) == 3)
    return _frames(name, passages, triples)


def _genwiki_records(zf: zipfile.ZipFile, members: list[str]):
    for member in members:
        yield from json.loads(zf.read(member).decode("utf-8"))


def parse_genwiki(name: str, prefix: str, paths: dict[str, Path], n: int | None) -> Benchmark:
    (path,) = paths.values()
    passages, triples = [], []
    with zipfile.ZipFile(path) as zf:
        members = sorted(m for m in zf.namelist() if m.startswith(prefix) and m.endswith(".json"))
        for i, r in enumerate(_genwiki_records(zf, members)):
            text = r["text"]
            for j, entity in enumerate(r["entities"]):
                text = text.replace(f"<ENT_{j}>", entity)
            doc_id = f"{name}:{i}"
            meta = {"masked_text": r["text"], "entities": r["entities"], "id_long": r["id_long"]}
            passages.append((doc_id, r["id_long"]["wikipage"].replace("_", " "), text, 0, meta))
            triples.extend((None, doc_id, s, p, o) for s, p, o in r["graph"])
    return _frames(name, passages, triples)


def parse_carb(paths: dict[str, Path], n: int | None) -> Benchmark:
    passages, triples = [], []
    seen: dict[tuple[str, str], str] = {}
    for split in ("dev", "test"):
        path = next(p for k, p in paths.items() if k.endswith(f"{split}.tsv"))
        for line in path.read_text(encoding="utf-8").splitlines():
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            sentence, predicate, args = cols[0], cols[1], cols[2:]
            key = (split, sentence)
            if key not in seen:
                seen[key] = f"carb:{split}:{len(seen)}"
                passages.append((seen[key], "", sentence, 0, {"split": split}))
            triples.append((None, seen[key], args[0], predicate, " ".join(args[1:])))
    return _frames("carb", passages, triples)


def _spans(name: str, split: str, records, passages: list, triples: list) -> None:
    for i, r in enumerate(records):
        tokens = list(r["tokens"])
        doc_id = f"{name}:{split}:{i}"
        entities = [
            {
                "text": " ".join(tokens[e["start"] : e["end"]]),
                "type": e["type"],
                "start": e["start"],
                "end": e["end"],
            }
            for e in r["entities"]
        ]
        passages.append(
            (
                doc_id,
                "",
                " ".join(tokens),
                0,
                {"split": split, "entities": entities, "orig_id": r["orig_id"]},
            )
        )
        triples.extend(
            (
                None,
                doc_id,
                entities[rel["head"]]["text"],
                rel["type"],
                entities[rel["tail"]]["text"],
            )
            for rel in r["relations"]
        )


def parse_conll04(paths: dict[str, Path], n: int | None) -> Benchmark:
    passages, triples = [], []
    for split in ("train", "validation", "test"):
        path = next(p for k, p in paths.items() if k.endswith(f"{split}-00000-of-00001.parquet"))
        _spans("conll04", split, pl.read_parquet(path).iter_rows(named=True), passages, triples)
    return _frames("conll04", passages, triples)


def parse_scierc(paths: dict[str, Path], n: int | None) -> Benchmark:
    passages, triples = [], []
    for split in ("train", "dev", "test"):
        path = next(p for k, p in paths.items() if k.endswith(f"scierc_{split}.json"))
        _spans("scierc", split, json.loads(path.read_text(encoding="utf-8")), passages, triples)
    return _frames("scierc", passages, triples)


def _graphjudge_spec(name: str, folder: str, licence: str) -> Spec:
    files = tuple(f for f in base.manifest_files("graphjudge") if folder in f.name)
    return Spec(
        name, "extraction", files, licence, lambda paths, n: parse_graphjudge(name, paths, n)
    )


_genwiki_files = base.manifest_files("genwiki")
SPECS = (
    _graphjudge_spec("graphjudge_genwiki", "GenWiki-Hard", "MIT repo; GenWiki CC0 1.0"),
    _graphjudge_spec("graphjudge_scierc", "SCIERC", "MIT repo; SciERC none declared"),
    _graphjudge_spec(
        "graphjudge_rebel", "rebel_sub", "MIT repo; REBEL CC BY-NC-SA 4.0 (research only)"
    ),
    Spec(
        "genwiki",
        "extraction",
        _genwiki_files,
        "CC0 1.0",
        lambda paths, n: parse_genwiki("genwiki", "genwiki/test/", paths, n),
    ),
    Spec(
        "genwiki_fine",
        "extraction",
        _genwiki_files,
        "CC0 1.0",
        lambda paths, n: parse_genwiki("genwiki_fine", "genwiki/train/fine/", paths, n),
        fixture=False,
    ),
    Spec("carb", "extraction", base.manifest_files("carb"), "MIT", parse_carb),
    Spec(
        "conll04",
        "extraction",
        base.manifest_files("conll04"),
        "none declared (HF DFKI-SLT/conll04)",
        parse_conll04,
    ),
    Spec(
        "scierc",
        "extraction",
        base.manifest_files("scierc"),
        "none declared (SpERT release)",
        parse_scierc,
    ),
)
