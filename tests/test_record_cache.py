import sys
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from triplum.cache import Cache, SQLiteBackend, cached
from triplum.datatype import Chunk, FingerprintedDataModel, Source
from triplum.utils.cache import content_key

COLLECTION = UUID("01900000-0000-7000-8000-000000000001")


class TextResult(FingerprintedDataModel):
    text: str


def _record(record_type: type[Source | Chunk], text: str) -> Source | Chunk:
    """A fresh record with `text`; equal arguments give an equal record."""
    source = Source(collection_id=COLLECTION, origin="a.md", text=text)
    if record_type is Source:
        return source
    return Chunk(
        collection_id=COLLECTION,
        source_id=source.id,
        origin=source.origin,
        ordinal=0,
        start=0,
        text=text,
    )


@pytest.mark.parametrize("record_type", [Source, Chunk])
def test_record_inputs_reuse_detached_results_after_reopen(
    tmp_path: Path, record_type: type[Source | Chunk]
):
    first = _record(record_type, "abc")
    equivalent = _record(record_type, "abc")
    calls = 0
    path = tmp_path / "cache.sqlite"
    process = content_key("record-uppercase", {})
    with Cache(SQLiteBackend(path)) as cache:

        @cached(cache=cache, process_id=process)
        def uppercase(item: Source | Chunk) -> TextResult:
            nonlocal calls
            calls += 1
            return TextResult(text=item.text.upper())

        assert uppercase(first) == TextResult(text="ABC")
        assert uppercase(equivalent) == TextResult(text="ABC")
        assert calls == 1
        changed = _record(record_type, "def")
        assert uppercase(changed) == TextResult(text="DEF")
        assert calls == 2

    with Cache(SQLiteBackend(path)) as cache:

        @cached(cache=cache, process_id=process)
        def reopened(item: Source | Chunk) -> TextResult:
            raise AssertionError("persisted record-input result should be reused")

        assert reopened(first) == TextResult(text="ABC")
        assert reopened(changed) == TextResult(text="DEF")


@pytest.mark.parametrize("record_type", [Source, Chunk])
def test_traced_record_inputs_admit_and_reuse_detached_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_type: type[Source | Chunk]
):
    first = _record(record_type, "abc")
    equivalent = _record(record_type, "abc")
    calls: list[str] = []
    for _ in range(2):
        with Cache(SQLiteBackend(tmp_path / "traced.sqlite")) as cache:
            module = ModuleType("traced_record_application")
            vars(module).update(cache=cache, calls=calls)
            monkeypatch.setitem(sys.modules, module.__name__, module)
            application = """from triplum.cache import cached
from triplum.datatype import Chunk, FingerprintedDataModel, Source
class Result(FingerprintedDataModel):
    text: str
@cached(cache=cache, dependency_mode="traced")
def operation(item: Source | Chunk) -> Result:
    calls.append(item.text)
    return Result(text=item.text.upper())
"""
            exec(  # noqa: S102 - controlled application fixture
                compile(application, "/application/traced_record_application.py", "exec"),
                vars(module),
            )
            assert module.operation(first).text == "ABC"
            assert module.operation(equivalent).text == "ABC"
            assert calls == ["abc"]
