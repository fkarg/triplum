# Collection

A **`Collection`** identifies the corpus you want to index and search together. For example,
your research notes and a benchmark's document corpus can be two collections: each gives an
experiment an explicit scope for its input material and derived records.

A [Source](source.md) holds one document's prepared text. A collection identifies the scope that
source belongs to. Different indexing strategies can work on the same collection; choosing a
collection and choosing how to process it are separate decisions.

## Example

```python
from triplum.datatype import Collection

collection = Collection(name="Research notes")
print(collection.name)  # Research notes
print(collection.id.version)  # 7
```

`name` is a human-readable label. `id` identifies the collection independently of its name and
is generated as a UUIDv7 unless you supply an ID. Names need not be unique. The record is a plain
Pydantic model with no storage behavior.

## Why membership is exclusive

The decided model gives each source exactly one collection. Its chunks and other derived records
stay in that scope. This keeps the indexing boundary clear: a pipeline can reason about one
corpus without deciding which of several memberships each output belongs to.

Overlapping collections would share source records, but would also require rules for sharing or
separating their derived outputs. We deliberately avoid that complexity. Including the same
document in two collections means separate collection-specific Source records. Reusing identical
computation is a separate optimization; it does not imply shared collection membership.

## Scope, permissions and storage

These answer different questions:

| Concept | Question it answers |
| --- | --- |
| Collection | Which corpus are we working with? |
| Source | Which input text are these chunks derived from? |
| Dataset and loader | Where do inputs come from, and how are they consumed? |
| Permissions | Which evidence may this viewer access? |
| Store | Where are records kept and how are they read back? |

A collection scopes the material considered; permissions further restrict what a viewer may
access within that scope. Collection membership alone does not grant access. The permission
interface remains to be designed.

A collection also does not require a separate database, directory or physical index. Those are
storage choices. Overlapping groups within a collection can organize records without changing
their collection membership; group interfaces are not implemented yet.

## Current support

The baseline currently supplies only `Collection` and its SQL mapping,
[`CollectionRow`][triplum.store.sql.tables.CollectionRow]. Source and chunk membership fields
and store methods for collections are not implemented yet; existing stores do not enforce
collection scope. See the [store guide](../infrastructure/store.md).

## Reference

[`Collection`][triplum.datatype.collection.Collection] in the API reference.

Next: [Source](source.md), identified input text.
