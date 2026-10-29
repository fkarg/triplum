"""Records in a relational database through SQLModel: SQLite, PostgreSQL, or any SQLAlchemy URL."""

from collections.abc import Iterable, Iterator
from uuid import UUID

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, col, create_engine, select

from triplum.datatype import Chunk, Source
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
        with Session(self.engine) as session:
            for s in sources:
                session.merge(
                    SourceRow(
                        id=s.id,
                        collection_id=s.collection_id,
                        origin=s.origin,
                        text=s.text,
                        fingerprint=s.fingerprint(),
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
                        collection_id=c.collection_id,
                        source_id=c.source_id,
                        origin=c.origin,
                        ordinal=c.ordinal,
                        start=c.start,
                        text=c.text,
                        fingerprint=c.fingerprint(),
                    )
                )
            session.commit()

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
            rows = session.exec(
                select(ChunkRow)
                .where(ChunkRow.source_id == source_id)
                .order_by(col(ChunkRow.start))
            ).all()
        return [
            Chunk(
                id=row.id,
                collection_id=row.collection_id,
                source_id=row.source_id,
                origin=row.origin,
                ordinal=row.ordinal,
                start=row.start,
                text=row.text,
            )
            for row in rows
        ]


def _source(row: SourceRow) -> Source:
    """The stored source; its stored id is checked against the id derived from its fields."""
    return Source(id=row.id, collection_id=row.collection_id, origin=row.origin, text=row.text)
