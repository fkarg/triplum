"""The run store is the metrics store: runs, per-question rows, timed and priced events, prices."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, Self

import polars as pl

from triplum.cache import content_key
from triplum.data.schema import now_us

RUN_QUESTIONS_DDL = """
CREATE TABLE IF NOT EXISTS run_questions (
  run_id TEXT NOT NULL REFERENCES runs(run_id), question_id TEXT NOT NULL, retrieved_json TEXT NOT NULL,
  answer TEXT NOT NULL, em REAL NOT NULL, f1 REAL NOT NULL, contain REAL NOT NULL, judge REAL,
  r2 REAL, r5 REAL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
  usd REAL, cached INTEGER NOT NULL DEFAULT 0, latency_s REAL NOT NULL, n_passages INTEGER NOT NULL,
  PRIMARY KEY (run_id, question_id)
) STRICT;
"""

DDL = (
    RUN_QUESTIONS_DDL
    + """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, identity_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
  dataset TEXT NOT NULL, pipeline TEXT NOT NULL, config_hash TEXT NOT NULL, config_json TEXT NOT NULL,
  code_version TEXT NOT NULL, dirty INTEGER NOT NULL, code_hash TEXT NOT NULL,
  corpus_hash TEXT NOT NULL, questions_hash TEXT NOT NULL,
  n INTEGER NOT NULL, embedding_spec TEXT, reranker_spec TEXT, reader_model TEXT NOT NULL, judge_model TEXT,
  seed INTEGER NOT NULL, viewer_json TEXT NOT NULL, host TEXT NOT NULL,
  reader_prompt_hash TEXT NOT NULL, judge_prompt_hash TEXT,
  status TEXT NOT NULL DEFAULT 'running', wall_s REAL, cache_hits INTEGER, cache_misses INTEGER
) STRICT;
CREATE INDEX IF NOT EXISTS runs_identity ON runs(identity_hash);
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
)

# code_hash (the pipeline's own source files) identifies a run; code_version and dirty are
# recorded for bookkeeping only, so edits outside the pipeline do not orphan finished runs.
IDENTITY_FIELDS = (
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
        ],
        "run_questions": [("cached", "INTEGER NOT NULL DEFAULT 0")],
    }

    def _migrate(self) -> None:
        for table, cols in self.MIGRATIONS.items():
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        # r2/r5 became nullable (recall is undefined without gold chunks); SQLite cannot drop a
        # NOT NULL, so stores created before that rebuild the table once.
        notnull = {r[1]: r[3] for r in self.conn.execute("PRAGMA table_info(run_questions)")}
        if notnull.get("r2"):
            cols = ", ".join(notnull)
            self.conn.executescript(
                "ALTER TABLE run_questions RENAME TO run_questions_old;"
                + RUN_QUESTIONS_DDL
                + f"INSERT INTO run_questions ({cols}) SELECT {cols} FROM run_questions_old;"
                "DROP TABLE run_questions_old;"
            )

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

    def add_artifact(self, run_id: str, kind: str, path: str, sha256: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO run_artifacts VALUES (?,?,?,?)", (run_id, kind, path, sha256)
        )

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
        """Newest first: run_id, dataset, pipeline, status, n, reader_model, embedding_spec."""
        return self._frame(
            "SELECT run_id, dataset, pipeline, status, n, reader_model, embedding_spec"
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
