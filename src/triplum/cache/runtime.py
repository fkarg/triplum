"""Bounded background persistence and read-your-writes for a shared cache."""

import logging
from collections import deque
from dataclasses import dataclass
from threading import Condition, Lock, Thread
from types import TracebackType
from typing import Self

from triplum.cache.protocols import CacheBackend, CacheKey, CachePolicy

_DEFAULT_POLICY = CachePolicy()
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Write:
    sequence: int
    key: CacheKey
    payload: bytes
    charge: int


class Cache:
    """Explicitly owned cache, safe to lend to multiple steps and caller threads.

    Writes snapshot immutable bytes before admission. The pending budget counts key
    bytes, payload bytes and a 256-byte per-write bookkeeping allowance; it does not
    bound process RSS or serialization buffers. Default admission skips and counts.
    close drains accepted writes. Crash loss and duplicate computation are allowed.
    """

    def __init__(
        self,
        backend: CacheBackend,
        *,
        pending_bytes: int,
        policy: CachePolicy = _DEFAULT_POLICY,
    ) -> None:
        if pending_bytes <= 0:
            raise ValueError("pending_bytes must be positive")
        self._backend = backend
        self._budget = pending_bytes
        self._policy = policy
        self._condition = Condition()
        self._close_lock = Lock()
        self._queue: deque[_Write] = deque()
        self._pending: dict[CacheKey, _Write] = {}
        self._used = 0
        self._accepted = 0
        self._completed = 0
        self._skipped = 0
        self._readers = 0
        self._closing = False
        self._closed = False
        self._error: str | None = None
        self._writer = Thread(target=self._write, name="triplum-cache", daemon=True)
        self._writer.start()

    def _check_error(self) -> None:
        if self._error is not None:
            raise RuntimeError(f"cache writer failed: {self._error}")

    def _check_open(self) -> None:
        self._check_error()
        if self._closing:
            raise RuntimeError("cache is closed")

    def get(self, key: CacheKey, /) -> bytes | None:
        """Read accepted pending values first, then the backend; None is a miss."""
        with self._condition:
            self._check_open()
            pending = self._pending.get(key)
            if pending is not None:
                return pending.payload
            self._readers += 1
        try:
            value = self._backend.get(key)
            with self._condition:
                self._check_error()
                pending = self._pending.get(key)
                return pending.payload if pending is not None else value
        finally:
            with self._condition:
                self._readers -= 1
                self._condition.notify_all()

    def put(self, key: CacheKey, payload: bytes, /, *, policy: CachePolicy | None = None) -> bool:
        """Return whether the write was accepted, not whether it is durable.

        block waits for capacity; an entry exceeding the entire budget raises
        ValueError instead of waiting forever. skip returns False in either case.
        """
        if not isinstance(payload, bytes):
            raise TypeError("cache payload must be immutable bytes")
        charge = 256 + len(key.process) + len(key.input) + len(key.format.encode()) + len(payload)
        selected = self._policy if policy is None else policy
        with self._condition:
            self._check_open()
            if charge > self._budget and selected.on_full == "block":
                raise ValueError("entry exceeds the pending-byte budget")
            while self._used + charge > self._budget:
                if selected.on_full == "skip":
                    self._skipped += 1
                    return False
                self._condition.wait()
                self._check_open()
            self._accepted += 1
            entry = _Write(self._accepted, key, payload, charge)
            self._queue.append(entry)
            self._pending[key] = entry
            self._used += charge
            self._condition.notify_all()
            return True

    @property
    def skipped_writes(self) -> int:
        """Number of writes skipped because they could not fit the budget."""
        with self._condition:
            return self._skipped

    def _write(self) -> None:
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._queue or self._closing)
                    if not self._queue:
                        return
                    batch = list(self._queue)
                    self._queue.clear()
                self._backend.put_many([(entry.key, entry.payload) for entry in batch])
                with self._condition:
                    for entry in batch:
                        if self._pending.get(entry.key) is entry:
                            del self._pending[entry.key]
                        self._used -= entry.charge
                    self._completed = batch[-1].sequence
                    self._condition.notify_all()
                # Do not pin the last committed batch while the writer is idle.
                del batch, entry
        except BaseException as error:
            with self._condition:
                self._error = f"{type(error).__name__}: {error}"
                self._queue.clear()
                self._pending.clear()
                self._used = 0
                self._condition.notify_all()
            logger.exception("Cache background writer failed")

    def flush(self) -> None:
        """Wait for writes accepted before this call; surface any writer failure."""
        with self._condition:
            self._check_open()
            target = self._accepted
            self._condition.wait_for(lambda: self._completed >= target or self._error is not None)
            self._check_error()

    def close(self) -> None:
        """Stop admission, drain, close the backend, and report failures. Idempotent."""
        with self._close_lock:
            with self._condition:
                if self._closed:
                    return
                self._closing = True
                self._condition.notify_all()
            self._writer.join()
            with self._condition:
                self._condition.wait_for(lambda: self._readers == 0)
            try:
                self._backend.close()
            finally:
                with self._condition:
                    self._closed = True
            self._check_error()

    def __enter__(self) -> Self:
        with self._condition:
            self._check_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
