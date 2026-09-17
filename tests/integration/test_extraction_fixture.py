"""The extraction run end to end on the committed fixtures with the rules extractor."""

from dataclasses import replace

import pytest
from triplum.bench.cli import main
from triplum.bench.config import ExtractConfig, ExtractorConfig
from triplum.bench.report import extraction_summary
from triplum.bench.runner import run_extraction
from triplum.bench.runstore import RunStore
from triplum.extract.protocol import ResolverSpec

pytest.importorskip("spacy")
pytest.importorskip("en_core_web_sm")

# metaqa is left out: its verbalised chunks take spaCy half a minute; `bench extract` covers it.
DATASETS = ["carb", "conll04", "scierc", "genwiki", "twowiki"]


def _cfg(tmp_path, dataset, **kw):
    return ExtractConfig(
        dataset=dataset,
        fixture=True,
        store_path=str(tmp_path / f"{dataset}.sqlite"),
        runstore_path=str(tmp_path / "runs.db"),
        cache_root=str(tmp_path / "cache"),
        **kw,
    )


@pytest.mark.parametrize("dataset", DATASETS)
def test_rules_extraction_scores_every_fixture(tmp_path, dataset):
    rid = run_extraction(_cfg(tmp_path, dataset, resolver=ResolverSpec("exact")))
    with RunStore(tmp_path / "runs.db") as rs:
        row = rs.run(rid)
        x = rs.extraction(rid)
        stages = set(rs.events(rid)["stage"])
    assert row is not None and x is not None
    assert row["status"] == "ok" and row["kind"] == "extract" and row["pipeline"] is None
    assert x["n_gold"] > 0 and x["facts"] > 0 and x["graph_written"] == 1
    assert x["partial_recall"] >= x["exact_recall"] >= 0
    assert x["chunks_per_s"] is not None and x["chunks_per_s"] > 0
    assert {"index.documents", "extract", "resolve", "index.graph", "score"} <= stages
    if dataset in ("conll04", "scierc"):
        assert x["span_f1"] is not None
    if dataset == "twowiki":
        assert x["exact_precision"] is None  # evidences are not exhaustive: recall only
    else:
        assert x["exact_precision"] is not None


def test_identity_lookup_and_graph_reuse(tmp_path):
    cfg = _cfg(tmp_path, "carb")
    first = run_extraction(cfg)
    assert run_extraction(cfg) == first
    forced = run_extraction(replace(cfg, force=True))
    assert forced != first
    with RunStore(tmp_path / "runs.db") as rs:
        a, b = rs.extraction(first), rs.extraction(forced)
        assert a is not None and b is not None
        assert b["graph_written"] == 0  # same graph identity: the store already holds it
        assert b["chunks_per_s"] is None  # served from the per-chunk cache: no throughput claim
        assert {
            k: v for k, v in a.items() if k not in ("run_id", "chunks_per_s", "graph_written")
        } == {k: v for k, v in b.items() if k not in ("run_id", "chunks_per_s", "graph_written")}
        assert rs.events(forced).filter(rs.events(forced)["stage"] == "extract")["cached"][0] == 1
        # a different resolver is a different graph identity on the same store: refused
    with pytest.raises(RuntimeError, match="holds graph"):
        run_extraction(replace(cfg, resolver=ResolverSpec("exact")))


def test_small_model_needs_a_vocabulary(tmp_path):
    with pytest.raises(ValueError, match="relation vocabulary"):
        run_extraction(_cfg(tmp_path, "carb", extractor=ExtractorConfig(kind="small_model")))


def test_cli_extract_and_report(tmp_path, capsys):
    common = [
        "--fixture",
        "--runstore",
        str(tmp_path / "runs.db"),
        "--cache-root",
        str(tmp_path / "cache"),
    ]
    assert main(["bench", "extract", "--dataset", "conll04", "--resolver", "exact", *common]) == 0
    out = capsys.readouterr().out
    assert "exact_recall" in out and "extractor=rules" in out
    assert main(["bench", "report", "--runstore", str(tmp_path / "runs.db")]) == 0
    assert "resolver=exact" in capsys.readouterr().out
    with RunStore(tmp_path / "runs.db") as rs:
        assert extraction_summary(rs).height == 1
