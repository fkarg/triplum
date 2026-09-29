"""SQLModel tables for pipeline records, shared by every SQL-backed store."""

from uuid import UUID

from sqlmodel import Field, SQLModel


class CollectionRow(SQLModel, table=True):
    __tablename__ = "collection"  # type: ignore[assignment]

    id: UUID = Field(primary_key=True)
    name: str


class SourceRow(SQLModel, table=True):
    __tablename__ = "source"  # type: ignore[assignment]

    id: UUID = Field(primary_key=True)
    origin: str
    text: str
    fingerprint: str = Field(index=True)


class ChunkRow(SQLModel, table=True):
    __tablename__ = "chunk"  # type: ignore[assignment]

    id: UUID = Field(primary_key=True)
    source_id: UUID = Field(foreign_key="source.id", index=True)
    origin: str
    origin_is_path: bool
    start: int
    text: str
    fingerprint: str = Field(index=True)
