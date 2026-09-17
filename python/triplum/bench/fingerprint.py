"""Code fingerprint per pipeline: the sha256 of the source files a pipeline actually executes.

Part of the run identity instead of the git sha, so a change to the CLI, the report, or the docs
does not orphan finished runs, while a change to a stage the run depends on does. The git sha and
dirty flag are still recorded on the run for bookkeeping.
"""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

# Modules every pipeline depends on: data layer, store, cache, LLM adapters (real and fake),
# reader, metrics, datasets, and the factories that assemble them. Dataset parsers are not listed
# because a parser change alters corpus_hash and questions_hash, which are identity fields.
BASE = [
    "triplum.data.schema",
    "triplum.data.viewer",
    "triplum.cache",
    "triplum.llm.protocol",
    "triplum.llm.cached",
    "triplum.llm.openai_compat",
    "triplum.llm.cli",
    "triplum.llm.fake",
    "triplum.store.protocol",
    "triplum.store.sqlite.store",
    "triplum.store.sqlite.acl",
    "triplum.generate.reader",
    "triplum.eval.metrics",
    "triplum.eval.judge",
    "triplum.eval.datasets.base",
    "triplum.eval.datasets.registry",
    "triplum.eval.datasets.hipporag",
    "triplum.retrieve.stages",
    "triplum.bench.factories",
    "triplum.bench.index",
    "triplum.bench.runner",
]
EMBED = [
    "triplum.embed.protocol",
    "triplum.embed.cached",
    "triplum.embed.openai_compat",
    "triplum.embed.sentence_transformers",
    "triplum.embed.fastembed",
    "triplum.embed.fake",
]
RERANK = [
    "triplum.rerank.protocol",
    "triplum.rerank.cached",
    "triplum.rerank.cross_encoder",
    "triplum.rerank.fake",
]

PIPELINE_MODULES = {
    "closed_book": BASE,
    "oracle": BASE,
    "bm25": BASE,
    "dense": BASE + EMBED,
    "hybrid": BASE + EMBED + RERANK,
}

# Non-Python sources the data layer depends on, relative to the repository root.
EXTRA_FILES = ["python/triplum/store/sqlite/migrations.sql", "crates/triplum-core/src/schema.rs"]


def _repo_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def source_paths(pipeline: str) -> list[Path]:
    paths = []
    for mod in PIPELINE_MODULES[pipeline]:
        m = importlib.import_module(mod)
        if m.__file__:
            paths.append(Path(m.__file__))
    root = _repo_root()
    if root is not None:
        paths += [root / f for f in EXTRA_FILES if (root / f).exists()]
    return paths


def code_hash(pipeline: str) -> str:
    """Hash of the *contents* of the pipeline's source files, in a fixed order."""
    h = hashlib.sha256()
    for p in sorted(source_paths(pipeline)):
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]
