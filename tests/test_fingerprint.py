import importlib.util
import sys
from pathlib import Path
from uuid import UUID

import pytest

from triplum.datatype import Chunk, FingerprintedDataModel, Source
from triplum.steps.chunking import FixedSize
from triplum.steps.embedding import ZeroEmbedder
from triplum.utils.cache import content_key
from triplum.utils.fingerprint import FingerprintedComputationMixin, source_hash

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")
OTHER = UUID("01900000-0000-7000-8000-000000000002")


def test_source_fingerprint_follows_the_id_inputs():
    source = Source(collection_id=COLLECTION, origin="a.md", text="abc")
    original = source.fingerprint()
    assert original == content_key("source", [str(COLLECTION), "a.md", "abc"])
    assert Source(collection_id=COLLECTION, origin="a.md", text="abc").fingerprint() == original
    assert Source(collection_id=COLLECTION, origin="a.md", text="abd").fingerprint() != original
    assert Source(collection_id=COLLECTION, origin="b.md", text="abc").fingerprint() != original
    assert Source(collection_id=OTHER, origin="a.md", text="abc").fingerprint() != original


def _chunk(source: Source, ordinal: int = 0, start: int = 0, text: str = "ab") -> Chunk:
    return Chunk(
        collection_id=source.collection_id,
        source_id=source.id,
        origin=source.origin,
        ordinal=ordinal,
        start=start,
        text=text,
    )


def test_chunk_fingerprint_follows_the_id_inputs():
    source = Source(collection_id=COLLECTION, origin="a.md", text="abc")
    chunk = _chunk(source)
    original = chunk.fingerprint()
    assert original == content_key("chunk", [str(COLLECTION), str(source.id), 0, 0, "ab"])
    assert _chunk(Source(collection_id=COLLECTION, origin="a.md", text="abc")).fingerprint() == (
        original
    )
    assert _chunk(source, text="ac").fingerprint() != original
    assert _chunk(source, start=1).fingerprint() != original
    assert _chunk(source, ordinal=1).fingerprint() != original
    other_source = Source(collection_id=COLLECTION, origin="b.md", text="abc")
    assert _chunk(other_source).fingerprint() != original
    other_collection = Source(collection_id=OTHER, origin="a.md", text="abc")
    assert _chunk(other_collection).fingerprint() != original


def test_nested_records_use_their_fingerprints():
    class Bundle(FingerprintedDataModel):
        source: Source
        chunk: Chunk

    source = Source(collection_id=COLLECTION, origin="a.md", text="abc")
    original = Bundle(source=source, chunk=_chunk(source)).fingerprint()
    other = Source(collection_id=COLLECTION, origin="a.md", text="abc")
    assert Bundle(source=other, chunk=_chunk(other)).fingerprint() == original
    assert Bundle(source=other, chunk=_chunk(other, text="ac")).fingerprint() != original


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
