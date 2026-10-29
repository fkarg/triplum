# Retrieval results, Viewer and BM25 baseline

Questions use the `RT` prefix. Process: [questions index](README.md).

## Open

Round 3 peer: gpt-6.1-sol, review `a1347712184249d3a9dfb7431bd9c534`. Working frame:
[interface map](../interface-map.md).

### RT1. Retrieval hit record

`RetrievalHit(chunk: Chunk, score: float | None)`, list order is rank, producer recorded with the
stage. Claude and peer agree.

### RT2. Retriever and oracle

Retriever configured with k, called per question with the public input and Viewer. Oracle is a
privileged selector receiving evidence (Claude revised to the peer). Open: one input record versus
separate arguments.

### RT3. Viewer contract (queued)

Store reads take no Viewer today; the Retriever cannot be access-safe until they do. One `as_of`
cannot express both valid and transaction time.

## Answered
