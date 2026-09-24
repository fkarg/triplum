"""Knowledge-graph construction from chunks: extractors produce grounded spans and claims, the
stages turn them into the canonical entity, fact, support and mention frames, and resolvers add
`same_as` facts between entities of different documents."""

from triplum.extract.protocol import (
    CLAIM_SCHEMA,
    SPAN_SCHEMA,
    Extraction,
    Extractor,
    ExtractorSpec,
    ResolverSpec,
)
from triplum.extract.stages import build, extract, resolve

__all__ = [
    "CLAIM_SCHEMA",
    "SPAN_SCHEMA",
    "Extraction",
    "Extractor",
    "ExtractorSpec",
    "ResolverSpec",
    "build",
    "extract",
    "resolve",
]
