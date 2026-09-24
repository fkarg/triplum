# Sources

A source supplies records to an experiment. For records already in memory, wrap them in
`RecordDataset`:

```python
from triplum.data.corpus import Document
from triplum.utils.data import RecordDataset

source = RecordDataset([Document(id="note-1", source="notes", text="Alice met Bob.")])
assert source[0].text == "Alice met Bob."
assert list(source) == list(source)
assert source.fingerprint() == source.fingerprint()
```

`fingerprint()` identifies the ordered records. A benchmark may load the same source more than
once, so every pass must yield the same records in the same order for that fingerprint. If you
want a different corpus, give that variant its own fingerprint.

For a custom source, implement `Dataset` for indexed records or `IterableDataset` for streamed
records. See [built-in sources](../datasets.md) for more examples.

Next: [load records in batches](loading.md).
