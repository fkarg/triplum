# triplum

A composable, benchmark-first Python library for document search, knowledge graphs and GraphRAG.
Experiments combine importable modules; the library is the product. Bi-temporal evidence and
provenance-derived permissions remain design requirements; evidence must respect source access.

## Current state

The rebuild continues on `main`, one owner-reviewed interface at a time. Historical code is
reference material, not the current architecture contract. The old CLI and benchmark runner are
not working entry points.

The Python foundation includes datasets/loaders, Source and Chunk records, step Protocols,
memory/SQL record stores, and optional computation caching. Indexing prototypes remain under
review; there is no supported end-to-end retrieval pipeline. The pure Python package uses
`uv_build`; the independent Rust workspace is not built or linked during Python installation.

## Try it

From a checkout, install with [uv](https://docs.astral.sh/uv/). Python 3.14 or newer is required;
Rust is not needed for these Python examples.

```sh
git clone https://github.com/fkarg/triplum.git
cd triplum
uv sync
```

Create a source and split its text into chunks:

```sh
uv run python - <<'PYTHON'
from triplum.datatype import Source
from triplum.steps.chunking import FixedSize

source = Source(origin="example", text="Alpha. Beta.")
for chunk in FixedSize(7)(source):
    print(chunk.start, repr(chunk.text))
PYTHON
```

```text
0 'Alpha. '
7 'Beta.'
```

Each chunk retains its source reference and character offset. `FixedSize` is deliberately naive;
replace it with another chunker as the experiment needs. Continue with
[chunking](docs/concepts/chunking.md) or the [step-by-step concepts](docs/concepts.md).

For a two-step example demonstrating cached intermediate results, run:

```sh
uv run python examples/cached_pipeline.py
```

It demonstrates reuse across equivalent inputs, different upstream computations and a reopened
SQLite cache. The cache implementation is authorized for owner review; Source/Chunk identity
changes remain under review. See the [cache guide](docs/infrastructure/cache.md) for usage
and default Pydantic serialization.

## Where next?

- [Indexing and retrieval](docs/flow.md): what exists and how the intended pipeline fits together.
- [Decision points](docs/concepts/decisions.md): replaceable steps and their contracts.
- [Store](docs/infrastructure/store.md): retain sources and chunks in memory or SQL.
- [CONTRIBUTING.md](CONTRIBUTING.md): checks and hook setup; [AGENTS.md](AGENTS.md): contributor
  rules and the interface review gate.

Preview the documentation with `uv run mkdocs serve`; verify it with `uv run mkdocs build --strict`.
Use check and CI output for current verification results.

## License

[Apache-2.0](LICENSE). Record third-party terms in [dependency licences](docs/licences.md)
when introducing or restoring a dependency.
