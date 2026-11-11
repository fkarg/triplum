"""Shared BM25 scoring and tokenization settings, independent of store behavior."""

from pydantic import ConfigDict, Field

from triplum.datatype import FingerprintedDataModel


class BM25Settings(FingerprintedDataModel):
    """Tokenization and Lucene BM25 scoring of one configuration; every field can be changed.

    Tokens are the whole matches of `token_pattern` in the (optionally lowercased) text, for
    chunks and queries alike; capture groups do not change them and empty matches are skipped.
    """

    model_config = ConfigDict(frozen=True)

    k1: float = Field(ge=0)  # bounds keep every matching chunk's score positive
    b: float = Field(ge=0, le=1)
    token_pattern: str = r"\w+"
    lowercase: bool = True


HIPPORAG1 = BM25Settings(k1=1.2, b=0.75)
"""Approximates HippoRAG 1's Elasticsearch `standard` analyzer: lowercased words, no stopwords."""

BM25S_DEFAULT = BM25Settings(k1=1.5, b=0.75, token_pattern=r"(?u)\b\w\w+\b")
"""bm25s defaults: its default token pattern drops one-character tokens."""
