"""Records in a relational database through SQLModel: SQLite, PostgreSQL, or any SQLAlchemy URL."""

from collections.abc import Iterable, Iterator
from uuid import UUID

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, col, create_engine, delete, select

from triplum.datatype import Chunk, Source
from triplum.store.checks import checked_chunks, new_sources
from triplum.store.protocols import RecordStore
from triplum.store.sql.tables import ChunkRow, SourceRow


class SQLAlchemyStore(RecordStore):
    """Records in the database at `url` (any SQLAlchemy URL); missing tables are created.

    The default URL is an in-memory SQLite database, private to this store instance and shared
    by all threads using it. Backend-specific stores may subclass this where specific SQL is faster.
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
        with Session(self.engine) as session, session.begin():

            def stored(id: UUID) -> Source | None:
                row = session.get(SourceRow, id)
                return None if row is None else _source(row)

            for s in new_sources(sources, stored):
                session.add(
                    SourceRow(
                        id=s.id,
                        collection_id=s.collection_id,
                        origin=s.origin,
                        text=s.text,
                        fingerprint=s.fingerprint(),
                    )
                )

    def replace_chunks(self, source_id: UUID, chunks: Iterable[Chunk], /) -> None:
        # One transaction: SQLite serializes it against other writers, so no union is visible.
        with Session(self.engine) as session, session.begin():
            row = session.get(SourceRow, source_id)
            if row is None:
                raise KeyError(source_id)

            def stored(id: UUID) -> Chunk | None:
                row = session.get(ChunkRow, id)
                return None if row is None else _chunk(row)

            checked = checked_chunks(_source(row), chunks, stored)
            session.exec(delete(ChunkRow).where(col(ChunkRow.source_id) == source_id))
            for c in checked:
                session.add(
                    ChunkRow(
                        id=c.id,
                        collection_id=c.collection_id,
                        source_id=c.source_id,
                        origin=c.origin,
                        ordinal=c.ordinal,
                        start=c.start,
                        text=c.text,
                        fingerprint=c.fingerprint(),
                    )
                )

    def source(self, id: UUID, /) -> Source:
        with Session(self.engine) as session:
            row = session.get(SourceRow, id)
            if row is None:
                raise KeyError(id)
            return _source(row)

    def sources(self) -> Iterator[Source]:
        with Session(self.engine) as session:
            rows = session.exec(select(SourceRow)).all()
        for row in rows:
            yield _source(row)

    def chunks(self, source_id: UUID, /) -> list[Chunk]:
        with Session(self.engine) as session:
            return _chunks(session, source_id)

    def close(self) -> None:
        """Close this store's database connections. An in-memory database is discarded."""
        self.engine.dispose()


def _source(row: SourceRow) -> Source:
    """The stored source; its stored id is checked against the id derived from its fields."""
    return Source(id=row.id, collection_id=row.collection_id, origin=row.origin, text=row.text)


def _chunks(session: Session, source_id: UUID) -> list[Chunk]:
    rows = session.exec(
        select(ChunkRow).where(ChunkRow.source_id == source_id).order_by(col(ChunkRow.ordinal))
    ).all()
    return [_chunk(row) for row in rows]


def _chunk(row: ChunkRow) -> Chunk:
    """The stored chunk; its stored id is checked against the id derived from its fields."""
    return Chunk(
        id=row.id,
        collection_id=row.collection_id,
        source_id=row.source_id,
        origin=row.origin,
        ordinal=row.ordinal,
        start=row.start,
        text=row.text,
    )
