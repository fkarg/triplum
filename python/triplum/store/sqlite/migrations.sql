-- triplum SQLite store, schema v2 (v1 had NOT NULL confidence on facts and mentions). Times are INTEGER microseconds UTC.
-- Open interval ends use the sentinel 9223372036854775807.
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
-- The store's own record of every store-effect stage (ingestion, embeddings, the graph) by
-- execution key: a stage asks here, not the run store, whether its effect is already present.
CREATE TABLE IF NOT EXISTS effects (
  key          TEXT PRIMARY KEY,
  stage        TEXT NOT NULL,
  started_us   INTEGER NOT NULL,
  completed_us INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  source      TEXT NOT NULL,
  uri         TEXT,
  observed_at INTEGER NOT NULL,
  metadata    TEXT,
  acl_hash    TEXT NOT NULL,
  acl_tokens  TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS documents_acl ON documents(acl_hash);

CREATE TABLE IF NOT EXISTS document_grants (
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  principal   TEXT NOT NULL,
  granted_at  INTEGER NOT NULL,
  revoked_at  INTEGER,
  PRIMARY KEY (document_id, principal, granted_at)
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS grants_principal_live ON document_grants(principal, document_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS chunks (
  id          INTEGER PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  parent_id   INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
  level       INTEGER NOT NULL DEFAULT 0,
  span_start  INTEGER NOT NULL,
  span_end    INTEGER NOT NULL,
  text        TEXT NOT NULL,
  acl_tokens  TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id, span_start);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, acl_tokens,
  content = 'chunks', content_rowid = 'id',
  tokenize = "unicode61 remove_diacritics 2"
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text, acl_tokens) VALUES (new.id, new.text, new.acl_tokens);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, acl_tokens) VALUES ('delete', old.id, old.text, old.acl_tokens);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, acl_tokens) VALUES ('delete', old.id, old.text, old.acl_tokens);
  INSERT INTO chunks_fts(rowid, text, acl_tokens) VALUES (new.id, new.text, new.acl_tokens);
END;

CREATE TABLE IF NOT EXISTS embedding_specs (
  spec_hash TEXT PRIMARY KEY,
  spec_json TEXT NOT NULL,
  dims      INTEGER NOT NULL
) STRICT;

-- Graph tables (design D2). confidence is null where the extractor has no calibrated probability.
CREATE TABLE IF NOT EXISTS entities (
  id           TEXT PRIMARY KEY,
  canonical_id TEXT REFERENCES entities(id)
) STRICT;

CREATE TABLE IF NOT EXISTS facts (
  id                     INTEGER PRIMARY KEY,
  proposition_id         TEXT NOT NULL,
  subject_id             TEXT NOT NULL REFERENCES entities(id),
  predicate              TEXT NOT NULL,
  object_id              TEXT REFERENCES entities(id),
  object_literal         TEXT,
  object_datatype        TEXT,
  object_lang            TEXT,
  valid_from             INTEGER NOT NULL DEFAULT 0,
  valid_to               INTEGER NOT NULL DEFAULT 9223372036854775807,
  recorded_at            INTEGER NOT NULL,
  invalidated_at         INTEGER,
  invalidated_by_fact_id INTEGER REFERENCES facts(id),
  confidence             REAL,
  CHECK ((object_id IS NULL) <> (object_literal IS NULL)),
  CHECK (valid_from < valid_to)
) STRICT;
CREATE INDEX IF NOT EXISTS facts_spo_live ON facts(subject_id, predicate, valid_from, valid_to) WHERE invalidated_at IS NULL;
CREATE INDEX IF NOT EXISTS facts_ops_live ON facts(object_id, predicate, valid_from, valid_to) WHERE invalidated_at IS NULL AND object_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS facts_proposition ON facts(proposition_id);

CREATE TABLE IF NOT EXISTS fact_support (
  fact_id     INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
  group_no    INTEGER NOT NULL,
  chunk_id    INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  extractor   TEXT NOT NULL,
  recorded_at INTEGER NOT NULL,
  PRIMARY KEY (fact_id, group_no, chunk_id)
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS fact_support_chunk ON fact_support(chunk_id, fact_id);

CREATE TABLE IF NOT EXISTS mentions (
  entity_id  TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  chunk_id   INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  span_start INTEGER NOT NULL,
  span_end   INTEGER NOT NULL,
  confidence REAL,
  PRIMARY KEY (chunk_id, span_start, entity_id)
) STRICT, WITHOUT ROWID;

INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '2');
