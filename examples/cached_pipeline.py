"""Run with `uv run python examples/cached_pipeline.py`.

A deliberately cheap pipeline demonstrates correctness, not a cache speedup. Both
stages share one cache. Different normalization computations can yield identical
text, letting downstream analysis reuse its result. In production, opt in where
reuse is useful; ordinary functions remain ordinary uncached steps.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import ConfigDict

from triplum.cache import Cache, CachedStep, SQLiteBackend, cached
from triplum.datatype import FingerprintedDataModel
from triplum.utils.fingerprint import definition_hash


class Text(FingerprintedDataModel):
    model_config = ConfigDict(frozen=True)
    text: str
    observed_at: int = 0

    fingerprint_exclude = frozenset({"observed_at"})


class Analysis(FingerprintedDataModel):
    model_config = ConfigDict(frozen=True)
    words: tuple[str, ...]


class Normalize(CachedStep[Text, Text]):
    def __init__(self, cache: Cache, mode: Literal["lower", "casefold"]) -> None:
        super().__init__(cache=cache, output_type=Text)
        self.mode = mode
        self.calls = 0

    def fingerprint_config(self) -> dict[str, object]:
        return {"mode": self.mode}

    def compute(self, item: Text, /) -> Text:
        self.calls += 1
        text = item.text.lower() if self.mode == "lower" else item.text.casefold()
        return Text(text=text.strip())


def analyze_text(item: Text) -> Analysis:
    return Analysis(words=tuple(item.text.split()))


def demonstrate(path: Path) -> dict[str, int]:
    counts = {"analysis_computations": 0, "reopened_analysis_computations": 0}
    process_id = definition_hash(analyze_text)
    with Cache(SQLiteBackend(path), pending_bytes=1024 * 1024) as cache:
        lower = Normalize(cache, "lower")
        casefold = Normalize(cache, "casefold")

        @cached(cache=cache, process_id=process_id, output_type=Analysis)
        def analyze(item: Text) -> Analysis:
            counts["analysis_computations"] += 1
            return analyze_text(item)

        a = Text(text=" Hello World ", observed_at=1)
        b = Text(text=" A Different Input ", observed_at=2)
        first = analyze(lower(a))
        assert first == Analysis(words=("hello", "world"))
        assert analyze(lower(b)) == Analysis(words=("a", "different", "input"))
        # A → B → A and a different observation time still reuse A.
        assert analyze(lower(a.model_copy(update={"observed_at": 3}))) == first
        # Different upstream computation, same immediate value: downstream reuse.
        assert analyze(casefold(a)) == first
        counts["lowercase_computations"] = lower.calls
        counts["casefold_computations"] = casefold.calls

    # Context exit drains accepted writes. A new owner can reuse the same storage.
    with Cache(SQLiteBackend(path), pending_bytes=1024 * 1024) as cache:

        @cached(cache=cache, process_id=process_id, output_type=Analysis)
        def reopened(item: Text) -> Analysis:
            counts["reopened_analysis_computations"] += 1
            return analyze_text(item)

        assert reopened(Text(text="hello world")) == first
    return counts


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        print(json.dumps(demonstrate(Path(directory) / "cache.sqlite"), sort_keys=True))
