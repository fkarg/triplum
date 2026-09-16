"""Make sure the dataset is in the store: documents, chunks, and embeddings for a spec.
Everything is idempotent and skips what exists (design D6a)."""

from __future__ import annotations

from triplum.bench.runstore import Recorder
from triplum.embed.protocol import Embedder
from triplum.eval.datasets.hipporag import Dataset
from triplum.store.sqlite.store import SqliteStore


def ensure_documents(store: SqliteStore, ds: Dataset, rec: Recorder) -> None:
    n = store.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    if n == ds.chunks.height:
        return
    with rec.stage("index.documents"):
        store.put_documents(ds.documents, ds.grants)
        store.put_chunks(ds.chunks)


def ensure_embeddings(
    store: SqliteStore, ds: Dataset, embedder: Embedder, rec: Recorder, batch: int = 256
) -> None:
    ids = ds.chunks["id"].to_list()
    texts = ds.chunks["text"].to_list()
    have = store.has_embeddings(embedder.spec, ids)
    todo = [i for i, h in enumerate(have) if not h]
    if not todo:
        return
    with rec.stage(
        "index.embed", model=embedder.spec.model, provider=embedder.spec.runtime
    ) as ev:
        for start in range(0, len(todo), batch):
            idx = todo[start : start + batch]
            vecs = embedder.embed_passages([texts[i] for i in idx])
            store.put_embeddings(embedder.spec, [ids[i] for i in idx], vecs)
            ev.usage(sum(len(texts[i].split()) for i in idx), 0)
