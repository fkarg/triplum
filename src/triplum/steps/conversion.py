# operations of form A -> Source
# i.e. for items from dataset[A] to be converted to Source objects for standardized chunking and embedding
from abc import abstractmethod
from pathlib import Path
from typing import Protocol
from uuid import UUID

from triplum.datatype import Source
from triplum.utils.fingerprint import FingerprintedComputationMixin


class Converter[A](Protocol):
    """Turn one dataset item into zero or more sources (an archive may hold several)."""

    @abstractmethod
    def __call__(self, item: A, /) -> list[Source]: ...


class Utf8File(Converter[Path], FingerprintedComputationMixin):
    """Read a file as UTF-8 text, keeping newlines unchanged; `origin` is the path.

    Sources belong to the collection `collection_id`.
    """

    def __init__(self, *, collection_id: UUID) -> None:
        self.collection_id = collection_id

    def fingerprint_config(self) -> dict[str, object]:
        return {"collection_id": str(self.collection_id)}

    def __call__(self, item: Path, /) -> list[Source]:
        text = item.read_bytes().decode("utf-8")
        return [Source(collection_id=self.collection_id, origin=str(item), text=text)]
