from triplum.bench import fingerprint as fp
from triplum.retrieve import pipelines


def test_pipelines_have_distinct_module_sets_and_stable_hashes():
    assert fp.code_hash("bm25") == fp.code_hash("bm25")
    assert fp.code_hash("bm25") == fp.code_hash("closed_book")  # same modules
    assert fp.code_hash("dense") != fp.code_hash("bm25")
    assert fp.code_hash("hybrid") != fp.code_hash("dense")
    assert fp.code_hash("rrf") == fp.code_hash("dense")  # same components, no reranker
    assert set(fp.PIPELINE_MODULES) == set(pipelines.NAMES) | {"graph", "extract"}
    assert fp.code_hash("extract") != fp.code_hash("graph")  # the scorer is not in the graph


def test_every_listed_module_resolves_to_a_file():
    for name in fp.PIPELINE_MODULES:
        paths = fp.source_paths(name)
        assert all(p.exists() for p in paths) and len(paths) >= len(fp.PIPELINE_MODULES[name])
    assert any(p.name == "migrations.sql" for p in fp.source_paths("bm25"))


def test_every_adapter_module_is_fingerprinted():
    """A change to any LLM, embedder or reranker adapter (fake ones included) or to the factories
    that assemble them can change answers, so it must change the hybrid pipeline's code hash."""
    import pkgutil

    import triplum.embed
    import triplum.llm
    import triplum.rerank

    listed = set(fp.PIPELINE_MODULES["hybrid"])
    for pkg in (triplum.llm, triplum.embed, triplum.rerank):
        for info in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
            assert info.name in listed, info.name
    assert "triplum.bench.factories" in set(fp.PIPELINE_MODULES["closed_book"])


def test_every_extract_module_is_in_the_graph_identity():
    import pkgutil

    import triplum.extract

    listed = set(fp.GRAPH)
    for info in pkgutil.iter_modules(triplum.extract.__path__, triplum.extract.__name__ + "."):
        if info.name != "triplum.extract.fake":
            assert info.name in listed, info.name
