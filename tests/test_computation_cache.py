from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from threading import Event, Semaphore

import pytest

from triplum.cache import Cache, CacheKey, CachePolicy, SQLiteBackend

KEY = CacheKey(b"p" * 32, b"i" * 32, "v1")
OTHER = CacheKey(b"p" * 32, b"j" * 32, "v1")


class GatedSQLite(SQLiteBackend):
    """Expose commit boundaries while retaining real persistence and reads."""

    def __init__(self, path: Path, *, fail: bool = False) -> None:
        super().__init__(path)
        self.entered: Queue[None] = Queue()
        self.release = Semaphore(0)
        self.fail = fail

    def put_many(self, entries: Sequence[tuple[CacheKey, bytes]], /) -> None:
        self.entered.put(None)
        if not self.release.acquire(timeout=5):
            raise TimeoutError("test did not release commit")
        if self.fail:
            raise OSError("test storage failure")
        super().put_many(entries)


def test_pending_visible_and_skip_counts_inflight_bytes(tmp_path: Path) -> None:
    backend = GatedSQLite(tmp_path / "cache.sqlite")
    cache = Cache(backend, pending_bytes=4096)
    try:
        assert cache.put(KEY, b"a" * 3000)
        backend.entered.get(timeout=5)
        assert cache.get(KEY) == b"a" * 3000
        assert not cache.put(OTHER, b"b" * 3000)
        assert cache.skipped_writes == 1
        assert cache.get(OTHER) is None
        backend.release.release()
        cache.flush()
        assert cache.put(OTHER, b"b" * 3000)
        backend.release.release()
        cache.flush()
        assert cache.get(OTHER) == b"b" * 3000
    finally:
        backend.release.release(10)
        cache.close()


def test_old_commit_does_not_hide_new_pending_value(tmp_path: Path) -> None:
    backend = GatedSQLite(tmp_path / "cache.sqlite")
    cache = Cache(backend, pending_bytes=4096)
    try:
        cache.put(KEY, b"old")
        backend.entered.get(timeout=5)
        cache.put(KEY, b"new")
        backend.release.release()
        backend.entered.get(timeout=5)
        assert cache.get(KEY) == b"new"
        backend.release.release()
        cache.flush()
        assert cache.get(KEY) == b"new"
    finally:
        backend.release.release(10)
        cache.close()


def test_blocking_override_waits_for_capacity(tmp_path: Path) -> None:
    backend = GatedSQLite(tmp_path / "cache.sqlite")
    cache = Cache(backend, pending_bytes=4096)
    started = Event()
    finished = Event()

    def put() -> bool:
        started.set()
        try:
            return cache.put(OTHER, b"b" * 3000, policy=CachePolicy(on_full="block"))
        finally:
            finished.set()

    with ThreadPoolExecutor() as pool:
        try:
            cache.put(KEY, b"a" * 3000)
            backend.entered.get(timeout=5)
            future = pool.submit(put)
            assert started.wait(5)
            assert not finished.wait(0.05)
            backend.release.release()
            assert future.result(timeout=5)
            backend.release.release()
            cache.flush()
            assert cache.get(OTHER) == b"b" * 3000
            assert cache.skipped_writes == 0
        finally:
            backend.release.release(10)
            cache.close()


def test_oversize_never_waits_for_impossible_admission(tmp_path: Path) -> None:
    with Cache(SQLiteBackend(tmp_path / "cache.sqlite"), pending_bytes=4096) as cache:
        assert not cache.put(KEY, b"a" * 5000)
        with pytest.raises(ValueError, match="budget"):
            cache.put(KEY, b"a" * 5000, policy=CachePolicy(on_full="block"))
        assert cache.skipped_writes == 1


def test_writer_failure_wakes_blocked_put_and_surfaces_on_close(tmp_path: Path) -> None:
    backend = GatedSQLite(tmp_path / "cache.sqlite", fail=True)
    cache = Cache(backend, pending_bytes=4096, policy=CachePolicy(on_full="block"))
    started, finished = Event(), Event()

    def put() -> bool:
        started.set()
        try:
            return cache.put(OTHER, b"b" * 3000)
        finally:
            finished.set()

    with ThreadPoolExecutor() as pool:
        cache.put(KEY, b"a" * 3000)
        backend.entered.get(timeout=5)
        pending = pool.submit(put)
        flushed = pool.submit(cache.flush)
        assert started.wait(5)
        assert not finished.wait(0.05)
        assert not flushed.done()
        backend.release.release()
        for future in (pending, flushed):
            with pytest.raises(RuntimeError, match="writer"):
                future.result(timeout=5)
        with pytest.raises(RuntimeError, match="writer"):
            cache.get(KEY)
        with pytest.raises(RuntimeError, match="writer"):
            cache.close()
        cache.close()


def test_close_drains_and_rejects_further_use(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    with Cache(SQLiteBackend(path), pending_bytes=4096) as cache:
        assert cache.put(KEY, b"saved")
    cache.close()
    with pytest.raises(RuntimeError, match="closed"):
        cache.get(KEY)
    with pytest.raises(RuntimeError, match="closed"):
        cache.put(KEY, b"late")
    reopened = SQLiteBackend(path)
    try:
        assert reopened.get(KEY) == b"saved"
    finally:
        reopened.close()


def test_committed_payload_is_released_while_writer_is_idle(tmp_path: Path) -> None:
    released = Event()

    class Snapshot(bytes):
        def __del__(self) -> None:
            released.set()

    with Cache(SQLiteBackend(tmp_path / "cache.sqlite"), pending_bytes=4096) as cache:
        assert cache.put(KEY, Snapshot(b"saved"))
        cache.flush()
        assert released.wait(1), "committed payload remains retained by the idle writer"


def test_failed_writer_does_not_retain_payload_in_sticky_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import gc

    caplog.set_level("ERROR", logger="triplum.cache.runtime")
    released = Event()

    class Snapshot(bytes):
        def __del__(self) -> None:
            released.set()

    backend = GatedSQLite(tmp_path / "cache.sqlite", fail=True)
    cache = Cache(backend, pending_bytes=4096)
    cache.put(KEY, Snapshot(b"saved"))
    backend.entered.get(timeout=5)
    backend.release.release()
    with pytest.raises(RuntimeError, match="writer"):
        cache.close()
    gc.collect()
    assert released.wait(1), "sticky error retains failed payload traceback frames"


def test_close_wakes_capacity_waiter_before_drain_finishes(tmp_path: Path) -> None:
    backend = GatedSQLite(tmp_path / "cache.sqlite")
    cache = Cache(backend, pending_bytes=4096, policy=CachePolicy(on_full="block"))
    with ThreadPoolExecutor() as pool:
        try:
            cache.put(KEY, b"a" * 3000)
            backend.entered.get(timeout=5)
            waiting = pool.submit(cache.put, OTHER, b"b" * 3000)
            closing = pool.submit(cache.close)
            with pytest.raises(RuntimeError, match="closed"):
                waiting.result(timeout=5)
            assert not closing.done()
            backend.release.release()
            closing.result(timeout=5)
        finally:
            backend.release.release(10)
            cache.close()


def test_close_waits_for_active_backend_read(tmp_path: Path) -> None:
    entered, release = Event(), Event()

    class GatedRead(SQLiteBackend):
        def get(self, key: CacheKey, /) -> bytes | None:
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test did not release read")
            return super().get(key)

    backend = GatedRead(tmp_path / "cache.sqlite")
    backend.put_many([(KEY, b"saved")])
    cache = Cache(backend, pending_bytes=4096)
    with ThreadPoolExecutor() as pool:
        try:
            reading = pool.submit(cache.get, KEY)
            assert entered.wait(5)
            closing = pool.submit(cache.close)
            assert not closing.done()
            release.set()
            assert reading.result(timeout=5) == b"saved"
            closing.result(timeout=5)
        finally:
            release.set()
            cache.close()


def test_two_cache_owners_can_write_same_database(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite"
    with (
        Cache(SQLiteBackend(path), pending_bytes=65536) as first,
        Cache(SQLiteBackend(path), pending_bytes=65536) as second,
        ThreadPoolExecutor() as pool,
    ):

        def write(cache: Cache, tag: bytes) -> None:
            for index in range(30):
                key = CacheKey(tag * 32, index.to_bytes(32), "v1")
                assert cache.put(key, tag + bytes([index]))
            cache.flush()

        futures = [pool.submit(write, first, b"a"), pool.submit(write, second, b"b")]
        for future in futures:
            future.result(timeout=5)
        for index in range(30):
            assert first.get(CacheKey(b"b" * 32, index.to_bytes(32), "v1")) == b"b" + bytes([index])
            assert second.get(CacheKey(b"a" * 32, index.to_bytes(32), "v1")) == b"a" + bytes(
                [index]
            )


def test_close_reports_both_failures_and_allows_cleanup_retry(tmp_path: Path) -> None:
    class FailingClose(GatedSQLite):
        fail_close = True

        def close(self) -> None:
            if self.fail_close:
                self.fail_close = False
                raise OSError("cleanup failed")
            super().close()

    backend = FailingClose(tmp_path / "cache.sqlite", fail=True)
    cache = Cache(backend, pending_bytes=4096)
    cache.put(KEY, b"value")
    backend.entered.get(timeout=5)
    backend.release.release()
    try:
        with pytest.raises(ExceptionGroup) as caught:
            cache.close()
        assert "writer" in str(caught.value.exceptions[0])
        assert "cleanup failed" in str(caught.value.exceptions[1])
        with pytest.raises(RuntimeError, match="writer"):
            cache.close()
        cache.close()
    finally:
        backend.close()
