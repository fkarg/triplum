# Loading batches

`DataLoader` reads a source when you iterate it. `batch_size` sets the number of records in each
list; the last list can be smaller.

```python
from triplum.utils.data import DataLoader

loader = DataLoader(["a", "b", "c"], batch_size=2)
assert list(loader) == [["a", "b"], ["c"]]
assert list(loader) == [["a", "b"], ["c"]]
```

Each pass asks the source for a new iterator. The list above repeats, while an exhausted
generator does not. Use a repeatable source for benchmarks. `collate_fn` can convert each list
to a [corpus batch](frames.md).
