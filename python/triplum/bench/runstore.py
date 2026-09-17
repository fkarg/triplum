"""The run store is the metrics store: runs, per-question rows, timed and priced events, prices."""

from __future__ import annotations

import platform
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ClassVar, Self

import polars as pl

from triplum.cache import content_key
from triplum.data.schema import now_us

_HOST = platform.node()

RUN_QUESTIONS_DDL = """
CREATE TABLE IF NOT EXISTS run_questions (
  run_id TEXT NOT NULL REFERENCES runs(run_id), question_id TEXT NOT NULL, retrieved_json TEXT NOT NULL,
  answer TEXT NOT NULL, em REAL NOT NULL, f1 REAL NOT NULL, contain REAL NOT NULL, judge REAL,
  r2 REAL, r5 REAL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
  usd REAL, cached INTEGER NOT NULL DEFAULT 0, latency_s REAL NOT NULL, n_chunks INTEGER NOT NULL,
  PRIMARY KEY (run_id, question_id)
) STRICT;
"""

# One envelope for every kind of run (`qa`, `extract`), so events, prices and artifacts point at
# one table; the columns only one kind fills are nullable.
RUNS_DDL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, identity_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'qa',
  dataset TEXT NOT NULL, pipeline TEXT, config_hash TEXT NOT NULL, config_json TEXT NOT NULL,
  code_version TEXT NOT NULL, dirty INTEGER NOT NULL, code_hash TEXT NOT NULL,
  corpus_hash TEXT NOT NULL, questions_hash TEXT NOT NULL,
  n INTEGER NOT NULL, embedding_spec TEXT, reranker_spec TEXT, reader_model TEXT, judge_model TEXT,
  seed INTEGER NOT NULL, viewer_json TEXT NOT NULL, host TEXT NOT NULL,
  reader_prompt_hash TEXT, judge_prompt_hash TEXT,
  extractor_spec TEXT, resolver_spec TEXT, graph_identity TEXT,
  experiment_id TEXT, replicate INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running', wall_s REAL, cache_hits INTEGER, cache_misses INTEGER
) STRICT;
CREATE INDEX IF NOT EXISTS runs_identity ON runs(identity_hash);
"""

EXTRACTION_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS extraction_runs (
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
  entities INTEGER NOT NULL, facts INTEGER NOT NULL, mentions INTEGER NOT NULL,
  claims_accepted INTEGER NOT NULL, claims_subordinate INTEGER NOT NULL, claims_negated INTEGER NOT NULL,
  claims_modal INTEGER NOT NULL, claims_ungrounded INTEGER NOT NULL,
  n_pred INTEGER NOT NULL, n_gold INTEGER NOT NULL, duplicate_rate REAL NOT NULL,
  exact_precision REAL, exact_recall REAL NOT NULL, exact_f1 REAL,
  partial_precision REAL, partial_recall REAL NOT NULL, partial_f1 REAL,
  span_precision REAL, span_recall REAL, span_f1 REAL,
  chunks_per_s REAL, graph_written INTEGER NOT NULL
) STRICT;
"""

# Provenance in the entity, activity and used shape: an artifact is a completed stage output
# addressed by data key and code fingerprint; an invocation is one stage call inside a run; the
# inputs are the edges an invocation used; a manifest is stored once per distinct code.
PROVENANCE_DDL = """
CREATE TABLE IF NOT EXISTS artifacts (
  key TEXT NOT NULL, code TEXT NOT NULL, stage TEXT NOT NULL, kind TEXT NOT NULL, path TEXT,
  content_hash TEXT NOT NULL, rows INTEGER NOT NULL, bytes INTEGER NOT NULL, record_type TEXT,
  created_by INTEGER NOT NULL, created_us INTEGER NOT NULL,
  PRIMARY KEY (key, code)
) STRICT;
CREATE TABLE IF NOT EXISTS invocations (
  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id), stage TEXT NOT NULL,
  structural_key TEXT NOT NULL, key TEXT NOT NULL, code TEXT, inputs_json TEXT NOT NULL,
  seed INTEGER, replicate INTEGER NOT NULL, fetched INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running', error TEXT,
  started_us INTEGER NOT NULL, finished_us INTEGER, wall_s REAL, host TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS invocations_run ON invocations(run_id);
CREATE INDEX IF NOT EXISTS invocations_key ON invocations(structural_key);
CREATE TABLE IF NOT EXISTS invocation_inputs (
  invocation_id INTEGER NOT NULL REFERENCES invocations(id), position INTEGER NOT NULL,
  name TEXT NOT NULL, kind TEXT NOT NULL, identity TEXT NOT NULL, code TEXT,
  PRIMARY KEY (invocation_id, position)
) STRICT;
CREATE TABLE IF NOT EXISTS manifests (code TEXT PRIMARY KEY, manifest_json TEXT NOT NULL) STRICT;
"""

DDL = (
    RUN_QUESTIONS_DDL
    + RUNS_DDL
    + EXTRACTION_RUNS_DDL
    + """
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL REFERENCES runs(run_id), stage TEXT NOT NULL, question_id TEXT, provider TEXT, model TEXT,
  started_at INTEGER NOT NULL, ended_at INTEGER NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0, cached_input_tokens INTEGER NOT NULL DEFAULT 0,
  cached INTEGER NOT NULL DEFAULT 0, usd REAL
) STRICT;
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, stage);
CREATE TABLE IF NOT EXISTS prices (
  model TEXT NOT NULL, provider TEXT NOT NULL, usd_in_per_m REAL NOT NULL, usd_out_per_m REAL NOT NULL,
  usd_cached_in_per_m REAL NOT NULL, valid_from INTEGER NOT NULL, source TEXT NOT NULL,
  PRIMARY KEY (model, provider, valid_from)
) STRICT;
CREATE TABLE IF NOT EXISTS run_prices (
  run_id TEXT NOT NULL REFERENCES runs(run_id), model TEXT NOT NULL, provider TEXT NOT NULL,
  usd_in_per_m REAL NOT NULL, usd_out_per_m REAL NOT NULL, usd_cached_in_per_m REAL NOT NULL,
  valid_from INTEGER NOT NULL, source TEXT NOT NULL,
  PRIMARY KEY (run_id, model)
) STRICT;
CREATE TABLE IF NOT EXISTS run_artifacts (
  run_id TEXT NOT NULL REFERENCES runs(run_id), kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
  PRIMARY KEY (run_id, kind)
) STRICT;
"""
    + PROVENANCE_DDL
)

# code_hash (the pipeline's own source files) identifies a run; code_version and dirty are
# recorded for bookkeeping only, so edits outside the pipeline do not orphan finished runs.
IDENTITY_FIELDS = (
    "kind",
    "dataset",
    "pipeline",
    "config_hash",
    "code_hash",
    "corpus_hash",
    "questions_hash",
    "n",
    "embedding_spec",
    "reranker_spec",
    "reader_model",
    "judge_model",
    "seed",
    "viewer_json",
    "reader_prompt_hash",
    "judge_prompt_hash",
    "extractor_spec",
    "resolver_spec",
    "graph_identity",
)


class RunStore:
    """Owns one SQLite connection from construction to `close()`; use it as a context manager.
    Autocommit, except inside `question_unit`. Every write goes through a named method; the read
    methods return frames or dicts, and nothing outside this module touches the connection."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(DDL)
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # Columns added after the first release, with the default an old row gets. STRICT tables
    # accept ADD COLUMN ... NOT NULL only with a default.
    MIGRATIONS: ClassVar[dict[str, list[tuple[str, str]]]] = {
        "runs": [
            ("code_hash", "TEXT NOT NULL DEFAULT ''"),
            ("reader_prompt_hash", "TEXT NOT NULL DEFAULT ''"),
            ("judge_prompt_hash", "TEXT"),
            ("kind", "TEXT NOT NULL DEFAULT 'qa'"),
            ("extractor_spec", "TEXT"),
            ("resolver_spec", "TEXT"),
            ("graph_identity", "TEXT"),
            ("experiment_id", "TEXT"),
            ("replicate", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "run_questions": [("cached", "INTEGER NOT NULL DEFAULT 0")],
    }

    def _migrate(self) -> None:
        for table, cols in self.MIGRATIONS.items():
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        # n_passages was renamed to n_chunks (the canonical layer's word) on 2026-09-17.
        names = {r[1] for r in self.conn.execute("PRAGMA table_info(run_questions)")}
        if "n_passages" in names:
            self.conn.execute("ALTER TABLE run_questions RENAME COLUMN n_passages TO n_chunks")
        # r2/r5 became nullable (recall is undefined without gold chunks); SQLite cannot drop a
        # NOT NULL, so stores created before that rebuild the table once.
        notnull = {r[1]: r[3] for r in self.conn.execute("PRAGMA table_info(run_questions)")}
        if notnull.get("r2"):
            self._rebuild("run_questions", RUN_QUESTIONS_DDL)
        # pipeline, reader_model and reader_prompt_hash became nullable when extraction runs
        # joined the envelope (2026-09-17).
        notnull = {r[1]: r[3] for r in self.conn.execute("PRAGMA table_info(runs)")}
        if notnull.get("reader_model"):
            self._rebuild("runs", RUNS_DDL)

    def _rebuild(self, table: str, ddl: str) -> None:
        """Recreate a table from the current DDL, keeping every row. Foreign keys from other
        tables keep pointing at the table name (legacy rename), so the new table inherits them."""
        cols = ", ".join(r[1] for r in self.conn.execute(f"PRAGMA table_info({table})"))
        # The rename takes the table's indexes with it; drop them so the DDL recreates them on
        # the new table instead of finding them already present.
        indexes = [
            r[1]
            for r in self.conn.execute(f"PRAGMA index_list({table})")
            if not r[1].startswith("sqlite_autoindex")
        ]
        drops = "".join(f"DROP INDEX IF EXISTS {i};" for i in indexes)
        # foreign_keys cannot change inside a transaction; everything else is one transaction,
        # so an interrupted rebuild leaves the old table in place.
        self.conn.execute("PRAGMA foreign_keys = OFF")
        try:
            self.conn.executescript(
                "BEGIN; PRAGMA legacy_alter_table = ON;"
                f"ALTER TABLE {table} RENAME TO {table}_old;"
                + drops
                + ddl
                + f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {table}_old;"
                f"DROP TABLE {table}_old;"
                "PRAGMA legacy_alter_table = OFF; COMMIT;"
            )
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise
        finally:
            self.conn.execute("PRAGMA foreign_keys = ON")

    # ---- prices -----------------------------------------------------------------------------

    def set_price(
        self,
        model: str,
        provider: str,
        *,
        usd_in_per_m: float,
        usd_out_per_m: float,
        usd_cached_in_per_m: float,
        source: str,
        valid_from: int | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
            (
                model,
                provider,
                usd_in_per_m,
                usd_out_per_m,
                usd_cached_in_per_m,
                valid_from or now_us(),
                source,
            ),
        )

    def price(self, model: str) -> tuple[float, float, float] | None:
        row = self.conn.execute(
            "SELECT usd_in_per_m, usd_out_per_m, usd_cached_in_per_m FROM prices WHERE model = ?"
            " ORDER BY valid_from DESC LIMIT 1",
            (model,),
        ).fetchone()
        return None if row is None else (row[0], row[1], row[2])

    def snapshot_prices(self, run_id: str, models: list[str]) -> None:
        """Copy the price rows in force now into run_prices so the run's cost stays reproducible."""
        for model in {m for m in models if m}:
            row = self.conn.execute(
                "SELECT model, provider, usd_in_per_m, usd_out_per_m, usd_cached_in_per_m,"
                " valid_from, source FROM prices WHERE model = ? ORDER BY valid_from DESC LIMIT 1",
                (model,),
            ).fetchone()
            if row is not None:
                self.conn.execute(
                    "INSERT OR REPLACE INTO run_prices VALUES (?,?,?,?,?,?,?,?)", (run_id, *row)
                )

    def run_price(self, run_id: str, model: str) -> tuple[float, float, float] | None:
        row = self.conn.execute(
            "SELECT usd_in_per_m, usd_out_per_m, usd_cached_in_per_m FROM run_prices"
            " WHERE run_id = ? AND model = ?",
            (run_id, model),
        ).fetchone()
        return None if row is None else (row[0], row[1], row[2])

    # ---- runs -------------------------------------------------------------------------------

    @staticmethod
    def identity_hash(meta: dict) -> str:
        return content_key("run", {k: meta.get(k) for k in IDENTITY_FIELDS})

    def find_run(self, identity_hash: str, status: str = "ok") -> str | None:
        row = self.conn.execute(
            "SELECT run_id FROM runs WHERE identity_hash = ? AND status = ?"
            " ORDER BY created_at DESC LIMIT 1",
            (identity_hash, status),
        ).fetchone()
        return None if row is None else row[0]

    def completed_questions(self, run_id: str) -> set[str]:
        return {
            r[0]
            for r in self.conn.execute(
                "SELECT question_id FROM run_questions WHERE run_id = ?", (run_id,)
            )
        }

    @contextmanager
    def question_unit(self):
        """One transaction per finished question: its events and its row commit together, so a
        crash in between leaves nothing half-written and resume can trust run_questions."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def start_run(self, meta: dict) -> str:
        run_id = uuid.uuid4().hex[:12]
        cols = ["run_id", "identity_hash", "created_at", *meta.keys()]
        vals = [run_id, self.identity_hash(meta), now_us(), *meta.values()]
        self.conn.execute(
            f"INSERT INTO runs({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals
        )
        return run_id

    def resume_run(self, run_id: str) -> None:
        """Mark a running or failed run as running again before continuing its questions."""
        self.conn.execute("UPDATE runs SET status = 'running' WHERE run_id = ?", (run_id,))

    def finish_run(
        self, run_id: str, *, status: str, wall_s: float, cache_hits: int, cache_misses: int
    ) -> None:
        self.conn.execute(
            "UPDATE runs SET status = ?, wall_s = ?, cache_hits = ?, cache_misses = ?"
            " WHERE run_id = ?",
            (status, wall_s, cache_hits, cache_misses, run_id),
        )

    def add_question(self, run_id: str, row: dict) -> None:
        cols = ["run_id", *row.keys()]
        self.conn.execute(
            f"INSERT OR REPLACE INTO run_questions({','.join(cols)})"
            f" VALUES ({','.join('?' * len(cols))})",
            [run_id, *row.values()],
        )

    def add_extraction(self, run_id: str, row: dict) -> None:
        cols = ["run_id", *row.keys()]
        self.conn.execute(
            f"INSERT OR REPLACE INTO extraction_runs({','.join(cols)})"
            f" VALUES ({','.join('?' * len(cols))})",
            [run_id, *row.values()],
        )

    def extraction(self, run_id: str) -> dict | None:
        cur = self.conn.execute("SELECT * FROM extraction_runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        return None if row is None else dict(zip([d[0] for d in cur.description], row))

    def add_artifact(self, run_id: str, kind: str, path: str, sha256: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO run_artifacts VALUES (?,?,?,?)", (run_id, kind, path, sha256)
        )

    # ---- provenance: artifacts, invocations, inputs, manifests -----------------------------

    def start_invocation(
        self,
        run_id: str,
        stage: str,
        structural_key: str,
        key: str,
        seed: int | None,
        replicate: int,
        inputs_json: str,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO invocations(run_id, stage, structural_key, key, inputs_json, seed,"
            " replicate, started_us, host) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, stage, structural_key, key, inputs_json, seed, replicate, now_us(), _HOST),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def finish_invocation(
        self,
        invocation_id: int,
        *,
        status: str,
        code: str | None,
        fetched: bool,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            "UPDATE invocations SET status = ?, code = ?, fetched = ?, error = ?,"
            " finished_us = ?, wall_s = (? - started_us) / 1e6 WHERE id = ?",
            (status, code, int(fetched), error, now_us(), now_us(), invocation_id),
        )

    def add_invocation_inputs(
        self, invocation_id: int, rows: list[tuple[int, str, str, str, str | None]]
    ) -> None:
        """Rows of (position, name, kind, identity, code); code only for artifact inputs."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO invocation_inputs VALUES (?,?,?,?,?,?)",
            [(invocation_id, *r) for r in rows],
        )

    def invocation_inputs(self, invocation_id: int) -> list[dict]:
        return self._rows(
            "SELECT * FROM invocation_inputs WHERE invocation_id = ? ORDER BY position",
            (invocation_id,),
        )

    def invocations(self, run_id: str) -> pl.DataFrame:
        return self._frame("SELECT * FROM invocations WHERE run_id = ? ORDER BY id", (run_id,))

    def add_artifact_row(self, artifact: Any, *, created_by: int) -> None:
        """Record a published artifact (a `stage.artifacts.Artifact`); a second publication at
        the same key and code keeps the first row."""
        self.conn.execute(
            "INSERT OR IGNORE INTO artifacts(key, code, stage, kind, path, content_hash, rows,"
            " bytes, record_type, created_by, created_us) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                artifact.key,
                artifact.code,
                artifact.stage,
                artifact.kind,
                artifact.path,
                artifact.content_hash,
                artifact.rows,
                artifact.bytes,
                artifact.record_type,
                created_by,
                now_us(),
            ),
        )

    def artifacts(self, key: str) -> list[dict]:
        """Every artifact at a data key, newest first."""
        return self._rows("SELECT * FROM artifacts WHERE key = ? ORDER BY created_us DESC", (key,))

    def artifact_row(self, key: str, code: str) -> dict | None:
        rows = self._rows("SELECT * FROM artifacts WHERE key = ? AND code = ?", (key, code))
        return rows[0] if rows else None

    def put_manifest(self, manifest: Any) -> None:
        """Store a `stage.fingerprint.Manifest` once per distinct code."""
        self.conn.execute(
            "INSERT OR IGNORE INTO manifests VALUES (?, ?)",
            (manifest.code, manifest.model_dump_json()),
        )

    def manifest(self, code: str) -> Any | None:
        from triplum.stage.fingerprint import Manifest

        row = self.conn.execute(
            "SELECT manifest_json FROM manifests WHERE code = ?", (code,)
        ).fetchone()
        return None if row is None else Manifest.model_validate_json(row[0])

    def lineage(self, key: str, code: str) -> list[dict]:
        """The artifacts an artifact was built from, transitively: rows of (key, code, stage),
        the artifact itself first, each input after the artifact that used it."""
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        todo = [(key, code)]
        while todo:
            k, c = todo.pop(0)
            if (k, c) in seen:
                continue
            seen.add((k, c))
            row = self.artifact_row(k, c)
            if row is None:
                continue
            out.append({"key": k, "code": c, "stage": row["stage"]})
            for inp in self.invocation_inputs(row["created_by"]):
                if inp["kind"] == "artifact" and inp["code"] is not None:
                    todo.append((inp["identity"], inp["code"]))
        return out

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.conn.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def add_event(
        self,
        run_id: str,
        stage: str,
        *,
        question_id: str | None,
        provider: str | None,
        model: str | None,
        started_at: int,
        ended_at: int,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int,
        cached: bool,
        usd: float | None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO events(run_id, stage, question_id, provider, model, started_at,"
            " ended_at, input_tokens, output_tokens, cached_input_tokens, cached, usd)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                stage,
                question_id,
                provider,
                model,
                started_at,
                ended_at,
                input_tokens,
                output_tokens,
                cached_input_tokens,
                int(cached),
                usd,
            ),
        )

    def recorder(self, run_id: str) -> Recorder:
        return Recorder(self, run_id)

    # ---- reads ------------------------------------------------------------------------------

    def _frame(self, sql: str, params: tuple = ()) -> pl.DataFrame:
        cur = self.conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pl.DataFrame(cur.fetchall(), schema=cols, orient="row")

    def run(self, run_id: str) -> dict | None:
        cur = self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        return None if row is None else dict(zip([d[0] for d in cur.description], row))

    def runs(self) -> pl.DataFrame:
        return self._frame("SELECT * FROM runs ORDER BY created_at")

    def questions(self, run_id: str) -> pl.DataFrame:
        return self._frame("SELECT * FROM run_questions WHERE run_id = ?", (run_id,))

    def events(self, run_id: str) -> pl.DataFrame:
        return self._frame("SELECT * FROM events WHERE run_id = ? ORDER BY started_at", (run_id,))

    def run_index(self) -> pl.DataFrame:
        """Newest first: run_id, dataset, pipeline, status, n, reader_model, embedding_spec.
        An extraction run shows `extract` as its pipeline and its extractor as the model."""
        return self._frame(
            "SELECT run_id, dataset, COALESCE(pipeline, 'extract') AS pipeline, status, n,"
            " COALESCE(reader_model, extractor_spec) AS reader_model, embedding_spec"
            " FROM runs ORDER BY created_at DESC, run_id"
        )

    def question_ids(self, run_id: str) -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT question_id FROM run_questions WHERE run_id = ? ORDER BY question_id",
                (run_id,),
            )
        ]

    def artifact(self, run_id: str, kind: str) -> tuple[str, str] | None:
        """(path, sha256) of a recorded artifact, or None."""
        row = self.conn.execute(
            "SELECT path, sha256 FROM run_artifacts WHERE run_id = ? AND kind = ?", (run_id, kind)
        ).fetchone()
        return None if row is None else (row[0], row[1])

    def progress(self, run_id: str) -> tuple[int, tuple[str, str | None, int] | None]:
        """Questions finished, and the latest event as (stage, question_id, ended_at)."""
        done = self.conn.execute(
            "SELECT COUNT(*) FROM run_questions WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        last = self.conn.execute(
            "SELECT stage, question_id, ended_at FROM events WHERE run_id = ?"
            " ORDER BY ended_at DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        return done, (None if last is None else (last[0], last[1], last[2]))


class _Event:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_in = 0
        self.cached = False

    def usage(
        self, input_tokens: int, output_tokens: int, cached_in: int = 0, cached: bool = False
    ) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_in += cached_in
        self.cached = self.cached or cached


class Recorder:
    def __init__(self, store: RunStore, run_id: str) -> None:
        self.store = store
        self.run_id = run_id
        self.cache_hits = 0
        self.cache_misses = 0

    def cost(
        self, model: str | None, input_tokens: int, output_tokens: int, cached_in: int
    ) -> float | None:
        p = self.store.run_price(self.run_id, model) if model else None
        if p is None:
            return None
        usd_in, usd_out, usd_cached = p
        return (
            (input_tokens - cached_in) * usd_in + cached_in * usd_cached + output_tokens * usd_out
        ) / 1e6

    @contextmanager
    def stage(
        self,
        stage: str,
        *,
        question_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ):
        ev = _Event()
        t0 = time.time_ns() // 1000
        try:
            yield ev
        finally:
            t1 = time.time_ns() // 1000
            if ev.cached:
                self.cache_hits += 1
            elif ev.input_tokens or ev.output_tokens:
                self.cache_misses += 1
            usd = self.cost(model, ev.input_tokens, ev.output_tokens, ev.cached_in)
            self.store.add_event(
                self.run_id,
                stage,
                question_id=question_id,
                provider=provider,
                model=model,
                started_at=t0,
                ended_at=t1,
                input_tokens=ev.input_tokens,
                output_tokens=ev.output_tokens,
                cached_input_tokens=ev.cached_in,
                cached=ev.cached,
                usd=usd,
            )
