"""Extensible indexed/streaming datasets and lazy loaders; no task schema is imposed."""

from .dataset import Dataset, IterableDataset
from .loader import DataLoader

__all__ = ["DataLoader", "Dataset", "IterableDataset"]
