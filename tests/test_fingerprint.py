import importlib.util
import sys
from pathlib import Path

import pytest

from triplum.datatype import Chunk, Source
from triplum.steps.chunking import FixedSize
from triplum.steps.embedding import ZeroEmbedder
from triplum.utils.fingerprint import Fingerprinted


def test_record_fingerprint_ignores_id_and_follows_content():
    a = Source(origin="a.md", text="abc")
    assert Source(origin="a.md", text="abc").fingerprint == a.fingerprint
    assert Source(origin="a.md", text="abd").fingerprint != a.fingerprint
    assert "fingerprint" in a.model_dump()

    chunk = Chunk(source_id=a.id, origin="a.md", start=0, text="ab")
    other_source = Source(origin="x", text="y")
    assert Chunk(source_id=other_source.id, origin="a.md", start=0, text="ab").fingerprint == (
        chunk.fingerprint
    )


def test_object_fingerprint_covers_class_and_state():
    assert FixedSize(3).fingerprint() == FixedSize(3).fingerprint()
    assert FixedSize(3).fingerprint() != FixedSize(4).fingerprint()
    assert ZeroEmbedder(3).fingerprint() != FixedSize(3).fingerprint()


class _Uses(Fingerprinted):
    def __init__(self, inner: object) -> None:
        self.inner = inner


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
        "from triplum.utils.fingerprint import Fingerprinted\n\n"
        "class Step(Fingerprinted):\n"
        '    """{doc}"""\n\n'
        "    def __call__(self):\n"
        "        return {value}  # {comment}\n"
    )
    fingerprints = []
    for i, (doc, value, comment) in enumerate([("a", 1, "x"), ("b", 1, "y"), ("a", 2, "x")]):
        path = tmp_path / f"step_{i}.py"
        path.write_text(template.format(doc=doc, value=value, comment=comment))
        fingerprints.append(_load(path, "step", monkeypatch).Step().fingerprint())
    assert fingerprints[0] == fingerprints[1]  # docstrings and comments do not count
    assert fingerprints[0] != fingerprints[2]


def test_class_without_source_is_refused():
    namespace: dict = {}
    source = "class Step(Fingerprinted):\n    pass\n"
    exec(source, {"Fingerprinted": Fingerprinted}, namespace)  # noqa: S102 - a class with no file
    with pytest.raises(TypeError, match="source is unavailable"):
        namespace["Step"]().fingerprint()
