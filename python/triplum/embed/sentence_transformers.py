"""sentence-transformers adapter: picks cuda, mps or cpu and records it in the spec, along with the
resolved weights commit, max sequence length, instruction text and padding side, because each of
those silently changes the vectors."""

from __future__ import annotations

import numpy as np

from triplum.embed.protocol import EmbeddingSpec, l2_normalize, render_query_prefix


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _hf_commit(name: str) -> str | None:
    """Resolved commit sha of the cached snapshot, so the spec pins weights, not a tag."""
    try:
        from huggingface_hub import scan_cache_dir

        for repo in scan_cache_dir().repos:
            if repo.repo_id == name and repo.revisions:
                return max(repo.revisions, key=lambda r: r.last_modified).commit_hash
    except Exception:  # noqa: BLE001 - cache scan is best effort
        return None
    return None


class SentenceTransformersEmbedder:
    def __init__(self, spec: EmbeddingSpec, model, batch_size: int = 32) -> None:
        self.spec = spec
        self.model = model
        self.batch_size = batch_size

    @classmethod
    def from_model(
        cls,
        name: str,
        *,
        query_template: str = "",
        passage_prefix: str = "",
        device: str | None = None,
        batch_size: int = 32,
        trust_remote_code: bool = False,
        max_seq_length: int | None = None,
        instruction: str = "",
        padding_side: str = "",
        revision: str | None = None,
    ) -> SentenceTransformersEmbedder:
        from sentence_transformers import SentenceTransformer

        device = device or pick_device()
        model = SentenceTransformer(
            name, device=device, trust_remote_code=trust_remote_code, revision=revision
        )
        if max_seq_length is not None:
            model.max_seq_length = max_seq_length
        if padding_side:
            model.tokenizer.padding_side = padding_side
        resolved = revision or _hf_commit(name) or "unknown"
        dims = model.get_embedding_dimension()
        if dims is None:
            raise ValueError(f"Cannot determine embedding dimensions for {name}")
        spec = EmbeddingSpec(
            model=name,
            revision=str(resolved),
            dims=dims,
            pooling="model",
            normalize=True,
            query_prefix=render_query_prefix(query_template, instruction),
            passage_prefix=passage_prefix,
            quantization="fp32" if device == "cpu" else "fp16",
            runtime=f"sentence-transformers:{device}",
            max_seq_length=int(model.max_seq_length) if model.max_seq_length else None,
            instruction=instruction,
            padding_side=padding_side,
        )
        return cls(spec, model, batch_size)

    def _embed(self, texts: list[str], prefix: str) -> np.ndarray:
        arr = self.model.encode(
            [prefix + t for t in texts],
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        ).astype(np.float32)
        return l2_normalize(arr) if self.spec.normalize else arr

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.query_prefix)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, self.spec.passage_prefix)
