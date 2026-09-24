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

from triplum.cache import content_key
from triplum.data.schema import CHUNKS, FACT_SUPPORT, FACTS, MENTIONS, now_us, polars_schema
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
# The Polars view of the canonical Arrow schemas: one definition, owned by the Rust core.
CHUNK_SCHEMA = polars_schema(CHUNKS)
FACT_SCHEMA = polars_schema(FACTS)
SUPPORT_SCHEMA = polars_schema(FACT_SUPPORT)
MENTION_SCHEMA = polars_schema(MENTIONS)
FACT_COLS = list(FACT_SCHEMA)


def _require_cols(df: pl.DataFrame, cols: list[str], what: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{what} frame missing columns {missing}; have {df.columns}")


def _q(n: int) -> str:
    return ",".join("?" * n)


def fts_query(text: str) -> str:
    """Quote terms so user text cannot inject FTS5 operators; match any term."""
    terms = re.findall(r"\w+", text)
    if not terms:
        return '""'
    return " OR ".join(f'"{t}"' for t in terms)


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
        ddl = files("triplum.store.sqlite").joinpath("migrations.sql").read_text()
        self.conn.executescript(ddl)
        self._migrate(ddl)

    def _migrate(self, ddl: str) -> None:
        """Schema 1 had NOT NULL confidence on facts and mentions. Nothing wrote the graph
        tables under schema 1, so they are dropped and recreated rather than rebuilt."""
        if self.get_meta("schema_version") != "1":
            return
        n = self.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        if n:
            raise RuntimeError(f"store {self.path} is schema 1 with {n} facts; cannot migrate")
        self.conn.executescript(
            "DROP TABLE mentions; DROP TABLE fact_support; DROP TABLE facts; DROP TABLE entities;"
        )
        self.conn.executescript(ddl)
        self.set_meta("schema_version", "2")

    def close(self) -> None:
        self.conn.close()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row[0]

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))

    def identity(self) -> str:
        return content_key(
            "store", [self.get_meta("corpus_hash"), self.get_meta("graph_identity")]
        )[:16]

    def begin_effect(self, key: str, stage: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO effects(key, stage, started_us, completed_us)"
            " VALUES (?, ?, ?, NULL)",
            (key, stage, now_us()),
        )

    def complete_effect(self, key: str) -> None:
        self.conn.execute("UPDATE effects SET completed_us = ? WHERE key = ?", (now_us(), key))

    def effect_complete(self, key: str) -> bool:
        row = self.conn.execute("SELECT completed_us FROM effects WHERE key = ?", (key,)).fetchone()
        return row is not None and row[0] is not None

    def capabilities(self) -> Capabilities:
        return Capabilities(exact_acl_filter=True, vector_search_exact=True, bm25=True)

    # ---- documents and grants ------------------------------------------------------------

    def put_documents(self, docs: pl.DataFrame, grants: pl.DataFrame) -> None:
        """Upsert documents and grants, then rederive every touched document's ACL
        materialisations (acl_hash, acl_tokens on documents and chunks, vec0 partitions)."""
        _require_cols(docs, DOC_COLS, "documents")
        _require_cols(grants, GRANT_COLS, "document_grants")
        with self._tx():
            self.conn.executemany(
                "INSERT INTO documents(id, source, uri, observed_at, metadata, acl_hash, acl_tokens)"
                " VALUES (?,?,?,?,?,'','') ON CONFLICT(id) DO UPDATE SET source = excluded.source,"
                " uri = excluded.uri, observed_at = excluded.observed_at, metadata = excluded.metadata",
                [
                    (r["id"], r["source"], r["uri"], int(r["observed_at"]), r["metadata"])
                    for r in docs.iter_rows(named=True)
                ],
            )
            self.conn.executemany(
                "INSERT INTO document_grants(document_id, principal, granted_at, revoked_at)"
                " VALUES (?,?,?,?) ON CONFLICT(document_id, principal, granted_at)"
                " DO UPDATE SET revoked_at = excluded.revoked_at",
                [
                    (r["document_id"], r["principal"], int(r["granted_at"]), r["revoked_at"])
                    for r in grants.iter_rows(named=True)
                ],
            )
            for doc_id in set(docs["id"].to_list()) | set(grants["document_id"].to_list()):
                self._refresh_acl(doc_id)

    def grant(self, document_id: str, principal: str, at: int) -> None:
        with self._tx():
            self.conn.execute(
                "INSERT OR IGNORE INTO document_grants(document_id, principal, granted_at, revoked_at)"
                " VALUES (?,?,?,NULL)",
                (document_id, principal, at),
            )
            self._refresh_acl(document_id)

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
            # An upsert, not REPLACE: a replaced row cascades away the chunk's support and
            # mention rows, which would turn a two-chunk support group into a one-chunk one.
            self.conn.executemany(
                "INSERT INTO chunks(id, document_id, parent_id, level, span_start,"
                " span_end, text, acl_tokens) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE"
                " SET document_id = excluded.document_id, parent_id = excluded.parent_id,"
                " level = excluded.level, span_start = excluded.span_start,"
                " span_end = excluded.span_end, text = excluded.text,"
                " acl_tokens = excluded.acl_tokens",
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

    # ---- indexed text search ----------------------------------------------------------------

    def search_text(self, query: str, viewer: Viewer, limit: int = 10) -> pl.DataFrame:
        """Visible FTS5 matches in document order, without a ranking calculation."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        acl = " OR ".join(principal_token(p) for p in viewer.sorted_principals())
        match = f"text:({fts_query(query)}) AND acl_tokens:({acl})"
        vis, params = self._visible_ids_sql(viewer)
        rows = self.conn.execute(
            "SELECT c.id, c.document_id, c.parent_id, c.level, c.span_start, c.span_end, c.text"
            " FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid"
            f" WHERE chunks_fts MATCH ? AND {vis} ORDER BY c.document_id, c.id LIMIT ?",
            [match, *params, limit],
        ).fetchall()
        return pl.DataFrame(rows, schema=CHUNK_SCHEMA, orient="row")

    def bm25(self, query: str, k: int, viewer: Viewer) -> pl.DataFrame:
        acl = " OR ".join(principal_token(p) for p in viewer.sorted_principals())
        match = f"text:({fts_query(query)}) AND acl_tokens:({acl})"
        vis, params = self._visible_ids_sql(viewer)
        rows = self.conn.execute(
            "SELECT c.id, -bm25(chunks_fts, 1.0, 0.0) AS score FROM chunks_fts"
            " JOIN chunks c ON c.id = chunks_fts.rowid"
            f" WHERE chunks_fts MATCH ? AND {vis} ORDER BY bm25(chunks_fts, 1.0, 0.0), c.id LIMIT ?",
            [match, *params, k],
        ).fetchall()
        return pl.DataFrame(rows, schema={"id": pl.Int64, "score": pl.Float64}, orient="row")

    # ---- embeddings and vector search --------------------------------------------------------

    def _ensure_vec_table(self, spec: EmbeddingSpec) -> str:
        table = spec.table_name()
        self.conn.execute(
            "INSERT OR IGNORE INTO embedding_specs(spec_hash, spec_json, dims) VALUES (?,?,?)",
            (spec.hash(), json.dumps(spec.__dict__, sort_keys=True), spec.dims),
        )
        self.conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
            "chunk_id INTEGER PRIMARY KEY, acl_hash TEXT PARTITION KEY, "
            f"embedding float[{spec.dims}] distance_metric=cosine)"
        )
        return table

    def put_embeddings(
        self, spec: EmbeddingSpec, chunk_ids: list[int], vectors: np.ndarray
    ) -> None:
        if vectors.shape != (len(chunk_ids), spec.dims):
            raise ValueError(f"vectors shape {vectors.shape} != ({len(chunk_ids)}, {spec.dims})")
        table = self._ensure_vec_table(spec)
        hashes = dict(
            self.conn.execute(
                "SELECT c.id, d.acl_hash FROM chunks c JOIN documents d ON d.id = c.document_id"
                f" WHERE c.id IN ({_q(len(chunk_ids))})",
                [int(i) for i in chunk_ids],
            )
        )
        vectors = vectors.astype(np.float32)
        with self._tx():
            self.conn.executemany(
                f"DELETE FROM {table} WHERE chunk_id = ?", [(int(i),) for i in chunk_ids]
            )
            self.conn.executemany(
                f"INSERT INTO {table}(chunk_id, acl_hash, embedding) VALUES (?,?,?)",
                [
                    (int(cid), hashes[int(cid)], vectors[j].tobytes())
                    for j, cid in enumerate(chunk_ids)
                ],
            )

    def has_embeddings(self, spec: EmbeddingSpec, chunk_ids: list[int]) -> list[bool]:
        table = spec.table_name()
        exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            return [False] * len(chunk_ids)
        present = {
            r[0]
            for r in self.conn.execute(
                f"SELECT chunk_id FROM {table} WHERE chunk_id IN ({_q(len(chunk_ids))})",
                [int(i) for i in chunk_ids],
            )
        }
        return [int(i) in present for i in chunk_ids]

    def vector_search(
        self, spec: EmbeddingSpec, query: np.ndarray, k: int, viewer: Viewer
    ) -> pl.DataFrame:
        table = spec.table_name()
        q = np.asarray(query, dtype=np.float32).reshape(-1)
        if q.shape[0] != spec.dims:
            raise ValueError(f"query dims {q.shape[0]} != spec dims {spec.dims}")
        cands: list[tuple[int, float]] = []
        for h in self.eligible_acl_hashes(viewer):
            cands.extend(
                self.conn.execute(
                    f"SELECT chunk_id, distance FROM {table} WHERE embedding MATCH ?"
                    " AND k = ? AND acl_hash = ?",
                    (q.tobytes(), k, h),
                ).fetchall()
            )
        cands.sort(key=lambda r: (r[1], r[0]))
        ids = [c[0] for c in cands]
        visible = set(self.get_chunks(ids, viewer)["id"].to_list()) if ids else set()
        rows = [(cid, 1.0 - dist) for cid, dist in cands if cid in visible][:k]
        return pl.DataFrame(rows, schema={"id": pl.Int64, "score": pl.Float64}, orient="row")

    # ---- graph -----------------------------------------------------------------------------

    def put_graph(
        self,
        entities: pl.DataFrame,
        facts: pl.DataFrame,
        fact_support: pl.DataFrame,
        mentions: pl.DataFrame,
    ) -> None:
        _require_cols(facts, FACT_COLS, "facts")
        _require_cols(fact_support, list(SUPPORT_SCHEMA), "fact_support")
        _require_cols(mentions, list(MENTION_SCHEMA), "mentions")
        unsupported = set(facts["id"].to_list()) - set(fact_support["fact_id"].to_list())
        if unsupported:
            raise ValueError(f"{len(unsupported)} facts have no support group")
        bad = facts.filter(pl.col("object_id").is_null() == pl.col("object_literal").is_null())
        if bad.height:
            raise ValueError(f"{bad.height} facts have both or neither of object_id/object_literal")
        with self._tx():
            self.conn.executemany(
                "INSERT OR IGNORE INTO entities(id, canonical_id) VALUES (?, NULL)",
                [(e,) for e in entities["id"].to_list()],
            )
            self.conn.executemany(
                "UPDATE entities SET canonical_id = ? WHERE id = ?",
                [(c, e) for e, c in entities.select("id", "canonical_id").iter_rows()],
            )
            # Rows are never overwritten (D3): a fact already asserted keeps its original
            # recording time, and new support groups and mentions are added beside the old.
            self.conn.executemany(
                f"INSERT OR IGNORE INTO facts({','.join(FACT_COLS)}) VALUES ({_q(len(FACT_COLS))})",
                facts.select(FACT_COLS).rows(),
            )
            self.conn.executemany(
                "INSERT OR IGNORE INTO fact_support(fact_id, group_no, chunk_id, extractor,"
                " recorded_at) VALUES (?,?,?,?,?)",
                fact_support.select(list(SUPPORT_SCHEMA)).rows(),
            )
            self.conn.executemany(
                "INSERT OR IGNORE INTO mentions(entity_id, chunk_id, span_start, span_end,"
                " confidence) VALUES (?,?,?,?,?)",
                mentions.select(list(MENTION_SCHEMA)).rows(),
            )

    def _visible_facts_sql(self, viewer: Viewer) -> tuple[str, list]:
        """A fact is visible iff one support group has every chunk visible and every member
        recorded by `as_of_recorded` (D4), both of the viewer's instants fall inside its validity
        and recording intervals (D3), and it was not invalidated by then by a fact the viewer
        can see: a private correction does not remove a public fact for the public."""
        chunk_vis, ps = self._visible_ids_sql(viewer)
        vis_chunk = f"SELECT c.id FROM chunks c WHERE {chunk_vis}"
        supported = (
            f"SELECT s.fact_id FROM fact_support s GROUP BY s.fact_id, s.group_no"
            f" HAVING SUM(s.chunk_id NOT IN ({vis_chunk}) OR s.recorded_at > ?) = 0"
        )
        sql = (
            f"f.id IN ({supported})"
            " AND f.valid_from <= ? AND ? < f.valid_to AND f.recorded_at <= ?"
            " AND (f.invalidated_at IS NULL OR f.invalidated_at > ?"
            f" OR f.invalidated_by_fact_id NOT IN ({supported}))"
        )
        rec = viewer.as_of_recorded
        params = [*ps, rec, viewer.as_of_valid, viewer.as_of_valid, rec, rec, *ps, rec]
        return sql, params

    def _facts(self, where: str, params: list) -> pl.DataFrame:
        rows = self.conn.execute(
            f"SELECT {','.join('f.' + c for c in FACT_COLS)} FROM facts f WHERE {where}"
            " ORDER BY f.id",
            params,
        ).fetchall()
        return pl.DataFrame(rows, schema=FACT_SCHEMA, orient="row")

    def facts(self, viewer: Viewer) -> pl.DataFrame:
        return self._facts(*self._visible_facts_sql(viewer))

    def mentions(self, chunk_ids: list[int], viewer: Viewer) -> pl.DataFrame:
        """Mentions in the visible chunks among `chunk_ids`, of entities a visible fact
        touches (D4: an entity is visible iff a visible fact is)."""
        if not chunk_ids:
            return pl.DataFrame(schema=MENTION_SCHEMA)
        visible = self.get_chunks(chunk_ids, viewer)["id"].to_list()
        if not visible:
            return pl.DataFrame(schema=MENTION_SCHEMA)
        vis, params = self._visible_facts_sql(viewer)
        rows = self.conn.execute(
            "SELECT m.entity_id, m.chunk_id, m.span_start, m.span_end, m.confidence FROM mentions m"
            f" WHERE m.chunk_id IN ({_q(len(visible))}) AND EXISTS (SELECT 1 FROM facts f WHERE"
            f" (f.subject_id = m.entity_id OR f.object_id = m.entity_id) AND {vis})"
            " ORDER BY m.chunk_id, m.span_start, m.entity_id",
            [*[int(i) for i in visible], *params],
        ).fetchall()
        return pl.DataFrame(rows, schema=MENTION_SCHEMA, orient="row")

    def neighbours(self, entity_ids: list[str], hops: int, viewer: Viewer) -> pl.DataFrame:
        vis, vparams = self._visible_facts_sql(viewer)
        seen: dict[int, tuple] = {}

        def touching(ids: set[str], predicate: str | None) -> pl.DataFrame:
            if not ids:
                return pl.DataFrame(schema=FACT_SCHEMA)
            marks = _q(len(ids))
            where = f"{vis} AND (f.subject_id IN ({marks}) OR f.object_id IN ({marks}))"
            params = [*vparams, *ids, *ids]
            if predicate is not None:
                where += " AND f.predicate = ?"
                params.append(predicate)
            return self._facts(where, params)

        def close_identity(ids: set[str]) -> set[str]:
            """Union the ids with everything reachable over visible `same_as` facts."""
            grown = set(ids)
            while True:
                same = touching(grown, "same_as")
                new = (set(same["subject_id"]) | set(same["object_id"])) - grown
                for r in same.rows():
                    seen[r[0]] = r
                if not new:
                    return grown
                grown |= new

        frontier = close_identity(set(entity_ids))
        known = set(frontier)
        for _ in range(hops):
            found = touching(frontier, None)
            nxt: set[str] = set()
            for r in found.rows():
                seen[r[0]] = r
                nxt.add(r[2])
                if r[4] is not None:
                    nxt.add(r[4])
            nxt = close_identity(nxt - known) - known
            if not nxt:
                break
            known |= nxt
            frontier = nxt
        return pl.DataFrame(sorted(seen.values()), schema=FACT_SCHEMA, orient="row")

    # ---- helpers ---------------------------------------------------------------------------

    def _tx(self):
        store = self

        class _Tx:
            def __enter__(self_):
                store.conn.execute("BEGIN IMMEDIATE")

            def __exit__(self_, et, ev, tb):
                store.conn.execute("ROLLBACK" if et else "COMMIT")

        return _Tx()
