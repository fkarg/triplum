# Fingerprints

A **fingerprint** is a string that identifies *content*: equal content gives an equal fingerprint,
and changed content gives a different one. Fingerprints are what cache keys are built from, and
they let you recognise the same text or the same configured step across runs and machines.

triplum has three kinds. They answer different questions and are computed differently:

| Kind | Written as | Identifies | Used for |
| --- | --- | --- | --- |
| Record fingerprint | `source.fingerprint` (a property) | the content of one `Source` or `Chunk` | finding duplicate records, keying work done on one record |
| Object fingerprint | `step.fingerprint()` (a method) | a configured step: its code and its settings | keying work done *by* a step |
| Dataset fingerprint | `dataset.fingerprint()` (a method) | the ordered content of a whole dataset | keying work done on a whole dataset |

All three are 64-character hexadecimal SHA-256 digests, produced by
[`content_key`][triplum.utils.cache.content_key] (see [Cache](cache.md)).

## Example

```python
from pathlib import Path

from triplum.datatype import Source
from triplum.steps.chunking import FixedSize
from triplum.utils.data import RecordDataset

a = Source(origin=Path("notes/returns.md"), text="Returns are accepted within 30 days.")
b = Source(origin=Path("notes/returns.md"), text="Returns are accepted within 30 days.")
print(a.id == b.id, a.fingerprint == b.fingerprint)

print(FixedSize(20).fingerprint() == FixedSize(20).fingerprint())
print(FixedSize(20).fingerprint() == FixedSize(30).fingerprint())
```

Output:

```text
False True
True
False
```

1. `a` and `b` have the same content, but each got its own random `id` when it was created. The
   ids differ; the record fingerprints are equal.
2. Two `FixedSize(20)` chunkers have the same code and the same setting, so their object
   fingerprints are equal. Changing the setting to `30` changes the fingerprint.

## Record fingerprints

`Source.fingerprint` and `Chunk.fingerprint` are properties computed from the record's content
each time you read them:

- a source's fingerprint covers `origin` and `text`;
- a chunk's fingerprint covers `origin`, `start` and `text`.

Neither covers `id`, and a chunk's does not cover `source_id`. The `id` says *which stored record*
this is; the fingerprint says *what it contains*. The fingerprint is included when a record is
serialised (`model_dump()`), and
[`SQLAlchemyStore`][triplum.store.sql.generic.SQLAlchemyStore] stores it in an indexed column so
records with equal content can be found.

## Object fingerprints

Steps such as [`FixedSize`][triplum.steps.chunking.FixedSize] and
[`ZeroEmbedder`][triplum.steps.embedding.ZeroEmbedder] get a `fingerprint()` method by mixing in
[`Fingerprinted`][triplum.utils.fingerprint.Fingerprinted]. You can do the same for your own
steps:

```python
from triplum.datatype import Chunk, Source
from triplum.steps.chunking import Chunker
from triplum.utils.fingerprint import Fingerprinted


class Paragraphs(Chunker, Fingerprinted):
    """Split on blank lines."""

    def __init__(self, separator: str = "\n\n") -> None:
        self.separator = separator

    def __call__(self, source: Source, /) -> list[Chunk]:
        chunks, start = [], 0
        for part in source.text.split(self.separator):
            chunks.append(Chunk(source_id=source.id, origin=source.origin, start=start, text=part))
            start += len(part) + len(self.separator)
        return chunks


print(Paragraphs().fingerprint()[:16])
print(Paragraphs().fingerprint() == Paragraphs("\n").fingerprint())
```

Output:

```text
70cd0f8326da1984
False
```

The fingerprint hashes three things:

1. **The class name**, including its module (`__main__.Paragraphs` when run as a script, so the
   same class imported from a module fingerprints differently).
2. **The source code of the class and of each base class** it inherits from, here `Paragraphs`
   and `Chunker`. Docstrings, comments and formatting are ignored; any other code change,
   including a renamed variable, changes the fingerprint.
3. **Every instance attribute**, here `separator`. Attributes are normally the settings passed to
   `__init__`.

What it cannot see, and what you must handle yourself:

- **Code the class calls.** Helper functions, other modules and installed libraries are not
  hashed. If `__call__` delegates to a function in another file, or the result depends on a
  library version or a model's weights, override `fingerprint()` and add that information.
- **Attributes that are not plain data.** Allowed are `str`, `int`, `float`, `bool`, `None`,
  `Path`, lists, tuples and dicts of those, Pydantic models, and objects that have their own
  `fingerprint()` method. Anything else, such as a network client, raises `TypeError` instead of
  being silently left out:

  ```text
  cannot fingerprint attribute of type object; use plain data, a pydantic model, or an object with fingerprint()
  ```

  Keep such resources out of the fingerprint by overriding `fingerprint()`, or wrap them in an
  object with its own `fingerprint()` that names what matters (for example a model id).
- **Classes without a source file.** A class whose source Python cannot find, for example one
  created with `exec` or in a script piped to `python -`, raises `TypeError` with
  `cannot fingerprint ...: its source is unavailable`. Define fingerprinted classes in `.py`
  files. Other interactive environments (REPL, notebooks) are not tested.

## Dataset fingerprints

Every [dataset](../concepts/datasets.md) must implement `fingerprint()`. Equal fingerprints
promise the same records in the same order. Each dataset decides how to compute it; for example
[`MarkdownFolder`][triplum.datasets.markdownfolder.MarkdownFolder] hashes each file's name and bytes,
so editing a file changes the fingerprint, while re-reading an unchanged folder does not.

A dataset fingerprint describes content, not stored records. A dataset that builds `Source`
records on access, such as `MarkdownFolder`, gives them a fresh `id` each time; use the record
fingerprint, not the `id`, to match them across runs.

## Reference

- [`Fingerprinted`][triplum.utils.fingerprint.Fingerprinted] and
  [`source_hash`][triplum.utils.fingerprint.source_hash]
- [`Source`][triplum.datatype.source.Source] and [`Chunk`][triplum.datatype.chunk.Chunk]
- [`Dataset`][triplum.utils.data.dataset.Dataset]

Next: [Cache](cache.md).
