# Viewers

Every store read takes a `Viewer`. Its principals name the grants the caller holds. A public
read uses `Viewer.of("public")`:

```python
from triplum.data.viewer import Viewer

viewer = Viewer.of("public")
assert viewer.principals == frozenset({"public"})
```

You can set `as_of_valid` for world time and `as_of_recorded` for what the store knew then. Both
are UTC microsecond integers. If you omit both, they default to now; if you set only
`as_of_valid`, `as_of_recorded` uses that same instant. See the [API reference](../api/data.md)
for the full signature, then [read from a store](store.md).
