"""MultiHop-RAG corpus (Tang and Yang, 2024; ODC-BY): 609 news articles as `Source` records."""

import hashlib
import json
import urllib.request
from pathlib import Path

from triplum.datatype import Source
from triplum.utils.data import Dataset

URL = "https://huggingface.co/datasets/yixuantt/MultiHopRAG/resolve/main/corpus.json"
SHA256 = "20b61b5ab84de84a927420c5d265b7ec8d859ae49980699958a787ade9e4d28f"


def _verified(path: Path) -> bool:
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == SHA256


def download(root: Path) -> Path:
    """Fetch the pinned `corpus.json` into `root` unless a verified copy exists; return its path."""
    path = root / "multihoprag" / "corpus.json"
    if _verified(path):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    urllib.request.urlretrieve(URL, part)
    if not _verified(part):
        raise ValueError(f"{URL} does not match the pinned sha256 {SHA256}")
    part.replace(path)
    return path


class MultiHopRAGCorpus(Dataset[Source]):
    """One `Source` per article: `origin` is the article URL, `text` is title, blank line, body.

    The whole file is parsed at construction and must match the pinned hash.
    """

    def __init__(self, path: Path) -> None:
        if not _verified(path):
            raise ValueError(f"{path} does not match the pinned sha256 {SHA256}")
        self.articles = json.loads(path.read_bytes())

    def __len__(self) -> int:
        return len(self.articles)

    def __getitem__(self, index: int) -> Source:
        article = self.articles[index]
        return Source(origin=article["url"], text=f"{article['title']}\n\n{article['body']}")

    def fingerprint(self) -> str:
        return SHA256
