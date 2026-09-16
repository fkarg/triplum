"""SQLite store: documents, grants, chunks, FTS5 BM25, sqlite-vec vectors. Every read takes a Viewer.

Visibility at chunk level: a chunk is visible iff its document has a live grant to one of the
viewer's principals. Filtering happens inside FTS5 (acl_tokens column ANDed into MATCH) and inside
vec0 (partition key = document acl_hash), then an exact join re-checks against live grants.
"""

from __future__ import annotations

import json
import re
import sqlite3
from importlib.resources import files
from pathlib import Path

import numpy as np
import polars as pl

from triplum.data.viewer import Viewer
from triplum.embed.protocol import EmbeddingSpec
from triplum.store.protocol import Capabilities
from triplum.store.sqlite.acl import acl_hash, acl_tokens, principal_token

PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA foreign_keys = ON",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -262144",
]

DOC_COLS = ["id", "source", "uri", "observed_at", "metadata"]
GRANT_COLS = ["document_id", "principal", "granted_at", "revoked_at"]
CHUNK_COLS = ["id", "document_id", "parent_id", "level", "span_start", "span_end", "text"]
CHUNK_SCHEMA = {
    "id": pl.Int64,
    "document_id": pl.Utf8,
    "parent_id": pl.Int64,
    "level": pl.Int64,
    "span_start": pl.Int64,
    "span_end": pl.Int64,
    "text": pl.Utf8,
}


def _require_cols(df: pl.DataFrame, cols: list[str], what: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{what} frame missing columns {missing}; have {df.columns}")


def _q(n: int) -> str:
    return ",".join("?" * n)


def fts_query(text: str) -> str:
    """Quote every term so user text cannot inject FTS5 operators."""
    terms = re.findall(r"\w+", text)
    if not terms:
        return '""'
    return " ".join(f'"{t}"' for t in terms)


class SqliteStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        for p in PRAGMAS:
            self.conn.execute(p)
        self.conn.executescript(
            files("triplum.store.sqlite").joinpath("migrations.sql").read_text()
        )

    def close(self) -> None:
        self.conn.close()

    def capabilities(self) -> Capabilities:
        return Capabilities(exact_acl_filter=True, vector_search_exact=True, bm25=True)

    # ---- documents and grants ------------------------------------------------------------

    def put_documents(self, docs: pl.DataFrame, grants: pl.DataFrame) -> None:
        _require_cols(docs, DOC_COLS, "documents")
        _require_cols(grants, GRANT_COLS, "document_grants")
        by_doc: dict[str, set[str]] = {d: set() for d in docs["id"].to_list()}
        for row in grants.filter(pl.col("revoked_at").is_null()).iter_rows(named=True):
            by_doc.setdefault(row["document_id"], set()).add(row["principal"])
        with self._tx():
            self.conn.executemany(
                "INSERT OR REPLACE INTO documents(id, source, uri, observed_at, metadata, acl_hash, acl_tokens)"
                " VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        r["id"],
                        r["source"],
                        r["uri"],
                        int(r["observed_at"]),
                        r["metadata"],
                        acl_hash(by_doc[r["id"]]),
                        acl_tokens(by_doc[r["id"]]),
                    )
                    for r in docs.iter_rows(named=True)
                ],
            )
            self.conn.executemany(
                "INSERT OR REPLACE INTO document_grants(document_id, principal, granted_at, revoked_at)"
                " VALUES (?,?,?,?)",
                [
                    (r["document_id"], r["principal"], int(r["granted_at"]), r["revoked_at"])
                    for r in grants.iter_rows(named=True)
                ],
            )

    def revoke(self, document_id: str, principal: str, at: int) -> None:
        with self._tx():
            self.conn.execute(
                "UPDATE document_grants SET revoked_at = ? WHERE document_id = ? AND principal = ?"
                " AND revoked_at IS NULL",
                (at, document_id, principal),
            )
            self._refresh_acl(document_id)

    def _refresh_acl(self, document_id: str) -> None:
        live = [
            r[0]
            for r in self.conn.execute(
                "SELECT principal FROM document_grants WHERE document_id = ? AND revoked_at IS NULL",
                (document_id,),
            )
        ]
        h, toks = acl_hash(live), acl_tokens(live)
        self.conn.execute(
            "UPDATE documents SET acl_hash = ?, acl_tokens = ? WHERE id = ?", (h, toks, document_id)
        )
        self.conn.execute(
            "UPDATE chunks SET acl_tokens = ? WHERE document_id = ?", (toks, document_id)
        )
        ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
            )
        ]
        for (table,) in self.conn.execute(
            "SELECT 'emb_' || spec_hash FROM embedding_specs"
        ).fetchall():
            for cid in ids:
                row = self.conn.execute(
                    f"SELECT embedding FROM {table} WHERE chunk_id = ?", (cid,)
                ).fetchone()
                if row is not None:
                    self.conn.execute(f"DELETE FROM {table} WHERE chunk_id = ?", (cid,))
                    self.conn.execute(
                        f"INSERT INTO {table}(chunk_id, acl_hash, embedding) VALUES (?,?,?)",
                        (cid, h, row[0]),
                    )

    def document_acl_hash(self, document_id: str) -> str:
        return self.conn.execute(
            "SELECT acl_hash FROM documents WHERE id = ?", (document_id,)
        ).fetchone()[0]

    # ---- chunks ----------------------------------------------------------------------------

    def put_chunks(self, chunks: pl.DataFrame) -> None:
        _require_cols(chunks, CHUNK_COLS, "chunks")
        toks = dict(self.conn.execute("SELECT id, acl_tokens FROM documents"))
        with self._tx():
            self.conn.executemany(
                "INSERT OR REPLACE INTO chunks(id, document_id, parent_id, level, span_start,"
                " span_end, text, acl_tokens) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        int(r["id"]),
                        r["document_id"],
                        r["parent_id"],
                        int(r["level"]),
                        int(r["span_start"]),
                        int(r["span_end"]),
                        r["text"],
                        toks[r["document_id"]],
                    )
                    for r in chunks.iter_rows(named=True)
                ],
            )

    def _visible_ids_sql(self, viewer: Viewer) -> tuple[str, list]:
        ps = viewer.sorted_principals()
        sql = (
            "EXISTS (SELECT 1 FROM document_grants g WHERE g.document_id = c.document_id"
            f" AND g.revoked_at IS NULL AND g.principal IN ({_q(len(ps))}))"
        )
        return sql, ps

    def get_chunks(self, ids: list[int], viewer: Viewer) -> pl.DataFrame:
        if not ids:
            return pl.DataFrame(schema=CHUNK_SCHEMA)
        vis, params = self._visible_ids_sql(viewer)
        rows = self.conn.execute(
            "SELECT c.id, c.document_id, c.parent_id, c.level, c.span_start, c.span_end, c.text"
            f" FROM chunks c WHERE c.id IN ({_q(len(ids))}) AND {vis}",
            [*[int(i) for i in ids], *params],
        ).fetchall()
        return pl.DataFrame(rows, schema=CHUNK_SCHEMA, orient="row")

    def eligible_acl_hashes(self, viewer: Viewer) -> list[str]:
        ps = viewer.sorted_principals()
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT DISTINCT d.acl_hash FROM documents d WHERE EXISTS (SELECT 1 FROM"
                " document_grants g WHERE g.document_id = d.id AND g.revoked_at IS NULL"
                f" AND g.principal IN ({_q(len(ps))}))",
                ps,
            )
        ]

    # ---- helpers ---------------------------------------------------------------------------

    def _tx(self):
        store = self

        class _Tx:
            def __enter__(self_):
                store.conn.execute("BEGIN IMMEDIATE")

            def __exit__(self_, et, ev, tb):
                store.conn.execute("ROLLBACK" if et else "COMMIT")

        return _Tx()
