# Harness part 1: scaffold, data layer, SQLite store, model protocols

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (code is written in-session per repository policy; subagents review only). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A buildable `triplum` package (Python over a tiny Rust core) with the canonical Arrow schemas, a SQLite store that filters BM25 and vector search by viewer inside the index, and cached, swappable LLM, embedder and reranker protocols with fakes for tests.

**Architecture:** Rust crate `triplum-core` owns the Arrow schemas; `triplum-py` exposes them through PyO3 and pyo3-arrow; Python reads them as pyarrow schemas. Everything else in this plan is Python: a content-addressed cache, three model protocols with an OpenAI-compatible adapter each plus deterministic fakes, and a SQLite store (FTS5 with an ACL token column, sqlite-vec `vec0` partitioned by principal-set hash) whose every read takes a `Viewer`.

**Tech Stack:** uv, maturin 1.15 (mixed layout), PyO3 0.29, pyo3-arrow 0.19, arrow-schema 59, Python 3.12+, polars, pyarrow, numpy, sqlite-vec 0.1.9, openai SDK, pytest. Optional extras: sentence-transformers, fastembed.

Spec: `docs/specs/2026-09-16-harness-and-baselines.md`. Design: `docs/research/design.md` (D2, D4, D6, D6a, D7).

---

## File structure

```
pyproject.toml                       package metadata, maturin + uv config, extras
Cargo.toml                           workspace
crates/triplum-core/Cargo.toml
crates/triplum-core/src/lib.rs       pub mod schema; pub mod time;
crates/triplum-core/src/time.rs      TS_MAX
crates/triplum-core/src/schema.rs    one fn per canonical table -> SchemaRef; by_name()
crates/triplum-py/Cargo.toml
crates/triplum-py/src/lib.rs         #[pymodule] _core: schema(name, dims), ts_max()
python/triplum/__init__.py
python/triplum/data/__init__.py
python/triplum/data/schema.py        pyarrow schemas, TS_MAX, now_us()
python/triplum/data/viewer.py        Viewer
python/triplum/cache.py              Cache: content-addressed bytes store
python/triplum/llm/__init__.py
python/triplum/llm/protocol.py       Message, GenParams, Usage, Completion, LLM
python/triplum/llm/cached.py         CachedLLM wrapper
python/triplum/llm/fake.py           FakeLLM
python/triplum/llm/openai_compat.py  OpenAICompatLLM
python/triplum/llm/cli.py            CliLLM (subprocess)
python/triplum/embed/__init__.py
python/triplum/embed/protocol.py     EmbeddingSpec, Embedder
python/triplum/embed/cached.py       CachedEmbedder
python/triplum/embed/fake.py         FakeEmbedder
python/triplum/embed/openai_compat.py
python/triplum/embed/sentence_transformers.py
python/triplum/embed/fastembed.py
python/triplum/rerank/__init__.py
python/triplum/rerank/protocol.py    RerankSpec, Reranker
python/triplum/rerank/fake.py
python/triplum/rerank/cross_encoder.py
python/triplum/store/__init__.py
python/triplum/store/protocol.py     Store, Capabilities
python/triplum/store/sqlite/__init__.py
python/triplum/store/sqlite/migrations.sql
python/triplum/store/sqlite/acl.py   principal tokens, acl hash
python/triplum/store/sqlite/store.py SqliteStore
tests/conftest.py
tests/test_schema.py
tests/test_viewer.py
tests/test_cache.py
tests/test_llm.py
tests/test_embed.py
tests/test_rerank.py
tests/test_store_documents.py
tests/test_store_bm25.py
tests/test_store_vector.py
```

Conventions used throughout: timestamps are `int` microseconds since the Unix epoch, UTC; `TS_MAX = 9223372036854775807` is the open-interval sentinel; every hash is `sha256` hex truncated to 16 characters unless stated otherwise; canonical JSON is `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.

---

### Task 1: Scaffold that builds

**Files:**
- Create: `pyproject.toml`, `Cargo.toml`, `crates/triplum-core/Cargo.toml`, `crates/triplum-core/src/lib.rs`, `crates/triplum-core/src/time.rs`, `crates/triplum-core/src/schema.rs`, `crates/triplum-py/Cargo.toml`, `crates/triplum-py/src/lib.rs`, `python/triplum/__init__.py`, `python/triplum/data/__init__.py`, `python/triplum/data/schema.py`, `tests/conftest.py`, `tests/test_schema.py`
- Modify: `.gitignore` (add `target/`, `.venv/`, `*.so`)

- [ ] **Step 1: Write the failing test**

`tests/test_schema.py`:
```python
import pyarrow as pa

from triplum.data import schema


def test_documents_schema_columns():
    assert schema.DOCUMENTS.names == ["id", "source", "uri", "observed_at", "metadata"]
    assert schema.DOCUMENTS.field("observed_at").type == pa.timestamp("us", tz="UTC")


def test_chunks_schema_columns():
    assert schema.CHUNKS.names == [
        "id",
        "document_id",
        "parent_id",
        "level",
        "span_start",
        "span_end",
        "text",
    ]
    assert schema.CHUNKS.field("id").type == pa.int64()


def test_chunk_embeddings_is_parametric_in_dims():
    s = schema.chunk_embeddings(4)
    assert s.names == ["chunk_id", "embedding_spec", "vector"]
    assert s.field("vector").type == pa.list_(pa.float32(), 4)


def test_facts_schema_columns():
    assert schema.FACTS.names == [
        "id",
        "proposition_id",
        "subject_id",
        "predicate",
        "object_id",
        "object_literal",
        "object_datatype",
        "object_lang",
        "valid_from",
        "valid_to",
        "recorded_at",
        "invalidated_at",
        "invalidated_by_fact_id",
        "confidence",
    ]


def test_ts_max_sentinel():
    assert schema.TS_MAX == 9223372036854775807
```

`tests/conftest.py`:
```python
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "store.sqlite"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL (no module `triplum`; uv will first fail to build because the project files do not exist yet, which is fine).

- [ ] **Step 3: Write the project files**

`pyproject.toml`:
```toml
[project]
name = "triplum"
version = "0.0.1"
description = "Composable, benchmark-first sandbox for LLM knowledge-graph construction, GraphRAG and evaluation"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.12"
dependencies = [
  "polars>=1.44",
  "pyarrow>=25",
  "numpy>=2.3",
  "sqlite-vec>=0.1.9,<0.2",
  "openai>=3,<4",
]

[project.optional-dependencies]
local = ["sentence-transformers>=6", "fastembed>=0.8"]

[dependency-groups]
dev = ["pytest>=9", "ruff>=0.14", "maturin>=1.15,<2", "marimo>=0.24"]

[build-system]
requires = ["maturin>=1.15,<2"]
build-backend = "maturin"

[tool.maturin]
python-source = "python"
module-name = "triplum._core"
manifest-path = "crates/triplum-py/Cargo.toml"
features = ["pyo3/extension-module"]

[tool.uv]
cache-keys = [{ file = "pyproject.toml" }, { file = "Cargo.toml" }, { file = "crates/**/Cargo.toml" }, { file = "crates/**/*.rs" }]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

`Cargo.toml`:
```toml
[workspace]
resolver = "2"
members = ["crates/triplum-core", "crates/triplum-py"]

[workspace.package]
version = "0.0.1"
edition = "2021"
license = "Apache-2.0"

[workspace.dependencies]
arrow-schema = "59"
pyo3 = { version = "0.29", features = ["abi3-py312"] }
pyo3-arrow = "0.19"
```

`crates/triplum-core/Cargo.toml`:
```toml
[package]
name = "triplum-core"
version.workspace = true
edition.workspace = true
license.workspace = true

[dependencies]
arrow-schema = { workspace = true }
```

`crates/triplum-core/src/lib.rs`:
```rust
pub mod schema;
pub mod time;
```

`crates/triplum-core/src/time.rs`:
```rust
/// Open-interval sentinel for `valid_to` / `recorded_to`: i64::MAX microseconds.
pub const TS_MAX: i64 = i64::MAX;
```

`crates/triplum-core/src/schema.rs`:
```rust
use std::sync::Arc;

use arrow_schema::{DataType, Field, Schema, SchemaRef, TimeUnit};

fn ts() -> DataType {
    DataType::Timestamp(TimeUnit::Microsecond, Some("UTC".into()))
}

fn f(name: &str, dt: DataType, nullable: bool) -> Field {
    Field::new(name, dt, nullable)
}

pub fn documents() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Utf8, false),
        f("source", DataType::Utf8, false),
        f("uri", DataType::Utf8, true),
        f("observed_at", ts(), false),
        f("metadata", DataType::Utf8, true),
    ]))
}

pub fn document_grants() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("document_id", DataType::Utf8, false),
        f("principal", DataType::Utf8, false),
        f("granted_at", ts(), false),
        f("revoked_at", ts(), true),
    ]))
}

pub fn chunks() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Int64, false),
        f("document_id", DataType::Utf8, false),
        f("parent_id", DataType::Int64, true),
        f("level", DataType::Int32, false),
        f("span_start", DataType::Int64, false),
        f("span_end", DataType::Int64, false),
        f("text", DataType::Utf8, false),
    ]))
}

pub fn chunk_embeddings(dims: i32) -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("chunk_id", DataType::Int64, false),
        f("embedding_spec", DataType::Utf8, false),
        f(
            "vector",
            DataType::FixedSizeList(Arc::new(Field::new("item", DataType::Float32, false)), dims),
            false,
        ),
    ]))
}

pub fn entities() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Utf8, false),
        f("canonical_id", DataType::Utf8, true),
    ]))
}

pub fn facts() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("id", DataType::Int64, false),
        f("proposition_id", DataType::Utf8, false),
        f("subject_id", DataType::Utf8, false),
        f("predicate", DataType::Utf8, false),
        f("object_id", DataType::Utf8, true),
        f("object_literal", DataType::Utf8, true),
        f("object_datatype", DataType::Utf8, true),
        f("object_lang", DataType::Utf8, true),
        f("valid_from", ts(), false),
        f("valid_to", ts(), false),
        f("recorded_at", ts(), false),
        f("invalidated_at", ts(), true),
        f("invalidated_by_fact_id", DataType::Int64, true),
        f("confidence", DataType::Float32, false),
    ]))
}

pub fn fact_support() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("fact_id", DataType::Int64, false),
        f("group_no", DataType::Int32, false),
        f("chunk_id", DataType::Int64, false),
        f("extractor", DataType::Utf8, false),
        f("recorded_at", ts(), false),
    ]))
}

pub fn mentions() -> SchemaRef {
    Arc::new(Schema::new(vec![
        f("entity_id", DataType::Utf8, false),
        f("chunk_id", DataType::Int64, false),
        f("span_start", DataType::Int64, false),
        f("span_end", DataType::Int64, false),
        f("confidence", DataType::Float32, false),
    ]))
}

/// Look a canonical schema up by table name. `dims` is only used by `chunk_embeddings`.
pub fn by_name(name: &str, dims: Option<i32>) -> Option<SchemaRef> {
    match name {
        "documents" => Some(documents()),
        "document_grants" => Some(document_grants()),
        "chunks" => Some(chunks()),
        "chunk_embeddings" => dims.map(chunk_embeddings),
        "entities" => Some(entities()),
        "facts" => Some(facts()),
        "fact_support" => Some(fact_support()),
        "mentions" => Some(mentions()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_table_resolves() {
        for name in ["documents", "document_grants", "chunks", "entities", "facts", "fact_support", "mentions"] {
            assert!(by_name(name, None).is_some(), "{name}");
        }
        assert_eq!(by_name("chunk_embeddings", Some(8)).unwrap().fields().len(), 3);
        assert!(by_name("chunk_embeddings", None).is_none());
        assert!(by_name("nope", None).is_none());
    }
}
```

`crates/triplum-py/Cargo.toml`:
```toml
[package]
name = "triplum-py"
version.workspace = true
edition.workspace = true
license.workspace = true

[lib]
name = "_core"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { workspace = true }
pyo3-arrow = { workspace = true }
triplum-core = { path = "../triplum-core" }
```

`crates/triplum-py/src/lib.rs`:
```rust
use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3_arrow::PySchema;

/// Canonical Arrow schema by table name. `dims` is required for `chunk_embeddings`.
#[pyfunction]
#[pyo3(signature = (name, dims=None))]
fn schema(name: &str, dims: Option<i32>) -> PyResult<PySchema> {
    triplum_core::schema::by_name(name, dims)
        .map(PySchema::new)
        .ok_or_else(|| PyKeyError::new_err(format!("unknown schema: {name}")))
}

#[pyfunction]
fn ts_max() -> i64 {
    triplum_core::time::TS_MAX
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(schema, m)?)?;
    m.add_function(wrap_pyfunction!(ts_max, m)?)?;
    Ok(())
}
```

`python/triplum/__init__.py`:
```python
"""triplum: composable, benchmark-first sandbox for LLM knowledge-graph work."""

__version__ = "0.0.1"
```

`python/triplum/data/__init__.py`: empty file.

`python/triplum/data/schema.py`:
```python
"""Canonical Arrow schemas, owned by the Rust core and re-exported here as pyarrow schemas."""

from __future__ import annotations

import time

import pyarrow as pa

from triplum import _core

TS_MAX: int = _core.ts_max()


def _schema(name: str, dims: int | None = None) -> pa.Schema:
    return pa.schema(_core.schema(name, dims))


DOCUMENTS = _schema("documents")
DOCUMENT_GRANTS = _schema("document_grants")
CHUNKS = _schema("chunks")
ENTITIES = _schema("entities")
FACTS = _schema("facts")
FACT_SUPPORT = _schema("fact_support")
MENTIONS = _schema("mentions")


def chunk_embeddings(dims: int) -> pa.Schema:
    return _schema("chunk_embeddings", dims)


def now_us() -> int:
    """Current UTC time in microseconds since the epoch."""
    return time.time_ns() // 1000
```

Append to `.gitignore`:
```
# build
target/
.venv/
*.so
```

- [ ] **Step 4: Build and run the tests**

Run: `cargo test -p triplum-core`
Expected: `test schema::tests::every_table_resolves ... ok`

Run: `uv sync --all-extras --group dev && uv run pytest tests/test_schema.py -v`
Expected: 5 passed. (`uv sync` builds the extension via maturin; the first build takes a minute.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml Cargo.toml Cargo.lock crates python tests .gitignore
git commit -m "Scaffold: uv + maturin mixed layout, Rust core with canonical Arrow schemas"
```

---

### Task 2: Viewer

**Files:**
- Create: `python/triplum/data/viewer.py`
- Test: `tests/test_viewer.py`

- [ ] **Step 1: Write the failing test**

`tests/test_viewer.py`:
```python
import pytest

from triplum.data.schema import TS_MAX
from triplum.data.viewer import Viewer


def test_defaults_are_now_and_public():
    v = Viewer(principals=frozenset({"public"}))
    assert v.principals == frozenset({"public"})
    assert v.as_of_valid <= TS_MAX and v.as_of_valid > 0
    assert v.as_of_recorded == v.as_of_valid
    assert v.permission_revision is None


def test_principals_are_normalised_to_frozenset():
    v = Viewer(principals=["b", "a", "a"])
    assert v.principals == frozenset({"a", "b"})


def test_viewer_is_hashable_and_stable():
    a = Viewer(principals={"x"}, as_of_valid=10, as_of_recorded=10)
    b = Viewer(principals={"x"}, as_of_valid=10, as_of_recorded=10)
    assert hash(a) == hash(b) and a == b


def test_empty_principals_rejected():
    with pytest.raises(ValueError):
        Viewer(principals=[])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_viewer.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.data.viewer`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/data/viewer.py`:
```python
"""The query context every store read takes: who is asking, and as of when."""

from __future__ import annotations

from dataclasses import dataclass, field

from triplum.data.schema import now_us


@dataclass(frozen=True)
class Viewer:
    """principals: identities the caller holds. as_of_valid: world time. as_of_recorded:
    transaction time. permission_revision: the ACL snapshot the query was authorised against
    (None = current)."""

    principals: frozenset[str]
    as_of_valid: int = field(default_factory=now_us)
    as_of_recorded: int | None = None
    permission_revision: int | None = None

    def __post_init__(self) -> None:
        ps = (
            frozenset(self.principals)
            if not isinstance(self.principals, frozenset)
            else self.principals
        )
        if not ps:
            raise ValueError("Viewer needs at least one principal")
        object.__setattr__(self, "principals", ps)
        if self.as_of_recorded is None:
            object.__setattr__(self, "as_of_recorded", self.as_of_valid)

    @classmethod
    def of(cls, *principals: str, **kw) -> "Viewer":
        return cls(principals=frozenset(principals), **kw)

    def sorted_principals(self) -> list[str]:
        return sorted(self.principals)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_viewer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/data/viewer.py tests/test_viewer.py
git commit -m "Add Viewer: principals plus as-of on both time axes"
```

---

### Task 3: Content-addressed cache

**Files:**
- Create: `python/triplum/cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cache.py`:
```python
from triplum.cache import Cache, canonical_json, content_key


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})


def test_content_key_changes_with_kind_and_payload():
    k1 = content_key("llm", {"m": "x"})
    k2 = content_key("embed", {"m": "x"})
    k3 = content_key("llm", {"m": "y"})
    assert len(k1) == 64 and k1 != k2 and k1 != k3


def test_cache_roundtrip_and_miss(tmp_path):
    c = Cache(tmp_path)
    key = content_key("llm", {"q": 1})
    assert c.get(key) is None
    c.put(key, b"hello")
    assert c.get(key) == b"hello"
    assert (tmp_path / key[:2] / key).exists()


def test_cache_json_helpers(tmp_path):
    c = Cache(tmp_path)
    key = content_key("x", {})
    assert c.get_json(key) is None
    c.put_json(key, {"a": 1})
    assert c.get_json(key) == {"a": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.cache`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/cache.py`:
```python
"""Content-addressed disk cache shared by LLM, embedder and reranker adapters.

Keys are sha256 over (kind, canonical JSON payload). One file per entry, sharded by the first two
hex characters. The cache is per machine (design D6a); nothing requires it to exist.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_key(kind: str, payload: Any) -> str:
    h = hashlib.sha256()
    h.update(kind.encode())
    h.update(b"\0")
    h.update(canonical_json(payload).encode())
    return h.hexdigest()


def default_root() -> Path:
    return Path(os.environ.get("TRIPLUM_CACHE", Path.home() / ".cache" / "triplum"))


class Cache:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / key

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def get_json(self, key: str) -> Any | None:
        raw = self.get(key)
        return None if raw is None else json.loads(raw)

    def put_json(self, key: str, obj: Any) -> None:
        self.put(key, canonical_json(obj).encode())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cache.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/cache.py tests/test_cache.py
git commit -m "Add content-addressed disk cache"
```

---

### Task 4: LLM protocol, fake, cached wrapper

**Files:**
- Create: `python/triplum/llm/__init__.py`, `python/triplum/llm/protocol.py`, `python/triplum/llm/fake.py`, `python/triplum/llm/cached.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/test_llm.py`:
```python
import json

from triplum.cache import Cache
from triplum.llm.cached import CachedLLM
from triplum.llm.fake import FakeLLM
from triplum.llm.protocol import GenParams, Message, request_payload


def test_request_payload_includes_schema_and_params():
    msgs = [Message("user", "hi")]
    p1 = request_payload("fake", "m", msgs, None, GenParams())
    p2 = request_payload("fake", "m", msgs, {"type": "object"}, GenParams())
    p3 = request_payload("fake", "m", msgs, None, GenParams(temperature=0.5))
    assert p1 != p2 and p1 != p3


def test_fake_llm_is_deterministic_and_reports_usage():
    llm = FakeLLM()
    a = llm.complete([Message("user", "What is 2+2?")])
    b = llm.complete([Message("user", "What is 2+2?")])
    assert a.text == b.text and a.usage.output_tokens > 0 and a.cached is False


def test_fake_llm_structured_output_parses():
    llm = FakeLLM(responder=lambda msgs, schema: json.dumps({"answer": "4"}))
    c = llm.complete([Message("user", "q")], schema={"type": "object"})
    assert c.parsed == {"answer": "4"}


def test_cached_llm_hits_on_second_call(tmp_path):
    calls = []

    def responder(msgs, schema):
        calls.append(1)
        return "x"

    llm = CachedLLM(FakeLLM(responder=responder), Cache(tmp_path))
    c1 = llm.complete([Message("user", "q")])
    c2 = llm.complete([Message("user", "q")])
    assert len(calls) == 1 and c1.cached is False and c2.cached is True
    assert c1.text == c2.text and c1.request_hash == c2.request_hash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.llm`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/llm/__init__.py`: empty.

`python/triplum/llm/protocol.py`:
```python
"""One LLM protocol. Adapters implement `complete`; pipelines never import a provider SDK."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from triplum.cache import content_key


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class GenParams:
    temperature: float = 0.0
    max_tokens: int = 1024
    seed: int | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    text: str
    parsed: Any | None
    usage: Usage
    model: str
    request_hash: str
    cached: bool = False
    raw: dict = field(default_factory=dict)


def request_payload(
    adapter: str, model: str, messages: list[Message], schema: dict | None, params: GenParams
) -> dict:
    """The full effective request (design D6). Everything that changes the answer is in here."""
    return {
        "adapter": adapter,
        "model": model,
        "messages": [asdict(m) for m in messages],
        "schema": schema,
        "params": asdict(params),
    }


def request_hash(adapter: str, model: str, messages, schema, params) -> str:
    return content_key("llm", request_payload(adapter, model, messages, schema, params))


class LLM(Protocol):
    adapter: str
    model: str

    def complete(
        self,
        messages: list[Message],
        *,
        schema: dict | None = None,
        params: GenParams = GenParams(),
    ) -> Completion: ...
```

`python/triplum/llm/fake.py`:
```python
"""Deterministic LLM for tests. Default responder echoes a hash of the last user message."""

from __future__ import annotations

import hashlib
import json
from typing import Callable

from triplum.llm.protocol import Completion, GenParams, Message, Usage, request_hash

Responder = Callable[[list[Message], dict | None], str]


def _default_responder(messages: list[Message], schema: dict | None) -> str:
    last = messages[-1].content
    digest = hashlib.sha256(last.encode()).hexdigest()[:8]
    if schema is not None:
        return json.dumps({"answer": digest})
    return f"fake-answer-{digest}"


class FakeLLM:
    adapter = "fake"

    def __init__(self, responder: Responder = _default_responder, model: str = "fake-1") -> None:
        self.responder = responder
        self.model = model

    def complete(self, messages, *, schema=None, params=GenParams()) -> Completion:
        text = self.responder(messages, schema)
        parsed = json.loads(text) if schema is not None else None
        n_in = sum(len(m.content.split()) for m in messages)
        return Completion(
            text=text,
            parsed=parsed,
            usage=Usage(input_tokens=n_in, output_tokens=max(1, len(text.split()))),
            model=self.model,
            request_hash=request_hash(self.adapter, self.model, messages, schema, params),
        )
```

`python/triplum/llm/cached.py`:
```python
"""Wrap any LLM with the disk cache. A hit is an exact replay and is marked as such."""

from __future__ import annotations

from dataclasses import asdict

from triplum.cache import Cache
from triplum.llm.protocol import LLM, Completion, GenParams, Usage, request_hash


class CachedLLM:
    def __init__(self, inner: LLM, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.adapter = inner.adapter
        self.model = inner.model

    def complete(self, messages, *, schema=None, params=GenParams()) -> Completion:
        key = request_hash(self.adapter, self.model, messages, schema, params)
        hit = self.cache.get_json(key)
        if hit is not None:
            return Completion(
                text=hit["text"],
                parsed=hit["parsed"],
                usage=Usage(**hit["usage"]),
                model=hit["model"],
                request_hash=key,
                cached=True,
                raw=hit.get("raw", {}),
            )
        c = self.inner.complete(messages, schema=schema, params=params)
        self.cache.put_json(
            key,
            {
                "text": c.text,
                "parsed": c.parsed,
                "usage": asdict(c.usage),
                "model": c.model,
                "raw": c.raw,
            },
        )
        return c
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_llm.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/llm tests/test_llm.py
git commit -m "Add LLM protocol with deterministic fake and cached wrapper"
```

---

### Task 5: OpenAI-compatible and CLI LLM adapters

**Files:**
- Create: `python/triplum/llm/openai_compat.py`, `python/triplum/llm/cli.py`
- Test: append to `tests/test_llm.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_llm.py`:
```python
import os
import sys

import pytest

from triplum.llm.cli import CliLLM
from triplum.llm.openai_compat import OpenAICompatLLM


def test_openai_compat_builds_request_and_parses(monkeypatch):
    sent = {}

    class _Msg:
        content = '{"answer": "4"}'

    class _Choice:
        message = _Msg()

    class _Usage:
        prompt_tokens = 7
        completion_tokens = 3
        prompt_tokens_details = None

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()
        model = "test-model"

        def model_dump(self):
            return {"id": "r1"}

    class _Completions:
        def create(self, **kw):
            sent.update(kw)
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    llm = OpenAICompatLLM(model="test-model", client=_Client())
    c = llm.complete([Message("user", "q")], schema={"type": "object"})
    assert sent["model"] == "test-model"
    assert sent["response_format"]["type"] == "json_schema"
    assert c.parsed == {"answer": "4"} and c.usage.input_tokens == 7 and c.usage.output_tokens == 3


def test_cli_llm_runs_command_and_reads_stdout():
    llm = CliLLM(
        model="echo", argv=[sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"]
    )
    c = llm.complete([Message("user", "hello")])
    assert "HELLO" in c.text and c.usage.output_tokens >= 1


def test_cli_llm_json_output_field():
    argv = [
        sys.executable,
        "-c",
        "import json,sys; sys.stdin.read(); print(json.dumps({'result': 'ok'}))",
    ]
    llm = CliLLM(model="x", argv=argv, json_field="result")
    assert llm.complete([Message("user", "q")]).text == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm.py -v`
Expected: the three new tests FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/llm/openai_compat.py`:
```python
"""OpenAI-compatible chat completions: OpenAI, OpenRouter, vLLM, Ollama, LM Studio, ...

The API key is read by the SDK from the environment; never pass it as a literal.
"""

from __future__ import annotations

import json
import os
from typing import Any

from triplum.llm.protocol import Completion, GenParams, Message, Usage, request_hash


class OpenAICompatLLM:
    adapter = "openai_compat"

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        client: Any | None = None,
        max_parse_retries: int = 1,
    ) -> None:
        self.model = model
        self.max_parse_retries = max_parse_retries
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env))
        self.client = client

    def _call(self, messages: list[Message], schema: dict | None, params: GenParams):
        kw: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.seed is not None:
            kw["seed"] = params.seed
        if schema is not None:
            kw["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": False},
            }
        return self.client.chat.completions.create(**kw)

    def complete(self, messages, *, schema=None, params=GenParams()) -> Completion:
        attempts = 0
        while True:
            resp = self._call(messages, schema, params)
            text = resp.choices[0].message.content or ""
            parsed = None
            if schema is not None:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    attempts += 1
                    if attempts <= self.max_parse_retries:
                        messages = [
                            *messages,
                            Message("assistant", text),
                            Message("user", "Return only valid JSON matching the schema."),
                        ]
                        continue
            u = resp.usage
            details = getattr(u, "prompt_tokens_details", None)
            cached_in = getattr(details, "cached_tokens", 0) if details else 0
            return Completion(
                text=text,
                parsed=parsed,
                usage=Usage(
                    input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(u, "completion_tokens", 0) or 0,
                    cached_input_tokens=cached_in or 0,
                ),
                model=getattr(resp, "model", self.model) or self.model,
                request_hash=request_hash(self.adapter, self.model, messages, schema, params),
                raw=resp.model_dump() if hasattr(resp, "model_dump") else {},
            )
```

`python/triplum/llm/cli.py`:
```python
"""Local CLI harness as an LLM: the prompt goes to stdin, the answer comes from stdout.

Must be invoked statelessly (no ambient session, tools or filesystem context) to satisfy the
cache contract (design D6). Preset for Claude Code: `claude -p --output-format json`, answer in
the `result` field. Usage counts are approximated from whitespace tokens because CLIs do not
report them uniformly.
"""

from __future__ import annotations

import json
import subprocess

from triplum.llm.protocol import Completion, GenParams, Message, Usage, request_hash

CLAUDE_PRESET = {"argv": ["claude", "-p", "--output-format", "json"], "json_field": "result"}


def render_prompt(messages: list[Message]) -> str:
    return "\n\n".join(f"[{m.role}]\n{m.content}" for m in messages)


class CliLLM:
    adapter = "cli"

    def __init__(
        self, model: str, argv: list[str], json_field: str | None = None, timeout_s: int = 600
    ) -> None:
        self.model = model
        self.argv = argv
        self.json_field = json_field
        self.timeout_s = timeout_s

    def complete(self, messages, *, schema=None, params=GenParams()) -> Completion:
        prompt = render_prompt(messages)
        if schema is not None:
            prompt += "\n\nRespond with JSON only, matching this schema:\n" + json.dumps(schema)
        proc = subprocess.run(
            self.argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=True,
        )
        text = proc.stdout.strip()
        if self.json_field is not None:
            text = str(json.loads(text)[self.json_field])
        parsed = json.loads(text) if schema is not None else None
        return Completion(
            text=text,
            parsed=parsed,
            usage=Usage(input_tokens=len(prompt.split()), output_tokens=max(1, len(text.split()))),
            model=self.model,
            request_hash=request_hash(self.adapter, self.model, messages, schema, params),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/llm tests/test_llm.py
git commit -m "Add OpenAI-compatible and CLI subprocess LLM adapters"
```

---

### Task 6: Embedder protocol, fake, cached wrapper, OpenAI-compatible adapter

**Files:**
- Create: `python/triplum/embed/__init__.py`, `python/triplum/embed/protocol.py`, `python/triplum/embed/fake.py`, `python/triplum/embed/cached.py`, `python/triplum/embed/openai_compat.py`
- Test: `tests/test_embed.py`

- [ ] **Step 1: Write the failing test**

`tests/test_embed.py`:
```python
import numpy as np

from triplum.cache import Cache
from triplum.embed.cached import CachedEmbedder
from triplum.embed.fake import FakeEmbedder
from triplum.embed.openai_compat import OpenAICompatEmbedder
from triplum.embed.protocol import EmbeddingSpec


def test_spec_hash_is_stable_and_sensitive():
    a = EmbeddingSpec(model="m", revision="r", dims=8)
    b = EmbeddingSpec(model="m", revision="r", dims=8)
    c = EmbeddingSpec(model="m", revision="r", dims=8, query_prefix="query: ")
    assert a.hash() == b.hash() and a.hash() != c.hash() and len(a.hash()) == 16


def test_fake_embedder_shapes_and_determinism():
    e = FakeEmbedder(dims=8)
    q = e.embed_queries(["a", "b"])
    p = e.embed_passages(["a"])
    assert q.shape == (2, 8) and p.shape == (1, 8) and q.dtype == np.float32
    assert np.allclose(np.linalg.norm(q, axis=1), 1.0)
    assert np.allclose(e.embed_queries(["a"])[0], q[0])


def test_fake_embedder_similar_texts_are_closer():
    e = FakeEmbedder(dims=64)
    v = e.embed_passages(
        ["the cat sat on the mat", "the cat sat on a mat", "quarterly revenue grew"]
    )
    assert v[0] @ v[1] > v[0] @ v[2]


def test_cached_embedder_hits_per_text(tmp_path):
    inner = FakeEmbedder(dims=8)
    calls = []
    orig = inner.embed_passages
    inner.embed_passages = lambda texts: (calls.append(list(texts)), orig(texts))[1]
    e = CachedEmbedder(inner, Cache(tmp_path))
    e.embed_passages(["x", "y"])
    e.embed_passages(["y", "z"])
    assert calls == [["x", "y"], ["z"]]


def test_openai_compat_embedder_calls_client():
    class _Item:
        def __init__(self, v):
            self.embedding = v

    class _Resp:
        def __init__(self, n):
            self.data = [_Item([1.0, 0.0]) for _ in range(n)]

    class _Emb:
        def create(self, **kw):
            return _Resp(len(kw["input"]))

    class _Client:
        embeddings = _Emb()

    spec = EmbeddingSpec(
        model="text-embedding-3-large", revision="2026", dims=2, query_prefix="q: "
    )
    e = OpenAICompatEmbedder(spec, client=_Client())
    out = e.embed_queries(["a", "b"])
    assert out.shape == (2, 2) and np.allclose(out[0], [1.0, 0.0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_embed.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.embed`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/embed/__init__.py`: empty.

`python/triplum/embed/protocol.py`:
```python
"""Embedding spec and protocol. The spec is the identity of an embedding: same model on a different
runtime, or with different prefixes, is a different spec and a different index."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

from triplum.cache import content_key


@dataclass(frozen=True)
class EmbeddingSpec:
    model: str
    revision: str
    dims: int
    pooling: str = "provider"
    normalize: bool = True
    query_prefix: str = ""
    passage_prefix: str = ""
    quantization: str = "none"
    runtime: str = "api"

    def hash(self) -> str:
        return content_key("embedding_spec", asdict(self))[:16]

    def table_name(self) -> str:
        return f"emb_{self.hash()}"


class Embedder(Protocol):
    spec: EmbeddingSpec

    def embed_queries(self, texts: list[str]) -> np.ndarray: ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...


def l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (x / n).astype(np.float32)
```

`python/triplum/embed/fake.py`:
```python
"""Deterministic bag-of-hashed-words embedder for tests: similar texts get similar vectors."""

from __future__ import annotations

import hashlib
import re

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


class FakeEmbedder:
    def __init__(self, dims: int = 64) -> None:
        self.spec = EmbeddingSpec(model="fake", revision="1", dims=dims, runtime="fake")

    def _embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.spec.dims), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in re.findall(r"\w+", t.lower()):
                h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:8], "little")
                out[i, h % self.spec.dims] += 1.0 if (h >> 63) == 0 else -1.0
                out[i, (h >> 8) % self.spec.dims] += 0.5
        return l2_normalize(out)

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts)
```

`python/triplum/embed/cached.py`:
```python
"""Per-text cache around any embedder, keyed on (spec hash, role, text)."""

from __future__ import annotations

import numpy as np

from triplum.cache import Cache, content_key
from triplum.embed.protocol import Embedder


class CachedEmbedder:
    def __init__(self, inner: Embedder, cache: Cache) -> None:
        self.inner = inner
        self.cache = cache
        self.spec = inner.spec

    def _embed(self, texts: list[str], role: str) -> np.ndarray:
        keys = [
            content_key("embed", {"spec": self.spec.hash(), "role": role, "text": t}) for t in texts
        ]
        out = np.zeros((len(texts), self.spec.dims), dtype=np.float32)
        missing: list[int] = []
        for i, k in enumerate(keys):
            raw = self.cache.get(k)
            if raw is None:
                missing.append(i)
            else:
                out[i] = np.frombuffer(raw, dtype=np.float32)
        if missing:
            fn = self.inner.embed_queries if role == "query" else self.inner.embed_passages
            vecs = fn([texts[i] for i in missing])
            for j, i in enumerate(missing):
                out[i] = vecs[j]
                self.cache.put(keys[i], vecs[j].astype(np.float32).tobytes())
        return out

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "query")

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "passage")
```

`python/triplum/embed/openai_compat.py`:
```python
"""OpenAI-compatible embeddings endpoint. Prefixes from the spec are prepended here."""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


class OpenAICompatEmbedder:
    def __init__(
        self,
        spec: EmbeddingSpec,
        *,
        base_url: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        client: Any | None = None,
        batch_size: int = 128,
    ) -> None:
        self.spec = spec
        self.batch_size = batch_size
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env))
        self.client = client

    def _embed(self, texts: list[str], prefix: str) -> np.ndarray:
        rows: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [prefix + t for t in texts[i : i + self.batch_size]]
            resp = self.client.embeddings.create(
                model=self.spec.model, input=batch, dimensions=self.spec.dims
            )
            rows.extend(item.embedding for item in resp.data)
        arr = np.asarray(rows, dtype=np.float32).reshape(len(texts), self.spec.dims)
        return l2_normalize(arr) if self.spec.normalize else arr

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.query_prefix)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.passage_prefix)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_embed.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/embed tests/test_embed.py
git commit -m "Add embedder protocol with spec identity, fake, cache and OpenAI-compatible adapter"
```

---

### Task 7: Local embedder adapters (sentence-transformers, fastembed)

**Files:**
- Create: `python/triplum/embed/sentence_transformers.py`, `python/triplum/embed/fastembed.py`
- Test: append to `tests/test_embed.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_embed.py`:
```python
import importlib.util

import pytest


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None, reason="extra not installed"
)
def test_sentence_transformers_adapter_small_model():
    from triplum.embed.sentence_transformers import SentenceTransformersEmbedder

    e = SentenceTransformersEmbedder.from_model("sentence-transformers/all-MiniLM-L6-v2")
    v = e.embed_passages(["hello world", "hello there"])
    assert v.shape == (2, e.spec.dims) and e.spec.runtime in {"cuda", "mps", "cpu"}
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)


@pytest.mark.skipif(importlib.util.find_spec("fastembed") is None, reason="extra not installed")
def test_fastembed_adapter_small_model():
    from triplum.embed.fastembed import FastEmbedEmbedder

    e = FastEmbedEmbedder.from_model("BAAI/bge-small-en-v1.5")
    v = e.embed_queries(["hello world"])
    assert v.shape == (1, e.spec.dims) and e.spec.runtime == "onnx"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_embed.py -v -k "sentence or fastembed"`
Expected: FAIL with `ModuleNotFoundError` (or SKIPPED if the extras are not installed; install with `uv sync --all-extras --group dev`).

- [ ] **Step 3: Write minimal implementation**

`python/triplum/embed/sentence_transformers.py`:
```python
"""sentence-transformers adapter: picks cuda, mps or cpu and records it in the spec."""

from __future__ import annotations

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class SentenceTransformersEmbedder:
    def __init__(self, spec: EmbeddingSpec, model, batch_size: int = 32) -> None:
        self.spec = spec
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_model(
        cls,
        name: str,
        *,
        query_prefix: str = "",
        passage_prefix: str = "",
        device: str | None = None,
        batch_size: int = 32,
        trust_remote_code: bool = False,
    ) -> "SentenceTransformersEmbedder":
        from sentence_transformers import SentenceTransformer

        device = device or pick_device()
        model = SentenceTransformer(name, device=device, trust_remote_code=trust_remote_code)
        revision = (
            getattr(getattr(model, "model_card_data", None), "base_model_revision", None)
            or "unknown"
        )
        spec = EmbeddingSpec(
            model=name,
            revision=str(revision),
            dims=int(model.get_sentence_embedding_dimension()),
            pooling="model",
            normalize=True,
            query_prefix=query_prefix,
            passage_prefix=passage_prefix,
            quantization="fp32" if device == "cpu" else "fp16",
            runtime=device,
        )
        return cls(spec, model, batch_size)

    def _embed(self, texts: list[str], prefix: str) -> np.ndarray:
        arr = self.model.encode(
            [prefix + t for t in texts],
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        ).astype(np.float32)
        return l2_normalize(arr) if self.spec.normalize else arr

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.query_prefix)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.passage_prefix)
```

`python/triplum/embed/fastembed.py`:
```python
"""fastembed (ONNX) adapter."""

from __future__ import annotations

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize


class FastEmbedEmbedder:
    def __init__(self, spec: EmbeddingSpec, model, batch_size: int = 64) -> None:
        self.spec = spec
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_model(
        cls, name: str, *, query_prefix: str = "", passage_prefix: str = "", batch_size: int = 64
    ):
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=name)
        dims = next(m["dim"] for m in TextEmbedding.list_supported_models() if m["model"] == name)
        spec = EmbeddingSpec(
            model=name,
            revision="fastembed",
            dims=int(dims),
            pooling="model",
            normalize=True,
            query_prefix=query_prefix,
            passage_prefix=passage_prefix,
            quantization="onnx-default",
            runtime="onnx",
        )
        return cls(spec, model, batch_size)

    def _embed(self, texts: list[str], prefix: str) -> np.ndarray:
        arr = np.asarray(
            list(self.model.embed([prefix + t for t in texts], batch_size=self.batch_size)),
            dtype=np.float32,
        )
        return l2_normalize(arr) if self.spec.normalize else arr

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.query_prefix)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.passage_prefix)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv sync --all-extras --group dev && uv run pytest tests/test_embed.py -v`
Expected: 7 passed (the two local tests download small models on first run).

- [ ] **Step 5: Commit**

```bash
git add python/triplum/embed tests/test_embed.py
git commit -m "Add sentence-transformers and fastembed embedder adapters"
```

---

### Task 8: Reranker protocol, fake, cross-encoder adapter

**Files:**
- Create: `python/triplum/rerank/__init__.py`, `python/triplum/rerank/protocol.py`, `python/triplum/rerank/fake.py`, `python/triplum/rerank/cross_encoder.py`
- Test: `tests/test_rerank.py`

- [ ] **Step 1: Write the failing test**

`tests/test_rerank.py`:
```python
import importlib.util

import numpy as np
import pytest

from triplum.rerank.fake import FakeReranker
from triplum.rerank.protocol import RerankSpec


def test_rerank_spec_hash():
    a = RerankSpec(model="m", revision="r")
    assert a.hash() == RerankSpec(model="m", revision="r").hash()


def test_fake_reranker_prefers_overlap():
    r = FakeReranker()
    s = r.score("cat on mat", ["the cat sat on the mat", "revenue grew"])
    assert s.shape == (2,) and s[0] > s[1]


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None, reason="extra not installed"
)
def test_cross_encoder_small_model():
    from triplum.rerank.cross_encoder import CrossEncoderReranker

    r = CrossEncoderReranker.from_model("cross-encoder/ms-marco-MiniLM-L-6-v2")
    s = r.score(
        "what is the capital of France", ["Paris is the capital of France.", "Bananas are yellow."]
    )
    assert s[0] > s[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rerank.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.rerank`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/rerank/__init__.py`: empty.

`python/triplum/rerank/protocol.py`:
```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

from triplum.cache import content_key


@dataclass(frozen=True)
class RerankSpec:
    model: str
    revision: str
    runtime: str = "api"

    def hash(self) -> str:
        return content_key("rerank_spec", asdict(self))[:16]


class Reranker(Protocol):
    spec: RerankSpec

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        """Higher is more relevant. Shape (len(passages),), float32."""
        ...
```

`python/triplum/rerank/fake.py`:
```python
from __future__ import annotations

import re

import numpy as np

from triplum.rerank.protocol import RerankSpec


class FakeReranker:
    spec = RerankSpec(model="fake", revision="1", runtime="fake")

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        q = set(re.findall(r"\w+", query.lower()))
        out = np.zeros(len(passages), dtype=np.float32)
        for i, p in enumerate(passages):
            toks = re.findall(r"\w+", p.lower())
            out[i] = sum(t in q for t in toks) / max(1, len(toks))
        return out
```

`python/triplum/rerank/cross_encoder.py`:
```python
from __future__ import annotations

import numpy as np

from triplum.embed.sentence_transformers import pick_device
from triplum.rerank.protocol import RerankSpec


class CrossEncoderReranker:
    def __init__(self, spec: RerankSpec, model, batch_size: int = 32) -> None:
        self.spec = spec
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_model(
        cls, name: str, *, device: str | None = None, batch_size: int = 32, max_length: int = 512
    ):
        from sentence_transformers import CrossEncoder

        device = device or pick_device()
        model = CrossEncoder(name, device=device, max_length=max_length)
        return cls(RerankSpec(model=name, revision="hf", runtime=device), model, batch_size)

    def score(self, query: str, passages: list[str]) -> np.ndarray:
        pairs = [(query, p) for p in passages]
        return np.asarray(
            self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False),
            dtype=np.float32,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rerank.py -v`
Expected: 3 passed (last one skipped if the extra is absent)

- [ ] **Step 5: Commit**

```bash
git add python/triplum/rerank tests/test_rerank.py
git commit -m "Add reranker protocol with fake and cross-encoder adapter"
```

---

### Task 9: SQLite store: migrations, documents, grants, chunks with viewer filtering

**Files:**
- Create: `python/triplum/store/__init__.py`, `python/triplum/store/protocol.py`, `python/triplum/store/sqlite/__init__.py`, `python/triplum/store/sqlite/migrations.sql`, `python/triplum/store/sqlite/acl.py`, `python/triplum/store/sqlite/store.py`
- Test: `tests/test_store_documents.py`

- [ ] **Step 1: Write the failing test**

`tests/test_store_documents.py`:
```python
import polars as pl
import pytest

from triplum.data.schema import now_us
from triplum.data.viewer import Viewer
from triplum.store.sqlite.acl import acl_hash, principal_token
from triplum.store.sqlite.store import SqliteStore


def _docs():
    t = now_us()
    docs = pl.DataFrame(
        {
            "id": ["d1", "d2"],
            "source": ["t", "t"],
            "uri": [None, None],
            "observed_at": [t, t],
            "metadata": [None, None],
        }
    )
    grants = pl.DataFrame(
        {
            "document_id": ["d1", "d1", "d2"],
            "principal": ["public", "alice", "alice"],
            "granted_at": [t, t, t],
            "revoked_at": [None, None, None],
        }
    )
    chunks = pl.DataFrame(
        {
            "id": [1, 2, 3],
            "document_id": ["d1", "d1", "d2"],
            "parent_id": [None, None, None],
            "level": [0, 0, 0],
            "span_start": [0, 10, 0],
            "span_end": [10, 20, 10],
            "text": ["public one", "public two", "alice secret"],
        }
    )
    return docs, grants, chunks


def test_acl_helpers():
    assert principal_token("alice@example.org") == principal_token("alice@example.org")
    assert principal_token("a") != principal_token("b")
    assert acl_hash({"b", "a"}) == acl_hash(["a", "b"]) and len(acl_hash({"a"})) == 16


def test_put_and_get_chunks_respects_viewer(tmp_db):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = _docs()
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    public = s.get_chunks([1, 2, 3], Viewer.of("public"))
    assert sorted(public["id"].to_list()) == [1, 2]
    alice = s.get_chunks([1, 2, 3], Viewer.of("alice"))
    assert sorted(alice["id"].to_list()) == [1, 2, 3]
    nobody = s.get_chunks([1, 2, 3], Viewer.of("carol"))
    assert nobody.height == 0


def test_revoked_grant_hides_document(tmp_db):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = _docs()
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    s.revoke("d2", "alice", at=now_us())
    assert s.get_chunks([3], Viewer.of("alice")).height == 0
    assert s.document_acl_hash("d2") == acl_hash([])


def test_put_documents_rejects_wrong_columns(tmp_db):
    s = SqliteStore(tmp_db)
    with pytest.raises(ValueError):
        s.put_documents(
            pl.DataFrame({"id": ["x"]}), pl.DataFrame({"document_id": [], "principal": []})
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store_documents.py -v`
Expected: FAIL with `ModuleNotFoundError: triplum.store`

- [ ] **Step 3: Write minimal implementation**

`python/triplum/store/__init__.py` and `python/triplum/store/sqlite/__init__.py`: empty.

`python/triplum/store/protocol.py`:
```python
"""The store protocol. Every read takes a Viewer; backends declare what they can filter exactly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import polars as pl

from triplum.data.viewer import Viewer
from triplum.embed.protocol import EmbeddingSpec


@dataclass(frozen=True)
class Capabilities:
    exact_acl_filter: bool
    vector_search_exact: bool  # brute force (exact) vs approximate
    bm25: bool


class Store(Protocol):
    def put_documents(self, docs: pl.DataFrame, grants: pl.DataFrame) -> None: ...
    def put_chunks(self, chunks: pl.DataFrame) -> None: ...
    def put_embeddings(
        self, spec: EmbeddingSpec, chunk_ids: list[int], vectors: np.ndarray
    ) -> None: ...
    def get_chunks(self, ids: list[int], viewer: Viewer) -> pl.DataFrame: ...
    def vector_search(
        self, spec: EmbeddingSpec, query: np.ndarray, k: int, viewer: Viewer
    ) -> pl.DataFrame: ...
    def bm25(self, query: str, k: int, viewer: Viewer) -> pl.DataFrame: ...
    def capabilities(self) -> Capabilities: ...
```

`python/triplum/store/sqlite/acl.py`:
```python
"""Principal tokens for FTS5 and principal-set hashes for vec0 partitions."""

from __future__ import annotations

import hashlib
from typing import Iterable


def principal_token(principal: str) -> str:
    """Alphanumeric token safe for the unicode61 tokenizer."""
    return "p" + hashlib.sha256(principal.encode()).hexdigest()[:20]


def acl_hash(principals: Iterable[str]) -> str:
    """Hash of the sorted active principal set of a document."""
    joined = "\0".join(sorted(set(principals)))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def acl_tokens(principals: Iterable[str]) -> str:
    return " ".join(principal_token(p) for p in sorted(set(principals)))
```

`python/triplum/store/sqlite/migrations.sql`:
```sql
-- triplum SQLite store, schema v1. Times are INTEGER microseconds UTC.
-- Open interval ends use the sentinel 9223372036854775807.
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;

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

-- Graph tables: created now (design D2), used from sub-project 2a on.
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
  confidence             REAL NOT NULL DEFAULT 1.0,
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
  confidence REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (chunk_id, span_start, entity_id)
) STRICT, WITHOUT ROWID;

INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1');
```

`python/triplum/store/sqlite/store.py`:
```python
"""SQLite store: documents, grants, chunks, FTS5 BM25, sqlite-vec vectors. Every read takes a Viewer.

Visibility at chunk level: a chunk is visible iff its document has a live grant to one of the
viewer's principals. Filtering happens inside FTS5 (acl_tokens column ANDed into MATCH) and inside
vec0 (partition key = document acl_hash), then an exact join re-checks against live grants.
"""

from __future__ import annotations

import json
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


def _require_cols(df: pl.DataFrame, cols: list[str], what: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{what} frame missing columns {missing}; have {df.columns}")


def _q(n: int) -> str:
    return ",".join("?" * n)


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
                "INSERT OR REPLACE INTO documents(id, source, uri, observed_at, metadata, acl_hash, acl_tokens) VALUES (?,?,?,?,?,?,?)",
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
                "INSERT OR REPLACE INTO document_grants(document_id, principal, granted_at, revoked_at) VALUES (?,?,?,?)",
                [
                    (r["document_id"], r["principal"], int(r["granted_at"]), r["revoked_at"])
                    for r in grants.iter_rows(named=True)
                ],
            )

    def revoke(self, document_id: str, principal: str, at: int) -> None:
        with self._tx():
            self.conn.execute(
                "UPDATE document_grants SET revoked_at = ? WHERE document_id = ? AND principal = ? AND revoked_at IS NULL",
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
        for (table,) in self.conn.execute("SELECT 'emb_' || spec_hash FROM embedding_specs"):
            ids = [
                r[0]
                for r in self.conn.execute(
                    "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
                )
            ]
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
                "INSERT OR REPLACE INTO chunks(id, document_id, parent_id, level, span_start, span_end, text, acl_tokens) VALUES (?,?,?,?,?,?,?,?)",
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
            f"EXISTS (SELECT 1 FROM document_grants g WHERE g.document_id = c.document_id "
            f"AND g.revoked_at IS NULL AND g.principal IN ({_q(len(ps))}))"
        )
        return sql, ps

    def get_chunks(self, ids: list[int], viewer: Viewer) -> pl.DataFrame:
        if not ids:
            return pl.DataFrame(
                schema={
                    c: pl.Int64 if c in ("id", "parent_id", "span_start", "span_end") else pl.Utf8
                    for c in CHUNK_COLS
                }
            )
        vis, params = self._visible_ids_sql(viewer)
        rows = self.conn.execute(
            f"SELECT c.id, c.document_id, c.parent_id, c.level, c.span_start, c.span_end, c.text FROM chunks c "
            f"WHERE c.id IN ({_q(len(ids))}) AND {vis}",
            [*ids, *params],
        ).fetchall()
        return pl.DataFrame(rows, schema=CHUNK_COLS, orient="row")

    def eligible_acl_hashes(self, viewer: Viewer) -> list[str]:
        ps = viewer.sorted_principals()
        return [
            r[0]
            for r in self.conn.execute(
                f"SELECT DISTINCT d.acl_hash FROM documents d WHERE EXISTS (SELECT 1 FROM document_grants g "
                f"WHERE g.document_id = d.id AND g.revoked_at IS NULL AND g.principal IN ({_q(len(ps))}))",
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store_documents.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/store tests/test_store_documents.py
git commit -m "Add SQLite store: migrations, documents, system-versioned grants, viewer-filtered chunks"
```

---

### Task 10: BM25 through FTS5 with the ACL column in the match

**Files:**
- Modify: `python/triplum/store/sqlite/store.py`
- Test: `tests/test_store_bm25.py`

- [ ] **Step 1: Write the failing test**

`tests/test_store_bm25.py`:
```python
from triplum.data.viewer import Viewer
from triplum.store.sqlite.store import SqliteStore, fts_query
from tests.test_store_documents import _docs


def test_fts_query_quotes_terms():
    assert fts_query('cat "dog" AND mat') == '"cat" "dog" "AND" "mat"'
    assert fts_query("") == '""'


def test_bm25_filters_by_viewer_inside_match(tmp_db):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = _docs()
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    pub = s.bm25("secret", k=10, viewer=Viewer.of("public"))
    assert pub.height == 0
    alice = s.bm25("secret", k=10, viewer=Viewer.of("alice"))
    assert alice["id"].to_list() == [3] and alice.columns == ["id", "score"]
    both = s.bm25("public", k=10, viewer=Viewer.of("public"))
    assert sorted(both["id"].to_list()) == [1, 2]


def test_bm25_after_revoke(tmp_db):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = _docs()
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    s.revoke("d2", "alice", at=1)
    assert s.bm25("secret", k=10, viewer=Viewer.of("alice")).height == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store_bm25.py -v`
Expected: FAIL with `ImportError: cannot import name 'fts_query'`

- [ ] **Step 3: Write minimal implementation**

Add to `python/triplum/store/sqlite/store.py` (module level, after `_q`):
```python
import re


def fts_query(text: str) -> str:
    """Quote every term so user text cannot inject FTS5 operators."""
    terms = re.findall(r"\w+", text)
    if not terms:
        return '""'
    return " ".join(f'"{t}"' for t in terms)
```

Add to the `SqliteStore` class:
```python
# ---- BM25 -------------------------------------------------------------------------------


def bm25(self, query: str, k: int, viewer: Viewer) -> pl.DataFrame:
    acl = " OR ".join(principal_token(p) for p in viewer.sorted_principals())
    match = f"({fts_query(query)}) AND acl_tokens:({acl})"
    vis, params = self._visible_ids_sql(viewer)
    rows = self.conn.execute(
        f"SELECT c.id, -bm25(chunks_fts, 1.0, 0.0) AS score FROM chunks_fts "
        f"JOIN chunks c ON c.id = chunks_fts.rowid "
        f"WHERE chunks_fts MATCH ? AND {vis} ORDER BY bm25(chunks_fts, 1.0, 0.0) LIMIT ?",
        [match, *params, k],
    ).fetchall()
    return pl.DataFrame(rows, schema={"id": pl.Int64, "score": pl.Float64}, orient="row")
```

The `acl_tokens` column weight is 0.0 in `bm25()` so principal tokens never influence ranking; the exact `EXISTS` re-check is belt and braces against a stale token column.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store_bm25.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add python/triplum/store/sqlite/store.py tests/test_store_bm25.py
git commit -m "Store: BM25 via FTS5 with the ACL token column inside the match"
```

---

### Task 11: Vector search through sqlite-vec partitioned by principal-set hash

**Files:**
- Modify: `python/triplum/store/sqlite/store.py`
- Test: `tests/test_store_vector.py`

- [ ] **Step 1: Write the failing test**

`tests/test_store_vector.py`:
```python
import numpy as np

from triplum.data.viewer import Viewer
from triplum.embed.fake import FakeEmbedder
from triplum.store.sqlite.store import SqliteStore
from tests.test_store_documents import _docs


def _load(tmp_db):
    s = SqliteStore(tmp_db)
    docs, grants, chunks = _docs()
    s.put_documents(docs, grants)
    s.put_chunks(chunks)
    e = FakeEmbedder(dims=32)
    vecs = e.embed_passages(chunks["text"].to_list())
    s.put_embeddings(e.spec, chunks["id"].to_list(), vecs)
    return s, e


def test_vector_search_respects_viewer(tmp_db):
    s, e = _load(tmp_db)
    q = e.embed_queries(["alice secret"])[0]
    pub = s.vector_search(e.spec, q, k=3, viewer=Viewer.of("public"))
    assert 3 not in pub["id"].to_list() and pub.height == 2
    alice = s.vector_search(e.spec, q, k=3, viewer=Viewer.of("alice"))
    assert alice["id"].to_list()[0] == 3 and alice.columns == ["id", "score"]


def test_put_embeddings_is_idempotent_and_records_spec(tmp_db):
    s, e = _load(tmp_db)
    s.put_embeddings(e.spec, [1], e.embed_passages(["public one"]))
    n = s.conn.execute(f"SELECT COUNT(*) FROM {e.spec.table_name()}").fetchone()[0]
    assert n == 3
    assert s.has_embeddings(e.spec, [1, 2, 3]) == [True, True, True]
    assert s.has_embeddings(e.spec, [99]) == [False]


def test_vector_search_after_revoke_moves_partition(tmp_db):
    s, e = _load(tmp_db)
    s.revoke("d2", "alice", at=1)
    q = e.embed_queries(["alice secret"])[0]
    assert 3 not in s.vector_search(e.spec, q, k=3, viewer=Viewer.of("alice"))["id"].to_list()


def test_no_embedding_leaves_store_for_hidden_rows(tmp_db):
    s, e = _load(tmp_db)
    q = e.embed_queries(["alice secret"])[0]
    out = s.vector_search(e.spec, q, k=3, viewer=Viewer.of("public"))
    assert "embedding" not in out.columns and "vector" not in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store_vector.py -v`
Expected: FAIL with `AttributeError: 'SqliteStore' object has no attribute 'put_embeddings'`

- [ ] **Step 3: Write minimal implementation**

Add to the `SqliteStore` class:
```python
# ---- embeddings and vector search --------------------------------------------------------


def _ensure_vec_table(self, spec: EmbeddingSpec) -> str:
    table = spec.table_name()
    self.conn.execute(
        "INSERT OR IGNORE INTO embedding_specs(spec_hash, spec_json, dims) VALUES (?,?,?)",
        (spec.hash(), json.dumps(spec.__dict__, sort_keys=True), spec.dims),
    )
    self.conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, acl_hash TEXT PARTITION KEY, "
        f"embedding float[{spec.dims}] distance_metric=cosine)"
    )
    return table


def put_embeddings(self, spec: EmbeddingSpec, chunk_ids: list[int], vectors: np.ndarray) -> None:
    if vectors.shape != (len(chunk_ids), spec.dims):
        raise ValueError(f"vectors shape {vectors.shape} != ({len(chunk_ids)}, {spec.dims})")
    table = self._ensure_vec_table(spec)
    hashes = dict(
        self.conn.execute(
            f"SELECT c.id, d.acl_hash FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id IN ({_q(len(chunk_ids))})",
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
            [(int(cid), hashes[int(cid)], vectors[j].tobytes()) for j, cid in enumerate(chunk_ids)],
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
                f"SELECT chunk_id, distance FROM {table} WHERE embedding MATCH ? AND k = ? AND acl_hash = ?",
                (q.tobytes(), k, h),
            ).fetchall()
        )
    cands.sort(key=lambda r: r[1])
    ids = [c[0] for c in cands[:k]]
    visible = set(self.get_chunks(ids, viewer)["id"].to_list())
    rows = [(cid, 1.0 - dist) for cid, dist in cands[:k] if cid in visible]
    return pl.DataFrame(rows, schema={"id": pl.Int64, "score": pl.Float64}, orient="row")
```

Partition-key equality is what vec0 supports natively; one query per eligible principal-set hash keeps every scan pre-filtered, and the number of distinct sets is small in practice (design D4 open question: measure it). Score is cosine similarity.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store_vector.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the whole suite and lint**

Run: `uv run pytest -q && uv run ruff check python tests && cargo test -p triplum-core`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add python/triplum/store/sqlite/store.py tests/test_store_vector.py
git commit -m "Store: vector search via sqlite-vec partitioned by principal-set hash with exact re-check"
```

---

## Self-review

**Spec coverage (part 1 items 1 to 6 of the scope list):** scaffold (Task 1), data layer schemas and Viewer (Tasks 1, 2), SQLite chunk side with FTS5 ACL column and vec0 per spec partitioned by principal-set hash, `vector_search`, `bm25`, `get_chunks` all taking a `Viewer` (Tasks 9 to 11), `LLM` protocol with OpenAI-compatible and CLI adapters and cache (Tasks 3 to 5), `Embedder` with spec and three adapters (Tasks 6, 7), `Reranker` (Task 8). Not in this plan, by design: datasets, pipelines, metrics, run store, CLI, notebook (part 2). `Capabilities` is defined but only reported; part 2 consumes it.

**Placeholders:** none.

**Type consistency:** `EmbeddingSpec.hash()` and `.table_name()` are used identically in Tasks 6, 9 and 11; `Viewer.sorted_principals()` from Task 2 is used in Tasks 9 to 11; `principal_token`/`acl_hash`/`acl_tokens` from Task 9 are used in Task 10; `Completion`/`Usage`/`request_hash` from Task 4 are used in Task 5. `get_chunks` returns the `CHUNK_COLS` frame that `vector_search` reads `id` from.
