"""Where triplum keeps re-creatable files on this machine."""

import os
from pathlib import Path


def cache_home() -> Path:
    """`$XDG_CACHE_HOME/triplum`, or `~/.cache/triplum` when unset or relative; not created."""
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    if not root.is_absolute():
        root = Path.home() / ".cache"
    return root / "triplum"
