"""Shared settings: where data and caches live, and URL mirrors for pinned files.

Read from the environment with the ``TRIPLUM_`` prefix (``TRIPLUM_DATA``, ``TRIPLUM_CACHE``,
``TRIPLUM_MIRRORS`` as a JSON object) or passed explicitly. Settings never enter an identity:
verified bytes are the same wherever they came from.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cache() -> Path:
    return Path.home() / ".cache" / "triplum"


def _default_data() -> Path:
    return _default_cache() / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRIPLUM_", frozen=True)

    data: Path = Field(default_factory=_default_data)
    cache: Path = Field(default_factory=_default_cache)
    mirrors: dict[str, str] = Field(default_factory=dict)  # URL prefix -> replacement prefix

    @field_validator("data", "cache")
    @classmethod
    def _expand(cls, path: Path) -> Path:
        return path.expanduser()

    def mirrored(self, url: str) -> str:
        """The URL to fetch: the longest matching mirror prefix replaced, else `url` itself."""
        best = max((p for p in self.mirrors if url.startswith(p)), key=len, default=None)
        return url if best is None else self.mirrors[best] + url[len(best) :]
