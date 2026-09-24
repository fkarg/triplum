"""Concrete datasets and the built-in benchmark catalog, independent of evaluation metrics.

Import the catalog from `triplum.datasets.registry` and the source machinery from
`triplum.datasets.base`; this package initialiser stays import-light so `bench.inputs` can use
the collators without a cycle."""

from triplum.datasets.frames import FrameDataset

__all__ = ["FrameDataset"]
