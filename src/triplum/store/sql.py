"""Records in a relational database through SQLModel: SQLite, PostgreSQL, or any SQLAlchemy URL."""

from collections.abc import Iterable, Iterator
from pathlib import Path
from uuid import UUID

from sqlmodel import Field, Session, SQLModel, col, create_engine, select

from triplum.datatype import Chunk, Source
from triplum.store import RecordStore


class SourceRow(SQLModel, table=True):
    __tablename__ = "source"  # type: ignore[assignment]

    id: UUID = Field(primary_key=True)
    origin: str
    origin_is_path: bool
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


def _origin(value: str, is_path: bool) -> Path | str:
    return Path(value) if is_path else value


class SQLStore(RecordStore):
    """Records in the database at `url`; tables are created if missing.

    `Path` and `str` origins are kept apart with an `origin_is_path` column. The default URL is a
    private in-memory SQLite database.
    """

    def __init__(self, url: str = "sqlite://") -> None:
        self.engine = create_engine(url)
        SQLModel.metadata.create_all(self.engine)

    def add_sources(self, sources: Iterable[Source], /) -> None:
        with Session(self.engine) as session:
            for s in sources:
                session.merge(
                    SourceRow(
                        id=s.id,
                        origin=str(s.origin),
                        origin_is_path=isinstance(s.origin, Path),
                        text=s.text,
                        fingerprint=s.fingerprint,
                    )
                )
            session.commit()

    def add_chunks(self, chunks: Iterable[Chunk], /) -> None:
        chunks = list(chunks)
        with Session(self.engine) as session:
            wanted = {c.source_id for c in chunks}
            present = set(session.exec(select(SourceRow.id).where(col(SourceRow.id).in_(wanted))))
            for missing in wanted - present:
                raise KeyError(missing)
            for c in chunks:
                session.merge(
                    ChunkRow(
                        id=c.id,
                        source_id=c.source_id,
                        origin=str(c.origin),
                        origin_is_path=isinstance(c.origin, Path),
                        start=c.start,
                        text=c.text,
                        fingerprint=c.fingerprint,
                    )
                )
            session.commit()

    def source(self, id: UUID, /) -> Source:
        with Session(self.engine) as session:
            row = session.get(SourceRow, id)
            if row is None:
                raise KeyError(id)
            return Source(id=row.id, origin=_origin(row.origin, row.origin_is_path), text=row.text)

    def sources(self) -> Iterator[Source]:
        with Session(self.engine) as session:
            rows = session.exec(select(SourceRow)).all()
        for row in rows:
            yield Source(id=row.id, origin=_origin(row.origin, row.origin_is_path), text=row.text)

    def chunks(self, source_id: UUID, /) -> list[Chunk]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(ChunkRow)
                .where(ChunkRow.source_id == source_id)
                .order_by(col(ChunkRow.start))
            ).all()
        return [
            Chunk(
                id=row.id,
                source_id=row.source_id,
                origin=_origin(row.origin, row.origin_is_path),
                start=row.start,
                text=row.text,
            )
            for row in rows
        ]
