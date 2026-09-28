"""Persistence, one Protocol per capability; implementations grouped by backend technology."""

from triplum.store.memory import MemoryStore
from triplum.store.protocols import RecordStore
from triplum.store.sql import SQLAlchemyStore

__all__ = ["MemoryStore", "RecordStore", "SQLAlchemyStore"]
