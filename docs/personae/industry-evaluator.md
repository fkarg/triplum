# Industry feasibility evaluator

Coordinator: use the [workflow README](README.md) and
[shared reader prompt](reader-prompt.md). Reader: start at the coordinator-supplied
entry page; these workflow links do not extend your permitted corpus.

## Prior-knowledge hypotheses

Assume practical Python and document-search experience, with a concrete business
use case but no triplum knowledge. Domain expertise may exceed graph-research
expertise. These are evaluation assumptions, not a simulated buyer's psychology.

## Goal

Judge whether a small comparative proof of concept is feasible, what engineering
work it requires and which limitations prevent a justified recommendation.

## Starter tasks

1. Use three synthetic documents shaped like your own domain, with two questions
   and expected supporting passages. Find the documented route from this custom
   data to sources and chunks; run the smallest supported portion.
2. Identify a simple comparison for the use case, such as ordinary document
   retrieval versus a graph-based approach. Find which parts can actually be run
   and measured through documented interfaces; record missing capabilities and
   avoid presenting a proposed comparison as a completed benchmark.
3. Investigate the documented store and cache boundaries for repeating the proof
   of concept. Attempt a small persistence or reuse example where supported, and
   identify documented evidence or open questions about data access, external
   processing, cost and the selected dependencies' reuse terms.

## Completion evidence

Provide the sample data, attempted commands, observed outputs and cited pages.
Produce a short feasibility assessment separating measured results, documented
guarantees and unresolved requirements. State what a next experiment would cost
or require only to the extent supported by evidence. Treat production readiness,
security and deployment suitability as questions to establish, not promises.

## Optional variations

- **Domain:** substitute synthetic support tickets, technical manuals or policies;
  do not introduce confidential material into the evaluation.
- **Compute:** local-only evaluation versus an explicitly authorized hosted-model
  budget; compare the scope each permits without guessing performance.
- **Returning user:** revisit an earlier feasibility assessment and identify which
  documented changes, if any, alter its conclusion.
