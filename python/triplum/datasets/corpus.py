"""A concrete corpus source for parsers that already produce canonical frames."""

from collections.abc import Iterator

from triplum.cache import content_key
from triplum.data.corpus import CorpusBatch
from triplum.datasets.frames import FrameDataset
from triplum.utils.data import IterableDataset


class CorpusDataset(IterableDataset[CorpusBatch]):
    """Expose an already prepared corpus as a source, keeping evaluation targets separate.

    This concrete implementation is eager. Streaming sources can subclass IterableDataset
    directly and yield CorpusBatch values without constructing a CorpusDataset.
    """

    def __init__(self, batch: CorpusBatch) -> None:
        self.batch = batch

    def __iter__(self) -> Iterator[CorpusBatch]:
        yield self.batch

    def fingerprint(self) -> str:
        return content_key("corpus", [FrameDataset(frame).fingerprint() for frame in self.batch])
