"""The datasets triplum can download, by name. Each entry lives beside its loader."""

from triplum.datasets import hotpotqa, multihoprag
from triplum.datasets.files import DatasetEntry

CATALOGUE: dict[str, DatasetEntry] = {
    entry.name: entry for entry in (hotpotqa.ENTRY, multihoprag.ENTRY)
}
