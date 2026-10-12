import importlib.util
import sys
from pathlib import Path

import pytest

from triplum.datatype import Chunk, FingerprintedDataModel, Source
from triplum.steps.chunking import FixedSize
from triplum.steps.embedding import ZeroEmbedder
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import FingerprintedComputationMixin, source_hash


def test_source_fingerprint_ignores_id_and_follows_content():
    source = Source(origin="a.md", text="abc")
    original = source.fingerprint()
    assert original == content_key("source", ["a.md", "abc"])
    assert Source(origin="a.md", text="abc").fingerprint() == original
    source.text = "abd"
    assert source.fingerprint() != original
    source.text = "abc"
    source.origin = "b.md"
    assert source.fingerprint() != original


def test_chunk_fingerprint_ignores_ids_and_follows_content():
    source = Source(origin="a.md", text="abc")
    chunk = Chunk(source_id=source.id, origin="a.md", start=0, text="ab")
    original = chunk.fingerprint()
    assert original == content_key("chunk", ["a.md", 0, "ab"])
    other_source = Source(origin="a.md", text="abc")
    assert (
        Chunk(source_id=other_source.id, origin="a.md", start=0, text="ab").fingerprint()
        == original
    )
    chunk.text = "ac"
    assert chunk.fingerprint() != original
    chunk.text = "ab"
    chunk.start = 1
    assert chunk.fingerprint() != original
    chunk.start = 0
    chunk.origin = "b.md"
    assert chunk.fingerprint() != original


def test_nested_records_use_their_fingerprints():
    class Bundle(FingerprintedDataModel):
        source: Source
        chunk: Chunk

    source = Source(origin="a.md", text="abc")
    chunk = Chunk(source_id=source.id, origin="a.md", start=0, text="ab")
    original = Bundle(source=source, chunk=chunk).fingerprint()
    other = Source(origin="a.md", text="abc")
    same = Bundle(source=other, chunk=Chunk(source_id=other.id, origin="a.md", start=0, text="ab"))
    assert same.fingerprint() == original
    same.chunk.text = "ac"
    assert same.fingerprint() != original


def test_object_fingerprint_covers_class_and_state():
    assert FixedSize(3).fingerprint() == FixedSize(3).fingerprint()
    assert FixedSize(3).fingerprint() != FixedSize(4).fingerprint()
    assert ZeroEmbedder(3).fingerprint() != FixedSize(3).fingerprint()


class _Uses(FingerprintedComputationMixin):
    def __init__(self, inner: object) -> None:
        self.inner = inner

    def fingerprint_config(self) -> dict[str, object]:
        return {"inner": self.inner}


def test_nested_fingerprints_and_unsupported_state():
    assert _Uses(FixedSize(3)).fingerprint() != _Uses(FixedSize(4)).fingerprint()
    assert _Uses({"k": [1, Path("p")]}).fingerprint() == _Uses({"k": [1, Path("p")]}).fingerprint()
    with pytest.raises(TypeError, match="cannot fingerprint"):
        _Uses(object()).fingerprint()


def _load(path: Path, name: str, monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_code_changes_change_the_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    template = (
        "from triplum.utils.fingerprint import FingerprintedComputationMixin, source_hash\n\n"
        "class Step(FingerprintedComputationMixin):\n"
        '    """{doc}"""\n\n'
        "    def fingerprint_config(self):\n"
        "        return {{}}\n"
        "    def __call__(self):\n"
        "        return {value}  # {comment}\n"
    )
    fingerprints = []
    sources = []
    for i, (doc, value, comment) in enumerate([("a", 1, "x"), ("b", 1, "y"), ("a", 2, "x")]):
        path = tmp_path / f"step_{i}.py"
        path.write_text(template.format(doc=doc, value=value, comment=comment))
        cls = _load(path, "step", monkeypatch).Step
        fingerprints.append(cls().fingerprint())
        sources.append(source_hash(cls))
    assert fingerprints[0] == fingerprints[1]  # docstrings and comments do not count
    assert fingerprints[0] != fingerprints[2]
    assert sources[0] == sources[1]
    assert sources[0] != sources[2]


def test_source_hash_without_source_is_refused():
    namespace: dict = {}
    source = "class Step(FingerprintedComputationMixin):\n    pass\n"
    exec(source, {"FingerprintedComputationMixin": FingerprintedComputationMixin}, namespace)  # noqa: S102 - a class with no file
    with pytest.raises(TypeError, match="source is unavailable"):
        source_hash(namespace["Step"])
