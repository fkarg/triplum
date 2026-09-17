"""What a stage is asked: the identity of each argument, the keys they compose to, and the
derived seeds. The argument table is the spec's; anything outside it is a `TypeError` at call
time, never a random key.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import polars as pl
from pydantic import BaseModel

from triplum.cache import content_key
from triplum.data.viewer import Viewer
from triplum.datasets.frames import FrameDataset
from triplum.stage.artifacts import Artifact
from triplum.stage.fingerprint import as_plain
from triplum.stage.run import current
from triplum.utils.data import Dataset, IterableDataset


def type_name(value: Any) -> str:
    t = type(value)
    return f"{t.__module__}:{t.__qualname__}"


def identity(value: Any) -> Any:
    """The JSON-ready identity of a stage argument. Plain data is itself; everything else is
    paired with its type, so a subclass with one overridden method is a different input."""
    ok, plain = as_plain(value)
    if ok:
        return plain
    key = artifact_key(value)
    if key is not None:
        return {"artifact": key}
    t = type_name(value)
    if isinstance(value, Viewer):
        # The as-of instants default to now and stay outside identity, as on the run record.
        return {
            "type": t,
            "principals": sorted(value.principals),
            "permission_revision": value.permission_revision,
        }
    if isinstance(value, (Dataset, IterableDataset)):
        return {"type": t, "fingerprint": value.fingerprint()}
    if isinstance(value, pl.DataFrame):
        return {"type": t, "frame": FrameDataset(value).fingerprint()}
    if (
        isinstance(value, dict)
        and value
        and all(isinstance(v, pl.DataFrame) for v in value.values())
    ):
        return {"type": t, "frames": {k: FrameDataset(v).fingerprint() for k, v in value.items()}}
    if isinstance(value, BaseModel):
        return {"type": t, "model": value.model_dump(mode="json")}
    if is_dataclass(value) and not isinstance(value, type):
        ok, plain = as_plain(asdict(value))
        if ok:
            return {"type": t, "dataclass": plain}
    own = getattr(value, "identity", None)
    if callable(own):
        return {"type": t, "identity": own()}
    spec = getattr(value, "spec", None)
    if spec is not None and callable(getattr(spec, "hash", None)):
        return {"type": t, "spec": spec.hash()}
    if isinstance(getattr(value, "adapter", None), str) and isinstance(
        getattr(value, "model", None), str
    ):
        return {"type": t, "llm": [value.adapter, value.model]}
    raise TypeError(f"{t} has no identity; pass a source, an artifact, a spec or plain data")


def artifact_key(value: Any) -> str | None:
    """The data key of an argument that is an artifact: an `Artifact`, a live or published
    stream, or a frame or record list a stage of this run produced or fetched. Identity by
    artifact key, never by type, so a live stream and its replay key the same."""
    if isinstance(value, Artifact):
        return value.key
    key = getattr(value, "artifact_key", None)
    if isinstance(key, str):
        return key
    run = current()
    if run is not None and (hit := run.produced_by(value)) is not None:
        return hit[0]
    return None


def seeded(arguments: dict[str, Any]) -> bool:
    """A stage is seeded when it takes `seed` or any argument declares itself seed-sensitive."""
    return "seed" in arguments or any(
        getattr(v, "seed_sensitive", False) is True for v in arguments.values()
    )


def derive(*parts: Any) -> int:
    """A 64-bit seed from a root and a path of names, so replicates and stages draw
    independently: `derive(root, replicate)`, then `derive(that, stage name)`."""
    return int(content_key("seed", list(parts))[:16], 16) >> 1  # 63 bits: fits SQLite
