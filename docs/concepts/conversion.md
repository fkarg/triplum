# Conversion

**Conversion** turns one dataset item into [sources](source.md). A dataset may yield file paths,
raw bytes, HTML pages or scanned images; chunking only understands `Source`. A converter is the
step in between: reading and decoding a file, extracting text from HTML, or running OCR.

The library provides one naive converter, `Utf8File`, which reads a file as text.

## Example

```python
from pathlib import Path

from triplum.steps.conversion import Utf8File

path = Path("returns.md")
path.write_text("# Returns\nReturns are accepted within 30 days.\n", encoding="utf-8")

convert = Utf8File()
sources = convert(path)
print(len(sources))  # 1
print(sources[0].origin, repr(sources[0].text))
# returns.md '# Returns\nReturns are accepted within 30 days.\n'
```

1. Create the converter once. Converters that need configuration or resources (an OCR model, an
   HTTP client) take them in `__init__`; `Utf8File` needs none.
2. Call it with one item, here a `Path`. It returns a **list** of sources, because one item may
   hold several documents (an archive, a JSON Lines file). `Utf8File` always returns one.
3. The source's `origin` is the path as given, and `text` is the file decoded as UTF-8 with its
   newlines unchanged. Invalid UTF-8 raises an error.

## The contract

`Converter[A]` is a `typing.Protocol` for converting items of type `A`:

```python
class Converter[A](Protocol):
    @abstractmethod
    def __call__(self, item: A, /) -> list[Source]: ...
```

- Input: one item, of whatever type the dataset yields. `Utf8File` is a `Converter[Path]`.
- Output: zero or more `Source`s. Each `origin` should identify where its text came from, and be
  unique within what you index together.
- A converter handles one item. Mapping it over a dataset or [`DataLoader`](datasets.md) is the
  pipeline's job, and the loader never converts.

Datasets whose items are already sources skip this step. The [MultiHop-RAG corpus](datasets.md)
is one.

## Writing your own

Subclass the protocol and implement `__call__`. This converter turns one JSON Lines file into
several sources:

```python
import json
from pathlib import Path

from triplum.datatype import Source
from triplum.steps.conversion import Converter


class JsonLines(Converter[Path]):
    """One source per line of a JSON Lines file with `id` and `text` fields."""

    def __call__(self, item: Path, /) -> list[Source]:
        records = [json.loads(line) for line in item.read_text("utf-8").splitlines() if line]
        return [Source(origin=f"{item}#{r['id']}", text=r["text"]) for r in records]


path = Path("faq.jsonl")
path.write_text('{"id": "returns", "text": "30 days."}\n{"id": "refunds", "text": "5 days."}\n')
for source in JsonLines()(path):
    print(source.origin, source.text)
# faq.jsonl#returns 30 days.
# faq.jsonl#refunds 5 days.
```

Subclassing is how triplum's own implementations are written: the type checker verifies the
signature where the class is defined, and a subclass that forgets `__call__` cannot be
instantiated. Code that does not inherit from `Converter` still fits wherever a converter is
expected, as long as its call signature matches; a plain function works too. See
[Decision points](decisions.md) for how this applies to every step.

## Reference

- [`Converter`][triplum.steps.conversion.Converter]
- [`Utf8File`][triplum.steps.conversion.Utf8File]

Next: [Chunking](chunking.md).
