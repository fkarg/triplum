"""Records in a relational database through SQLModel: SQLite, PostgreSQL, or any SQLAlchemy URL."""

from collections.abc import Iterable, Iterator
from uuid import UUID

from sqlalchemy import ColumnElement, exists, true
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, col, create_engine, delete, select

from triplum.datatype import Chunk, Source, Viewer
from triplum.store.checks import checked_chunks, new_sources, principals
from triplum.store.protocols import RecordStore
from triplum.store.sql.tables import ChunkRow, SourceAccessRow, SourceRow


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
        rows = (SourceRow, SourceAccessRow, ChunkRow)
        tables = [SQLModel.metadata.tables[row.__tablename__] for row in rows]  # pyright: ignore[reportArgumentType]
        SQLModel.metadata.create_all(self.engine, tables=tables)  # not every imported table

    def add_sources(self, sources: Iterable[Source], /, *, allow: Iterable[str]) -> None:
        access = principals(allow)
        with Session(self.engine) as session, session.begin():

            def stored(id: UUID) -> tuple[Source, frozenset[str]] | None:
                row = session.get(SourceRow, id)
                if row is None:
                    return None
                principals = session.exec(
                    select(SourceAccessRow.principal).where(SourceAccessRow.source_id == id)
                ).all()
                return _source(row), frozenset(principals)

            def holder(collection_id: UUID, external_id: str) -> UUID | None:
                return session.exec(
                    select(SourceRow.id).where(
                        SourceRow.collection_id == collection_id,
                        SourceRow.external_id == external_id,
                    )
                ).first()

            added = new_sources(sources, access, stored, holder)
            for s in added:
                session.add(
                    SourceRow(
                        id=s.id,
                        collection_id=s.collection_id,
                        origin=s.origin,
                        text=s.text,
                        external_id=s.external_id,
                        fingerprint=s.fingerprint(),
                    )
                )
            session.flush()  # sources first: access rows reference them by foreign key
            session.add_all(
                SourceAccessRow(source_id=s.id, principal=p) for s in added for p in access
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

    def source(self, id: UUID, /, *, viewer: Viewer | None = None) -> Source:
        with Session(self.engine) as session:
            row = session.exec(
                select(SourceRow).where(SourceRow.id == id, _visible(viewer))
            ).first()
            if row is None:
                raise KeyError(id)
            return _source(row)

    def sources(self, *, collection_id: UUID, viewer: Viewer | None = None) -> Iterator[Source]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(SourceRow).where(SourceRow.collection_id == collection_id, _visible(viewer))
            ).all()
        for row in rows:
            yield _source(row)

    def chunks(self, source_id: UUID, /, *, viewer: Viewer | None = None) -> list[Chunk]:
        with Session(self.engine) as session:
            visible = session.exec(
                select(SourceRow.id).where(SourceRow.id == source_id, _visible(viewer))
            ).first()
            if visible is None:
                raise KeyError(source_id)
            return _chunks(session, source_id)

    def close(self) -> None:
        """Close this store's database connections. An in-memory database is discarded."""
        self.engine.dispose()


def _visible(viewer: Viewer | None) -> ColumnElement[bool]:
    """Whether the source row's allowed principals meet the viewer's, decided before reading it.

    Without a viewer, every stored source is visible.
    """
    if viewer is None:
        return true()
    return exists().where(
        col(SourceAccessRow.source_id) == col(SourceRow.id),
        col(SourceAccessRow.principal).in_(viewer.principals),
    )


def _source(row: SourceRow) -> Source:
    """The stored source; its stored id is checked against the id derived from its fields."""
    return Source(
        id=row.id,
        collection_id=row.collection_id,
        origin=row.origin,
        text=row.text,
        external_id=row.external_id,
    )


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
