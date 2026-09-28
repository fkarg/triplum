"""Records in a relational database through SQLModel: SQLite, PostgreSQL, or any SQLAlchemy URL."""

from collections.abc import Iterable, Iterator
from pathlib import Path
from uuid import UUID

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, col, create_engine, select

from triplum.datatype import Chunk, Source
from triplum.store.protocols import RecordStore
from triplum.store.sql.tables import ChunkRow, SourceRow


def _origin(value: str, is_path: bool) -> Path | str:
    return Path(value) if is_path else value


class SQLAlchemyStore(RecordStore):
    """Records in the database at `url` (any SQLAlchemy URL); missing tables are created.

    The default URL is an in-memory SQLite database, private to this store instance and shared
    by all threads using it. `Path` and `str` origins are kept apart with an `origin_is_path`
    column. Backend-specific stores may subclass this where specific SQL is faster.
    """

    def __init__(self, url: str = "sqlite://") -> None:
        if url == "sqlite://":
            # One shared connection; otherwise each thread gets its own empty in-memory database.
            self.engine = create_engine(
                url, poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            self.engine = create_engine(url)
        tables = [SQLModel.metadata.tables[row.__tablename__] for row in (SourceRow, ChunkRow)]  # pyright: ignore[reportArgumentType]
        SQLModel.metadata.create_all(self.engine, tables=tables)  # not every imported table

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
