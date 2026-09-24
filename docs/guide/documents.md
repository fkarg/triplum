# Documents

Use a `Document` for one piece of source text. Give it an `id` that is unique in the corpus and a
`source` that names where the text came from.

```python
from triplum.data.corpus import Document

doc = Document(id="note-1", source="notes", text="Alice met Bob.")
assert doc.segments[0].start == 0
assert doc.segments[0].end == len(doc.text)
```

With no `segments`, the whole text becomes one segment. A segment is a piece the source already
defines, such as a page or a transcript turn. Triplum does not split the text further here.

The default `grants=("public",)` makes the document readable by a viewer with the `public`
principal. Set `grants` explicitly for restricted text. See [viewers](viewers.md) for a read
example.

Next: [turn documents into frames](frames.md).
