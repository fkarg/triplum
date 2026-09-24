# Documents

A `Document` is text from one source. Its `id` must be unique across the corpus; `source` names
where it came from. If you give no segments, the whole text is one segment.

```python
from triplum.data.corpus import Document

doc = Document(id="note-1", source="notes", text="Alice met Bob.")
assert doc.segments[0].start == 0
assert doc.segments[0].end == len(doc.text)
```

Use `segments` when the source already gives you passages, pages, or turns. Their `start` and
`end` are character positions in `text`; `end` is excluded. `grants` lists who may read the
document and defaults to `("public",)`.

Next: [turn documents into frames](frames.md).
