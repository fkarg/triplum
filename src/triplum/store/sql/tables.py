"""SQLModel tables for pipeline records, shared by every SQL-backed store."""

from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class CollectionRow(SQLModel, table=True):
    __tablename__ = "collection"  # type: ignore[assignment]

    id: UUID = Field(primary_key=True)
    name: str


class SourceRow(SQLModel, table=True):
    __tablename__ = "source"  # type: ignore[assignment]
    # NULLs are distinct in SQLite and PostgreSQL, so unset external ids never conflict.
    __table_args__ = (UniqueConstraint("collection_id", "external_id"),)

    id: UUID = Field(primary_key=True)
    collection_id: UUID = Field(index=True)
    origin: str
    text: str
    external_id: str | None = None
    fingerprint: str = Field(index=True)


class SourceAccessRow(SQLModel, table=True):
    """One principal allowed to read a source; a source without rows is readable by nobody."""

    __tablename__ = "source_access"  # type: ignore[assignment]

    source_id: UUID = Field(foreign_key="source.id", primary_key=True)
    principal: str = Field(primary_key=True)


class ChunkRow(SQLModel, table=True):
    __tablename__ = "chunk"  # type: ignore[assignment]

    id: UUID = Field(primary_key=True)
    collection_id: UUID = Field(index=True)
    source_id: UUID = Field(foreign_key="source.id", index=True)
    origin: str
    ordinal: int
    start: int
    text: str
    fingerprint: str = Field(index=True)


class TextIndexRow(SQLModel, table=True):
    """Effective settings for each successfully built native SQLite search snapshot."""

    __tablename__ = "text_index"  # type: ignore[assignment]

    collection_id: UUID = Field(primary_key=True)
    settings: str
