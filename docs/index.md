# triplum

A Python library being rebuilt for composable document search, knowledge graphs and GraphRAG
experiments. Combine small functions and classes to compare pipelines and their baselines.

## Try the building blocks

From a repository checkout, run `uv sync` to install (Python 3.14+), then `uv run python` to
try this example:

```python
from triplum.datatype import Source
from triplum.steps.chunking import FixedSize

source = Source(origin="example", text="Alpha. Beta.")
for chunk in FixedSize(7)(source):
    print(chunk.start, repr(chunk.text))
```

```text
0 'Alpha. '
7 'Beta.'
```

Each chunk retains its source reference and character offset. Follow
[chunking](concepts/chunking.md) to replace this naive splitter, or [Core concepts](concepts.md)
for the full sequence of building blocks. For intermediate-result reuse, see the
[cache guide](infrastructure/cache.md).

## Project status

[Indexing and retrieval](flow.md) distinguishes implemented foundations from the intended flow.
Indexing prototypes remain under review; there is no supported end-to-end retrieval pipeline.
The Python package and Rust workspace are independent, so the example requires no Rust build.
