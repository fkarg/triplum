# Chunking

**Chunking** splits a [source](source.md) into [chunks](chunk.md): the pieces that will be
indexed and retrieved. Choosing the pieces is a retrieval decision. Keeping the whole text as one
chunk is valid; so are fixed-size pieces, overlapping pieces, or pieces that follow sections.

The library provides one naive chunker, `FixedSize`, which cuts the text every `n` characters.

## Example

```python
from triplum.datatype import Source
from triplum.steps.chunking import FixedSize

source = Source(
    origin="notes/returns.md",
    text="Returns are accepted within 30 days. Refunds take 5 days.",
)
chunker = FixedSize(20)
for chunk in chunker(source):
    print(chunk.start, repr(chunk.text))
    assert source.text[chunk.start : chunk.start + len(chunk.text)] == chunk.text
# 0 'Returns are accepted'
# 20 ' within 30 days. Ref'
# 40 'unds take 5 days.'
```

1. `FixedSize(20)` configures the chunker: the size is set once, in `__init__`, not per call. A
   size below 1 raises `ValueError`.
2. Calling it with one source returns a list of chunks. The last chunk keeps the remainder.
3. Every chunk has the source's `origin`, and its `start` and `text` are an exact slice of the
   source text, which is what the assertion checks.

`FixedSize` ignores words, sentences and structure, which is why it is only a baseline.

## The contract

`Chunker` is a `typing.Protocol`:

```python
class Chunker(Protocol):
    @abstractmethod
    def __call__(self, source: Source, /) -> list[Chunk]: ...
```

- Input: one `Source`.
- Output: zero or more `Chunk`s with the source's `origin`, each satisfying
  `source.text[chunk.start : chunk.start + len(chunk.text)] == chunk.text`. Chunk text is never
  rewritten.
- `FixedSize` additionally guarantees that its chunks do not overlap, concatenate back to the
  source text, and that an empty source produces no chunks. Other chunkers may overlap or skip
  text.

## Writing your own

Subclass the protocol and implement `__call__`. This chunker makes one chunk per paragraph:

```python
import re

from triplum.datatype import Chunk, Source
from triplum.steps.chunking import Chunker


class Paragraphs(Chunker):
    """One chunk per paragraph; blank lines separate paragraphs."""

    def __call__(self, source: Source, /) -> list[Chunk]:
        return [
            Chunk(
                source_id=source.id,
                origin=source.origin,
                start=match.start(),
                text=match.group(),
            )
            for match in re.finditer(r"[^\n]+(?:\n[^\n]+)*", source.text)
        ]


source = Source(origin="notes/policy.md", text="Returns: 30 days.\n\nRefunds: 5 days.")
for chunk in Paragraphs()(source):
    print(chunk.start, repr(chunk.text))
# 0 'Returns: 30 days.'
# 19 'Refunds: 5 days.'
```

Taking `start` from the match keeps each chunk an exact slice. `Chunker` only asks for a call, so
a plain function with the same signature fits it as well, without subclassing (continuing the
example above):

```python
def whole_text(source: Source, /) -> list[Chunk]:
    if not source.text:
        return []
    return [Chunk(source_id=source.id, origin=source.origin, start=0, text=source.text)]


chunker: Chunker = whole_text  # accepted by the type checker
```

## Open questions

Hierarchical chunking (sections containing passages) and how containment is represented are still
open.

## Reference

- [`Chunker`][triplum.steps.chunking.Chunker]
- [`FixedSize`][triplum.steps.chunking.FixedSize]

Next: [Chunk preprocessing](chunk-preprocessing.md).
