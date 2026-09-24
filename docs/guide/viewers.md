# Viewers

Every store read takes a `Viewer`. Its principals are the identities whose grants the caller
holds. A public read uses `Viewer.of("public")`.

```python
from triplum.data.viewer import Viewer

viewer = Viewer.of("public")
assert viewer.principals == frozenset({"public"})
```

You can also set `as_of_valid` for world time or `as_of_recorded` for what the store knew then.
Both are UTC microsecond integers. If you omit both, they use now; if you set only `as_of_valid`,
`as_of_recorded` uses that same value. See the [API reference](../api/data.md) for the full
signature.
