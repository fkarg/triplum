from triplum.bench import fingerprint as fp


def test_pipelines_have_distinct_module_sets_and_stable_hashes():
    assert fp.code_hash("bm25") == fp.code_hash("bm25")
    assert fp.code_hash("bm25") == fp.code_hash("closed_book")  # same modules
    assert fp.code_hash("dense") != fp.code_hash("bm25")
    assert fp.code_hash("hybrid") != fp.code_hash("dense")


def test_every_listed_module_resolves_to_a_file():
    for name in fp.PIPELINE_MODULES:
        paths = fp.source_paths(name)
        assert all(p.exists() for p in paths) and len(paths) >= len(fp.BASE)
    assert any(p.name == "migrations.sql" for p in fp.source_paths("bm25"))
