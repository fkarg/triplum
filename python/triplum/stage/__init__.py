"""Stages: plain functions with a data key, a trace-discovered code manifest, a published
artifact and an invocation record, so a rerun fetches what it can and recomputes exactly the
stages whose code or inputs changed. Spec: `docs/specs/2026-09-17-stages.md`."""

from .artifacts import Artifact, Stream
from .fingerprint import Manifest
from .identity import derive
from .run import Run, active, current, stage_seed
from .stage import LiveStream, Stage, stage

__all__ = [
    "Artifact",
    "LiveStream",
    "Manifest",
    "Run",
    "Stage",
    "Stream",
    "active",
    "current",
    "derive",
    "stage",
    "stage_seed",
]
