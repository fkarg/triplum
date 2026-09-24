# Loading batches

`DataLoader` groups source records as you iterate. It accepts any iterable; `batch_size` says
how many records to put in each list.

```python
from triplum.utils.data import DataLoader

loader = DataLoader(["a", "b", "c"], batch_size=2)
assert list(loader) == [["a", "b"], ["c"]]
assert list(loader) == [["a", "b"], ["c"]]
```

Each pass asks the source for a new iterator. A list can be read again; an exhausted generator
cannot. Use `collate_fn` to turn each list into another batch type, such as a
[`CorpusBatch`](frames.md).
