"""SQLite's native FTS5 text-search capability, with one snapshot per collection."""

import re
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import text as sql
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

from triplum.datatype import Chunk, FingerprintedDataModel, RetrievalHit, Viewer
from triplum.store.sql.generic import SQLAlchemyStore
from triplum.store.sql.tables import TextIndexRow


class FTS5Settings(FingerprintedDataModel):
    """FTS5 tokenizer declaration and the pattern extracting literal OR query terms.

    FTS5 fixes BM25's k1=1.2 and b=0.75. The default tokenizer retains accents and
    underscores, closer to the reference's lowercased Unicode word tokens.
    """

    model_config = ConfigDict(frozen=True)

    tokenizer: str = "unicode61 remove_diacritics 0 tokenchars '_'"
    token_pattern: str = r"\w+"


class SQLiteStore(SQLAlchemyStore):
    """SQLite records with persisted FTS5 search snapshots and backend-specific settings."""

    def __init__(self, url: str = "sqlite://", *, text: FTS5Settings | None = None) -> None:
        if make_url(url).get_backend_name() != "sqlite":
            raise ValueError("SQLiteStore requires a SQLite URL")
        super().__init__(url)
        self._fts_settings = FTS5Settings() if text is None else text
        self._query_pattern = re.compile(self._fts_settings.token_pattern)
        SQLModel.metadata.create_all(
            self.engine, tables=[SQLModel.metadata.tables[TextIndexRow.__tablename__]]
        )

    def index_text(self, collection_id: UUID, /) -> None:
        """Atomically replace a collection's FTS5 table and its recorded settings."""
        table = f"chunk_text_{collection_id.hex}"
        tokenizer = self._fts_settings.tokenizer.replace("'", "''")
        with self.engine.begin() as connection:
            # sqlite3's legacy transaction mode does not BEGIN for DDL. Explicit BEGIN
            # makes a failed DROP/CREATE/repopulation roll back to the old snapshot.
            connection.exec_driver_sql("BEGIN")
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
            connection.exec_driver_sql(
                f'CREATE VIRTUAL TABLE "{table}" USING fts5('
                "text, chunk_id UNINDEXED, source_id UNINDEXED, ordinal UNINDEXED, "
                f"start UNINDEXED, tokenize='{tokenizer}')"
            )
            connection.execute(
                sql(
                    f'INSERT INTO "{table}" (text, chunk_id, source_id, ordinal, start) '
                    "SELECT text, id, source_id, ordinal, start FROM chunk "
                    "WHERE collection_id = :collection"
                ),
                {"collection": collection_id.hex},
            )
            connection.execute(
                sql(
                    "INSERT INTO text_index (collection_id, settings) VALUES (:id, :settings) "
                    "ON CONFLICT(collection_id) DO UPDATE SET settings = excluded.settings"
                ),
                {"id": collection_id.hex, "settings": self._fts_settings.model_dump_json()},
            )

    def search_text(
        self, query: str, /, *, collection_id: UUID, viewer: Viewer | None = None, k: int
    ) -> list[RetrievalHit]:
        """Search the persisted snapshot, checking settings and filtering before top-k."""
        if k < 1:
            raise ValueError("k must be at least 1")
        table = f"chunk_text_{collection_id.hex}"
        with self.engine.connect() as connection:
            # Keep the settings check and MATCH on the same actual SQLite read snapshot.
            connection.exec_driver_sql("BEGIN")
            settings = connection.execute(
                sql("SELECT settings FROM text_index WHERE collection_id = :id"),
                {"id": collection_id.hex},
            ).scalar_one_or_none()
            if settings is None:
                raise KeyError(collection_id)
            if FTS5Settings.model_validate_json(settings) != self._fts_settings:
                raise ValueError("text index settings changed; call index_text to rebuild")
            terms = [m.group() for m in self._query_pattern.finditer(query) if m.group()]
            if not terms:
                return []
            if any("\x00" in term for term in terms):
                raise ValueError("FTS5 query terms cannot contain NUL characters")
            parameters: dict[str, object] = {
                "query": " OR ".join('"' + term.replace('"', '""') + '"' for term in terms),
                "k": k,
            }
            visibility = ""
            if viewer is not None:
                if not viewer.principals:
                    return []
                placeholders = []
                for i, principal in enumerate(sorted(viewer.principals)):
                    key = f"principal_{i}"
                    placeholders.append(f":{key}")
                    parameters[key] = principal
                visibility = (
                    " AND EXISTS (SELECT 1 FROM source_access a WHERE a.source_id = s.id "
                    f"AND a.principal IN ({', '.join(placeholders)}))"
                )
            rows = connection.execute(
                sql(
                    f"SELECT f.text, f.chunk_id, f.source_id, f.ordinal, f.start, s.origin, "
                    f'-bm25("{table}") AS score FROM "{table}" f '
                    "JOIN source s ON s.id = f.source_id "
                    f'WHERE "{table}" MATCH :query{visibility} '
                    "ORDER BY score DESC, f.source_id, CAST(f.ordinal AS INTEGER) LIMIT :k"
                ),
                parameters,
            ).mappings()
            return [
                RetrievalHit(
                    chunk=Chunk(
                        id=UUID(row["chunk_id"]),
                        collection_id=collection_id,
                        source_id=UUID(row["source_id"]),
                        origin=row["origin"],
                        ordinal=row["ordinal"],
                        start=row["start"],
                        text=row["text"],
                    ),
                    score=row["score"],
                )
                for row in rows
            ]
