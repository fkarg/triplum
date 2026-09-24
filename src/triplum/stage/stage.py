"""The stage wrapper: a plain function gains a data key, a code manifest, an artifact and an
invocation record. Without an active `Run` the wrapper is the function.

Lookup is by data key; the code axis is validated along the lineage: a candidate artifact is
fetched when its own manifest and every input artifact's manifest still hash the same in this
process. A stage returning a frame or a list of records publishes on return; one returning a
stream publishes as the consumer pulls, with discovery open until exhaustion; one annotated
`-> None` is a store effect and the store it takes records the effect under the key.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from typing import Any, cast

import polars as pl
from pydantic import BaseModel

from triplum.cache import canonical_json, content_key
from triplum.stage import artifacts, fingerprint, identity
from triplum.stage.artifacts import Artifact, Frames, Records, Writer
from triplum.stage.run import Run, current, seeded
from triplum.stage.trace import Recording
from triplum.utils.data import Dataset, IterableDataset

BATCH = 1024


class Stage[**P, R]:
    def __init__(self, fn: Callable[P, R]) -> None:
        self.fn = fn
        functools.update_wrapper(self, fn)
        self.name = f"{fn.__module__}:{getattr(fn, '__qualname__', repr(fn))}"
        self.signature = inspect.signature(fn)
        ann = self.signature.return_annotation
        self.effect = ann is None or ann is type(None) or ann == "None"

    def __repr__(self) -> str:
        return f"<stage {self.name}>"

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        run = current()
        if run is None:
            return self.fn(*args, **kwargs)
        bound = self.signature.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = dict(bound.arguments)
        seed = identity.derive(run.seed, self.name) if identity.seeded(arguments) else None
        if "seed" in arguments:
            arguments["seed"] = seed
            bound.arguments["seed"] = seed
        store = _effect_store(arguments) if self.effect else None
        keyed = {k: v for k, v in arguments.items() if k != "seed" and v is not store}
        inputs = [[k, identity.identity(v)] for k, v in keyed.items()]
        structural = content_key("stage", [self.name, inputs])
        key = structural if seed is None else content_key("stage", [structural, seed])
        call = _Call(self, run, bound, keyed, structural, key, seed, canonical_json(inputs))
        if self.effect:
            assert store is not None
            return cast("R", call.effect(store))
        return call.value()


def stage[**P, R](fn: Callable[P, R]) -> Stage[P, R]:
    """Wrap a plain function as a stage. `stage(fn).fn` is the function itself."""
    return Stage(fn)


def _effect_store(arguments: dict[str, Any]) -> Any:
    for v in arguments.values():
        if callable(getattr(v, "effect_complete", None)):
            return v
    raise TypeError("a stage annotated -> None is a store effect and must take a store")


def _artifact_of(run: Run, value: Any) -> tuple[str, str | None] | None:
    """(key, code) for an argument that is an artifact; the code is None while a live stream
    is still being produced."""
    if isinstance(value, Artifact):
        return value.key, value.code
    key = getattr(value, "artifact_key", None)
    if isinstance(key, str):
        return key, getattr(value, "artifact_code", None)
    return run.produced_by(value)


class _Call:
    """One invocation of a stage under a run."""

    def __init__(
        self,
        stage: Stage,
        run: Run,
        bound: inspect.BoundArguments,
        keyed: dict[str, Any],
        structural: str,
        key: str,
        seed: int | None,
        inputs_json: str,
    ) -> None:
        self.stage, self.run, self.bound, self.keyed = stage, run, bound, keyed
        self.structural, self.key, self.seed, self.inputs_json = structural, key, seed, inputs_json

    def start(self) -> int:
        return self.run.store.start_invocation(
            self.run.run_id,
            self.stage.name,
            self.structural,
            self.key,
            self.seed,
            self.run.replicate,
            self.inputs_json,
        )

    def record_inputs(self, inv: int) -> bool:
        """Write the input edges; False when an input is a live stream not yet complete, in
        which case this invocation's output has no addressable input and is not published."""
        rows = []
        complete = True
        for position, (name, value) in enumerate(self.keyed.items()):
            art = _artifact_of(self.run, value)
            if art is not None:
                rows.append((position, name, "artifact", art[0], art[1]))
                complete = complete and art[1] is not None
            elif isinstance(value, (Dataset, IterableDataset)):
                rows.append((position, name, "source", value.fingerprint(), None))
            elif callable(getattr(value, "identity", None)):
                rows.append((position, name, "store", value.identity(), None))
            elif isinstance(value, (BaseModel,)) or hasattr(value, "__dataclass_fields__"):
                rows.append(
                    (position, name, "config", canonical_json(identity.identity(value)), None)
                )
            elif hasattr(value, "spec") or hasattr(value, "adapter"):
                rows.append(
                    (position, name, "adapter", canonical_json(identity.identity(value)), None)
                )
            else:
                rows.append(
                    (position, name, "value", canonical_json(identity.identity(value)), None)
                )
        self.run.store.add_invocation_inputs(inv, rows)
        return complete

    def fetch(self) -> Artifact | None:
        for row in self.run.store.artifacts(self.key):
            if valid(self.run, self.key, row["code"], set()):
                art = artifacts.complete(self.run.root, row["stage"], self.key, row["code"])
                if art is not None:
                    return art
        return None

    def value(self) -> Any:
        art = self.fetch()
        if art is not None:
            inv = self.start()
            self.record_inputs(inv)
            self.run.store.finish_invocation(inv, status="ok", code=art.code, fetched=True)
            value = artifacts.read(self.run.root, art)
            self.run.register(value, art.key, art.code)
            return value
        inv = self.start()
        rec = Recording()
        try:
            with seeded(self.seed), rec:
                result = self.stage.fn(*self.bound.args, **self.bound.kwargs)
                inner = iter(result) if isinstance(result, (IterableDataset, Iterator)) else None
        except BaseException as e:
            self.run.store.finish_invocation(
                inv, status="failed", code=None, fetched=False, error=repr(e)
            )
            raise
        if inner is not None:
            return LiveStream(self, inv, rec, inner)
        manifest = fingerprint.build(rec.codes)
        self.run.store.put_manifest(manifest)
        writer = Writer(self.run.root, self.stage.name, self.key)
        try:
            if isinstance(result, pl.DataFrame):
                writer.frame(result)
            elif isinstance(result, dict) and all(
                isinstance(v, pl.DataFrame) for v in result.values()
            ):
                result = Frames(result)
                writer.frames(result)
            elif isinstance(result, list) and all(isinstance(r, BaseModel) for r in result):
                result = Records(result)
                writer.records(result)
            else:
                raise TypeError(
                    f"stage {self.stage.name} returned {type(result).__name__}; a stage returns a"
                    " frame, a dict of frames, a list of records, a stream, or None for a store effect"
                )
        except BaseException as e:
            writer.abort()
            self.run.store.finish_invocation(
                inv, status="failed", code=manifest.code, fetched=False, error=repr(e)
            )
            raise
        art = self.publish(inv, writer, manifest)
        if art is not None:
            self.run.register(result, art.key, art.code)
        return result

    def publish(self, inv: int, writer: Writer, manifest: fingerprint.Manifest) -> Artifact | None:
        if not self.record_inputs(inv):
            writer.abort()
            self.run.store.finish_invocation(inv, status="ok", code=manifest.code, fetched=False)
            return None
        art = writer.finish(manifest.code)
        self.run.store.add_artifact_row(art, created_by=inv)
        self.run.store.finish_invocation(inv, status="ok", code=manifest.code, fetched=False)
        return art

    def effect(self, store: Any) -> None:
        # The store says whether the effect is present; the run store says whether the code
        # that produced it still hashes the same. Both, or the function runs again (every
        # store effect is idempotent over what is already there).
        if store.effect_complete(self.key):
            for row in self.run.store.artifacts(self.key):
                if valid(self.run, self.key, row["code"], set()):
                    inv = self.start()
                    self.record_inputs(inv)
                    self.run.store.finish_invocation(
                        inv, status="ok", code=row["code"], fetched=True
                    )
                    return
        inv = self.start()
        store.begin_effect(self.key, self.stage.name)
        rec = Recording()
        try:
            with seeded(self.seed):
                rec.start()
                self.stage.fn(*self.bound.args, **self.bound.kwargs)
        except BaseException as e:
            rec.stop()
            self.run.store.finish_invocation(
                inv, status="failed", code=None, fetched=False, error=repr(e)
            )
            raise
        rec.stop()
        manifest = fingerprint.build(rec.codes)
        self.run.store.put_manifest(manifest)
        store.complete_effect(self.key)
        self.record_inputs(inv)
        self.run.store.add_artifact_row(
            Artifact(
                stage=self.stage.name,
                key=self.key,
                code=manifest.code,
                kind="store",
                path=None,
                content_hash=store.identity(),
                rows=0,
                bytes=0,
            ),
            created_by=inv,
        )
        self.run.store.finish_invocation(inv, status="ok", code=manifest.code, fetched=False)


class LiveStream[T](IterableDataset[T]):
    """A stream a stage is producing in this run: consumed once, written to its artifact as it
    goes, published on exhaustion. Iterating again after that reads the artifact. Identified by
    the data key, the same as the published stream, so downstream keys do not depend on whether
    the input came live or from the cache."""

    def __init__(self, call: _Call, inv: int, rec: Recording, inner: Iterator[T]) -> None:
        self.call, self.inv, self.rec, self.inner = call, inv, rec, inner
        self.key = call.key
        self.artifact: Artifact | None = None
        self.started = False

    @property
    def artifact_key(self) -> str:
        return self.key

    @property
    def artifact_code(self) -> str | None:
        return self.artifact.code if self.artifact else None

    def fingerprint(self) -> str:
        return content_key("artifact", self.key)

    def __iter__(self) -> Iterator[T]:
        if self.artifact is not None:
            yield from artifacts.read(self.call.run.root, self.artifact)
            return
        if self.started:
            raise RuntimeError(f"stream of {self.call.stage.name} is already being consumed")
        self.started = True
        run = self.call.run
        writer = Writer(run.root, self.call.stage.name, self.key)
        writer.kind = "stream"  # an exhausted empty stream still publishes an empty artifact
        batch: list[Any] = []
        try:
            while True:
                with seeded(self.call.seed), self.rec:
                    try:
                        item = next(self.inner)
                    except StopIteration:
                        break
                if isinstance(item, pl.DataFrame):
                    writer.add(item)
                else:
                    batch.append(item)
                    if len(batch) >= BATCH:
                        writer.add(batch)
                        batch = []
                yield item
            if batch:
                writer.add(batch)
        except GeneratorExit:
            writer.abort()
            run.store.finish_invocation(self.inv, status="partial", code=None, fetched=False)
            raise
        except BaseException as e:
            writer.abort()
            run.store.finish_invocation(
                self.inv, status="failed", code=None, fetched=False, error=repr(e)
            )
            raise
        manifest = fingerprint.build(self.rec.codes)
        run.store.put_manifest(manifest)
        self.artifact = self.call.publish(self.inv, writer, manifest)


def valid(run: Run, key: str, code: str, seen: set[tuple[str, str]]) -> bool:
    """Whether the artifact at (key, code) would be produced again by the code in this process:
    its manifest validates, it is complete on disk, and every artifact it was built from is
    valid by the same test."""
    if (key, code) in seen:
        return True
    seen.add((key, code))
    row = run.store.artifact_row(key, code)
    if row is None:
        return False
    manifest = run.store.manifest(code)
    if manifest is None or not fingerprint.validate(manifest):
        return False
    if row["kind"] != "store" and artifacts.complete(run.root, row["stage"], key, code) is None:
        return False
    for inp in run.store.invocation_inputs(row["created_by"]):
        if inp["kind"] == "artifact" and (
            inp["code"] is None or not valid(run, inp["identity"], inp["code"], seen)
        ):
            return False
    return True
