# Sources

A source supplies records to an experiment. Use `RecordDataset` when the records are already in
memory. It calculates its fingerprint from their content.

```python
from triplum.data.corpus import Document
from triplum.utils.data import RecordDataset

source = RecordDataset([Document(id="note-1", source="notes", text="Alice met Bob.")])
assert source[0].text == "Alice met Bob."
assert source.fingerprint()
```

For another source, implement `Dataset` for indexed access or `IterableDataset` for streaming.
Both require `fingerprint()` so the benchmark can identify the ordered records without loading
them. The [dataset guide](../datasets.md) shows built-in and custom sources.

Next: [load records in batches](loading.md).
