# operations of form A -> Source
# i.e. for items from dataset[A] to be converted to Source objects for standardized chunking and embedding
from abc import abstractmethod
from pathlib import Path
from typing import Protocol

from triplum.datatype import Source
from triplum.utils.fingerprint import Fingerprinted


class Converter[A](Protocol):
    """Turn one dataset item into zero or more sources (an archive may hold several)."""

    @abstractmethod
    def __call__(self, item: A, /) -> list[Source]: ...


class Utf8File(Converter[Path], Fingerprinted):
    """Read a file as UTF-8 text, keeping newlines unchanged; `origin` is the path."""

    def fingerprint_config(self) -> dict[str, object]:
        return {}

    def __call__(self, item: Path, /) -> list[Source]:
        return [Source(origin=str(item), text=item.read_bytes().decode("utf-8"))]
