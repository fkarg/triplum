"""Make sure the dataset is in the store: documents, chunks, and embeddings for a spec.
Everything is idempotent and skips what exists (design D6a)."""

from __future__ import annotations

from triplum.bench.runstore import Recorder
from triplum.embed.protocol import Embedder
from triplum.eval.datasets.base import Dataset
from triplum.store.sqlite.store import SqliteStore


class CorpusMismatch(RuntimeError):
    pass


def ensure_documents(store: SqliteStore, ds: Dataset, rec: Recorder) -> None:
    """A store file is bound to exactly one corpus, identified by content hash."""
    bound = store.get_meta("corpus_hash")
    if bound == ds.corpus_hash:
        return
    if bound is not None:
        raise CorpusMismatch(
            f"store {store.path} holds corpus {bound[:12]}, dataset is {ds.corpus_hash[:12]}"
        )
    with rec.stage("index.documents"):
        store.put_documents(ds.documents, ds.grants)
        store.put_chunks(ds.chunks)
        store.set_meta("corpus_hash", ds.corpus_hash)
        store.set_meta("dataset", ds.name)


def ensure_embeddings(
    store: SqliteStore, ds: Dataset, embedder: Embedder, rec: Recorder, batch: int = 256
) -> None:
    ids = ds.chunks["id"].to_list()
    texts = ds.chunks["text"].to_list()
    have = store.has_embeddings(embedder.spec, ids)
    todo = [i for i, h in enumerate(have) if not h]
    if not todo:
        return
    with rec.stage("index.embed", model=embedder.spec.model, provider=embedder.spec.runtime) as ev:
        for start in range(0, len(todo), batch):
            idx = todo[start : start + batch]
            vecs = embedder.embed_passages([texts[i] for i in idx])
            store.put_embeddings(embedder.spec, [ids[i] for i in idx], vecs)
            ev.usage(sum(len(texts[i].split()) for i in idx), 0)
