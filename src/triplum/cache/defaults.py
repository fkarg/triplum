"""Visible, lazy defaults for parameter-free caching."""

import atexit
import os
from pathlib import Path
from threading import Lock

from triplum.cache.runtime import Cache
from triplum.cache.sqlite import SQLiteBackend

_lock = Lock()
_cache: Cache | None = None
_owner_pid = os.getpid()
_shutting_down = False


def default_cache_path() -> Path:
    """Resolve the default database path without creating directories or files."""
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    if not root.is_absolute():
        root = Path.home() / ".cache"
    return root / "triplum" / "cache.sqlite"


def default_backend() -> SQLiteBackend:
    """Open the default cache, creating its containing directory if necessary."""
    path = default_cache_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return SQLiteBackend(path)


def default_cache() -> Cache:
    """Lazily open the shared process cache; decoration/import performs no I/O.

    Initialize worker processes before first use. An inherited default after fork is
    rejected; use a fresh process or an explicitly created cache in each worker.
    """
    global _cache, _owner_pid, _lock

    if _owner_pid != os.getpid():
        if _cache is not None:
            raise RuntimeError(
                "default cache was inherited across fork; initialize caches in workers"
            )
        _lock = Lock()
        _owner_pid = os.getpid()
    with _lock:
        if _shutting_down:
            raise RuntimeError("default cache is shutting down")
        if _cache is None:
            _cache = Cache()
        return _cache


def close_default_cache() -> None:
    """Drain/release after callers stop. Later calls reopen it, except during shutdown.

    This does not wait for borrowed computations. Stop/join their callers first; a
    computation still using this owner will fail on insertion after close.
    """
    global _cache
    if _owner_pid != os.getpid():
        return
    with _lock:
        if _cache is not None:
            owned, _cache = _cache, None
            owned.close()


def _shutdown_default_cache() -> None:
    global _shutting_down
    _shutting_down = True
    close_default_cache()


atexit.register(_shutdown_default_cache)
