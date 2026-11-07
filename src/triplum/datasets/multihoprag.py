"""MultiHop-RAG corpus (Tang and Yang, 2024; ODC-BY): 609 news articles as `Source` records."""

import json
from pathlib import Path
from uuid import UUID

from triplum.datasets.files import datasets_home, fetch
from triplum.datatype import Source
from triplum.utils.cache import content_key
from triplum.utils.data import Dataset

URL = "https://huggingface.co/datasets/yixuantt/MultiHopRAG/resolve/main/corpus.json"
SHA256 = "20b61b5ab84de84a927420c5d265b7ec8d859ae49980699958a787ade9e4d28f"


def download(root: Path | None = None) -> Path:
    """Fetch the pinned `corpus.json` into `root` unless a verified copy exists; return its path.

    `root` defaults to `datasets_home()`.
    """
    root = datasets_home() if root is None else root
    return fetch(URL, root / "multihoprag" / "corpus.json", SHA256)


class MultiHopRAGCorpus(Dataset[Source]):
    """One `Source` per article: `origin` is the article URL, `text` is title, blank line, body.

    The file is downloaded into `root` on first use (`download`), verified against its pinned
    hash and parsed at construction. Sources belong to the collection `collection_id`.
    """

    def __init__(self, *, collection_id: UUID, root: Path | None = None) -> None:
        self.collection_id = collection_id
        self.articles = json.loads(download(root).read_bytes())

    def __len__(self) -> int:
        return len(self.articles)

    def __getitem__(self, index: int) -> Source:
        article = self.articles[index]
        return Source(
            collection_id=self.collection_id,
            origin=article["url"],
            text=f"{article['title']}\n\n{article['body']}",
        )

    def fingerprint(self) -> str:
        return content_key("multihoprag-corpus", [SHA256, str(self.collection_id)])
