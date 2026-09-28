# Chunk preprocessing

**Chunk preprocessing** decides what text represents a [chunk](chunk.md) when it is embedded.
The simplest choice is the chunk text unchanged. Richer choices add a generated description,
questions the chunk answers, or context from its source.

The library provides one naive choice, `OriginalText`, which uses the chunk text unchanged.

## Example

```python
from triplum.datatype import Source
from triplum.steps.chunk_preprocessing import OriginalText
from triplum.steps.chunking import FixedSize

source = Source(origin="notes/returns.md", text="Returns are accepted within 30 days.")
[chunk] = FixedSize(100)(source)
embedding_text = OriginalText()
print(embedding_text(chunk))  # Returns are accepted within 30 days.
```

1. Create the step once. A step that generates text would take its model or client in `__init__`.
2. Call it with one chunk. It returns the string that [embedding](embedding.md) will encode.
3. The chunk itself is unchanged: its `text` stays verbatim evidence.

## The contract

`EmbeddingText` is a `typing.Protocol`:

```python
class EmbeddingText(Protocol):
    @abstractmethod
    def __call__(self, chunk: Chunk, /) -> str: ...
```

- Input: one `Chunk`.
- Output: one string, the text to embed for that chunk.
- It must not modify the chunk. A chunk gets **one vector per embedding configuration**, so a
  step that uses several representations must combine them into this one string; they are not
  indexed as separate vectors.

## Writing your own

Subclass the protocol and implement `__call__`. This one adds the source's origin as context
(continuing the example above):

```python
from triplum.datatype import Chunk
from triplum.steps.chunk_preprocessing import EmbeddingText


class WithOrigin(EmbeddingText):
    """Prefix the chunk text with the origin of its source."""

    def __call__(self, chunk: Chunk, /) -> str:
        return f"{chunk.origin}\n{chunk.text}"


print(WithOrigin()(chunk))
# notes/returns.md
# Returns are accepted within 30 days.
```

A plain function `(chunk) -> str` also fits the protocol without subclassing.

## Open questions

- How several representations combine into the one embedding input is undecided:

  ```text
  Original:    Returns are accepted within 30 days of purchase.
  Description: This shop's returns policy.
  Question:    How long do I have to return a purchase?
                           ↓ preparation and embedding
                      One chunk vector
  ```

- Generated text (descriptions, questions) must stay distinguishable from the original evidence.
  Which record holds it is still open.
- Operations that filter or adjust chunks (chunk to chunk) have no contract yet.

## Reference

- [`EmbeddingText`][triplum.steps.chunk_preprocessing.EmbeddingText]
- [`OriginalText`][triplum.steps.chunk_preprocessing.OriginalText]

Next: [Embedding](embedding.md).
