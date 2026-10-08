"""Optional computation caching with explicit ownership and replaceable storage."""

from triplum.cache.admin import CacheStats, ComputationStats, cache_stats, clear_cache
from triplum.cache.codecs import PydanticCodec
from triplum.cache.defaults import close_default_cache, default_cache, default_cache_path
from triplum.cache.protocols import (
    CacheBackend,
    CacheKey,
    CachePolicy,
    Codec,
    ComputationMetadata,
    Fingerprintable,
)
from triplum.cache.runtime import Cache
from triplum.cache.sqlite import SQLiteBackend
from triplum.cache.steps import CachedStep, cached

__all__ = [
    "Cache",
    "CacheBackend",
    "CacheKey",
    "CachePolicy",
    "CacheStats",
    "CachedStep",
    "Codec",
    "ComputationMetadata",
    "ComputationStats",
    "Fingerprintable",
    "PydanticCodec",
    "SQLiteBackend",
    "cache_stats",
    "cached",
    "clear_cache",
    "close_default_cache",
    "default_cache",
    "default_cache_path",
]
