# Embedding

**Embedding** turns the text prepared for each chunk into a vector, so that chunks can be found by
similarity to a query's vector. An embedder works on a batch of texts at once, because real
models are much faster that way.

The library provides only a placeholder, `ZeroEmbedder`, which returns zero vectors. It fixes
the shape of the step; it does not embed anything meaningful.

## Example

```python
from triplum.steps.embedding import ZeroEmbedder

embed = ZeroEmbedder(dimensions=4)
vectors = embed(["Returns are accepted within 30 days.", "Refunds take 5 days."])
print(vectors.shape, vectors.dtype)  # (2, 4) float32
print(vectors[0])  # [0. 0. 0. 0.]
```

1. The vector size is configured in `__init__` and exposed as `embed.dimensions` (default 1536).
   A real embedder would load its model or create its client here, once.
2. Calling it with a list of texts returns one matrix: row `i` is the vector of text `i`.
3. The result is a numpy `float32` array of shape `(len(texts), dimensions)`. The type alias
   `Vectors` names that shape.

## The contract

`Embedder` is a `typing.Protocol`:

```python
type Vectors = NDArray[np.float32]  # shape (len(texts), dimensions)


class Embedder(Protocol):
    dimensions: int

    @abstractmethod
    def __call__(self, texts: list[str], /) -> Vectors: ...
```

- Input: one batch of texts, usually produced by [chunk preprocessing](chunk-preprocessing.md).
  Forming batches (for example with a [`DataLoader`](datasets.md)) is the pipeline's job.
- Output: a `float32` matrix with one row per text, in input order, each row `dimensions` long.
- `dimensions` is an attribute, so the vector size is known without embedding anything.

Benchmarks hold the embedding configuration fixed across the pipelines they compare, so that
differences in results come from the pipelines, not the embedder. Encoding a user's question at
retrieval time is a separate use of the same model and is not part of indexing.

## Writing your own

Subclass the protocol, set `dimensions` and implement `__call__`. This toy embedder counts
letters:

```python
import numpy as np

from triplum.steps.embedding import Embedder, Vectors


class LetterCounts(Embedder):
    """Count the letters a-z in each text; a toy embedder with 26 dimensions."""

    dimensions = 26

    def __call__(self, texts: list[str], /) -> Vectors:
        vectors = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for char in text.lower():
                if "a" <= char <= "z":
                    vectors[row, ord(char) - ord("a")] += 1
        return vectors


vectors = LetterCounts()(["abba", "Cab"])
print(vectors.shape, vectors.dtype)  # (2, 26) float32
print(vectors[:, :3])
# [[2. 2. 0.]
#  [1. 1. 1.]]
```

Unlike the other steps, a plain function does not fit `Embedder`: the protocol also requires the
`dimensions` attribute, so the type checker rejects a bare function.

## Open questions

How an embedder identifies itself (model, revision, settings) so that its vectors can be cached
and recorded in a run's identity is not decided yet.

## Reference

- [`Embedder`][triplum.steps.embedding.Embedder] and
  [`Vectors`][triplum.steps.embedding.Vectors]
- [`ZeroEmbedder`][triplum.steps.embedding.ZeroEmbedder]

Next: [Decision points](decisions.md), every place you choose an implementation.
