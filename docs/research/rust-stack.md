# Rust and Python stack (September 2026)

Building blocks we intend to use, with status as of 2026-09-16. Versions were verified against
crates.io, PyPI and the repositories that day; see [`fact-check-2026-09-16.md`](fact-check-2026-09-16.md)
for the log. Re-check before pinning.

## Data layer and bindings

- **Arrow**: `arrow-rs` in Rust, `pyarrow` and **Polars** in Python. The Arrow C data interface is
  the zero-copy path across PyO3. Polars is itself a Rust core with Python bindings, and its
  repository layout is the template we copy: Cargo workspace under `crates/`, `[workspace.package]`
  metadata, feature-flagged umbrella crate, separate thin bindings crate, Python package name equal
  to import name, maturin build, pytest plus cargo test / clippy / miri.
- **PyO3** 0.29.2 (2026-08-05): free-threaded Python is opt-out rather than opt-in since 0.28.0
  (2026-02-01); 3.13t dropped in 0.29, 3.14t+ supported. **maturin** 1.15.0 (2026-08-24): mixed layout with `python/<pkg>/` plus `src/lib.rs`,
  `[tool.maturin] python-source = "python"`, `module-name = "<pkg>._core"`. With uv, either
  `maturin develop --uv` or let `uv run` rebuild via
  `[tool.uv] cache-keys = [{file="pyproject.toml"},{file="Cargo.toml"},{file="**/*.rs"}]`
  (maturin issue #2314). Wheel matrix: abi3 at minimum supported Python, plus free-threaded variants.

## Storage

- **SQLite** (backend one): FTS5, [sqlite-vec](https://github.com/asg017/sqlite-vec) (pre-v1,
  "expect breaking changes", Rust and Python bindings, metadata/partition-key filtering; verified
  2026-09-16), `rusqlite`, stdlib `sqlite3` (extension loading needs a Python built with
  `enable_load_extension`; see [`storage-sqlite.md`](storage-sqlite.md)). sqlite-vec stable is
  0.1.9 (2026-03-31); ANN (DiskANN) exists only in the 0.1.10 alphas. `rusqlite` 0.40.2. Arrow
  interop in Python via `adbc-driver-sqlite` 1.12.0 (reference implementation, type inference on
  first batch, no optimisation work). **There is no Rust ADBC SQLite crate** (only `adbc_core`,
  `adbc_ffi`, `adbc_driver_manager`); on the Rust side use `rusqlite` plus an Arrow builder or
  `connector_arrow`.
- **Oxigraph** 0.5.11 (2026-09-02, MIT OR Apache-2.0; `pyoxigraph` same version) (RDF arm): SPARQL
  1.1 with 1.2 / RDF 1.2 behind a feature flag, RocksDB, split crates
  `oxrdf`, `oxrdfio` (which wraps `oxttl`, `oxrdfxml`), `spargebra`, `spareval`, `sparopt`,
  `sparesults`. **Rio is unmaintained** (repo archived, crate description says "use oxttl"); use
  `oxrdfio` 0.2.6. **Sophia** 0.10 (RDF 1.2, JSON-LD 1.1, RDFS reasoner) is the generic-trait
  alternative if we need one.
- **LadybugDB** (property-graph arm): Kùzu was archived on 2025-10-10 ("Kuzu is working on
  something new"), the company reportedly acquired by Apple (disclosed Feb 2026; not re-verified).
  LadybugDB is the continuation ("formerly known as Kuzu", LICENSE carries both copyrights): C++,
  MIT, v0.20.4 (2026-09-10), Rust crate `lbug` 0.20.4 via cxx (builds C++ from source), Python
  package **`ladybug`** (not `lbug`); aims at Arrow/Parquet/DuckDB interop. Caveat: Kùzu's on-disk
  format was never stable. Graphiti has deprecated its Kùzu backend for the same reason.
- **DuckDB** 1.5.5 (2026-07-22) (optional analytical arm): columnar, Arrow zero-copy, core `fts`
  and `vss` extensions (`vss` is officially experimental; persistent HNSW needs an experimental flag
  and is not recommended for production), and the `sqlite` extension to attach backend one's file
  directly. [DuckPGQ](https://duckdb.org/community_extensions/extensions/duckpgq) (CWI research
  project, 0.3.1) has **no build for DuckDB 1.5.5**; newest supported is 1.5.4 and the docs still
  recommend 1.4.4. Pin accordingly if we use it.
- **LanceDB** Rust 0.38 *(unverified)*: Lance format is now native on the Hugging Face Hub. Candidate
  for embedding persistence if sqlite-vec does not scale; note the `lzma-sys` dynamic-link gotcha.

## Indexes and kernels

- **tantivy** 0.26.2 (2026-09-08; `tantivy-py` 0.26.2 on GitHub, PyPI still 0.26.0), **usearch**
  2.26.2 (HNSW with in-traversal predicate filtering, which matters for permission filters),
  **hnsw_rs** (filtered search, mmap).
- **petgraph**: pin 0.8.3 (2025-09-30, no release since); trunk is a multi-crate rewrite toward
  0.9, which is not released (roadmap issue #891).
- **fastembed-rs** 7.0.1 (released 2026-09-16; text, sparse, image, BGE-M3, rerankers) on `ort`
  2.0.0-rc.13 (no stable 2.0 yet; wraps ONNX Runtime 1.28) with optional `candle`. `ort` for
  throughput and execution providers, `candle` for pure-Rust and any HF model; `ort-candle` bridges.

## LLM clients (Rust, only if the Rust side ever calls models)

`async-openai` 0.42.0 (full OpenAI-compatible fidelity), `genai` 0.6.5 stable / 0.7.0-beta
(multi-provider, native protocols, explicitly incomplete), `rig-core` 0.42.0 (split into contracts
plus `rig-agent`; 20+ providers), `llm` 1.3.8 (graniet; least active). Our own `LLM` trait, backed by
`genai` and `async-openai`, is the recommendation if needed. CLI harnesses are subprocess adapters
either way.

## Validation

- **pyshacl** 0.40 (July 2026, now with an Oxigraph backend; version not re-verified).
- [**rudof**](https://github.com/rudof-project/rudof) 0.3.21 (2026-09-13, MIT OR Apache-2.0): Rust,
  SHACL and ShEx, native and SPARQL engines, Python bindings as **`pyrudof`** (the bare `rudof` on
  PyPI and crates.io is a stale 2024 release), MCP export. Preferred if we want validation on the
  Rust side.

## Notebooks

- **marimo** 0.24.2 (2026-09-11, Apache-2.0): notebooks are plain `.py`, reactive DAG, `marimo pair`
  agent mode; CVE-2026-39987 was fixed in 0.23.0. Python-only.
- **Jupyter**: ecosystem and non-Python kernels. Our package works in both.
- **evcxr** (`evcxr_jupyter` 0.22.0, 2026-08-18): the only maintained Rust kernel; needs Jupyter,
  cranelift backend, no kernel interrupt.
  Rust exploration stays in cargo examples and tests.

## Sources

<https://github.com/pola-rs/polars>, <https://www.maturin.rs/project_layout.html>,
<https://github.com/PyO3/maturin/issues/2314>, <https://pyo3.rs/main/free-threading.html>,
<https://github.com/asg017/sqlite-vec>, <https://arrow.apache.org/adbc/current/driver/sqlite.html>,
<https://github.com/oxigraph/oxigraph>, <https://github.com/oxigraph/rio>, <https://docs.rs/sophia>,
<https://github.com/kuzudb/kuzu>, <https://thedataquarry.com/blog/from-kuzu-to-ladybug/>,
<https://github.com/LadybugDB/ladybug>, <https://crates.io/crates/lbug>,
<https://duckdb.org/community_extensions/extensions/duckpgq>, <https://docs.rs/crate/lancedb/latest>,
<https://github.com/petgraph/petgraph/issues/891>, <https://github.com/quickwit-oss/tantivy/releases>,
<https://docs.rs/usearch/latest/usearch/>, <https://docs.rs/hnsw_rs>,
<https://github.com/Anush008/fastembed-rs/releases>, <https://lib.rs/crates/ort-candle>,
<https://github.com/64bit/async-openai>, <https://github.com/jeremychone/rust-genai>,
<https://crates.io/crates/rig-core>, <https://github.com/graniet/llm>,
<https://github.com/RDFLib/pySHACL/releases>, <https://github.com/rudof-project/rudof>,
<https://github.com/marimo-team/marimo/releases>, <https://github.com/evcxr/evcxr>.
