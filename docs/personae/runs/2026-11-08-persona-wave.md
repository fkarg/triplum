# Persona documentation wave (2026-11-08)

Input: built site from main at 3165d1e. Synthetic reader trial, not a measurement of human
comprehension. Readers got the built site (including generated API pages), lookup access,
execution through the repository virtual environment with an isolated `XDG_CACHE_HOME`, no
network, downloads or model calls, and no access to source, tests or development records.
Reports and scratch work stayed machine-local; this record summarises them.

## Round 1: tasks and outcomes

| Reader | Task | Outcome |
| --- | --- | --- |
| Eager newcomer (N1) | Retrieve over own passages; generate an answer | Retrieval completed; answer generation correctly identified as unavailable |
| Dependency-familiar (D1) | Store round trip on memory and SQLite | Completed |
| Senior integrator (S1) | Custom retriever and recall; dense and fusion status | Completed; dense and fusion correctly identified as unavailable (fusion only inferred) |
| KG researcher (K1) | Reproduce fixture numbers; cache an experiment; graph retrieval status | Completed (numbers matched exactly); graph retrieval and PPR correctly identified as unavailable |
| Industry evaluator (I1) | Access-controlled proof of concept; comparative proof of concept | Access-controlled run completed; comparison correctly identified as not feasible yet |

No reader was blocked. Every documented example they ran matched its documented output.

## Verification

A fresh verifier checked each finding against the pages, code and approved specs: 17 confirmed,
3 partly confirmed, none refuted. Classification and disposition:

| Finding | Class | Cause | Disposition |
| --- | --- | --- | --- |
| API reference hides every `__call__` (filter `!^_` also drops dunders) | Materially misleading | Tooling | Fixed: filter keeps `__call__` |
| Trailing `/` missing when all parameters are positional-only (mkdocstrings-python 2.0.8–2.0.10 template) | Avoidable friction | Tooling | Fixed: template override adds it |
| Triplum's own licence absent from the site; polars, pyarrow, pydantic, pydantic-ai missing from licences | Materially misleading | Docs | Fixed: own licence stated; rows from installed metadata, including pydantic-ai-slim and the provider SDKs; remaining default extras listed as unrecorded |
| Random collection id defeats cross-run cache reuse | Materially misleading | Docs | Fixed: cache guide explains it with a pinned-id chunker example |
| Rerun with a new collection duplicates sources and hits | Materially misleading | Docs | Fixed: retrieval page warns; scoping is owner question Q33 |
| Restricted text stays readable in `cache.sqlite`, also after clear | Materially misleading | Docs | Fixed: guidance (own cache file, VACUUM after clear; verified the marker is gone once the connection closes). Deeper mechanics deferred by owner policy RT7 |
| `sys.stderr` in a cached step: error names neither reference nor function | Avoidable friction | Diagnostics | Fixed: errors name the path (`step references log: log references sys.stderr: …`); guide shows logging that works |
| `@cached` with `-> list[Chunk]`: unclear error, no wrapper example | Avoidable friction | Diagnostics, docs | Fixed: message says to wrap lists; guide example |
| Unknown fields on Source and Chunk silently ignored | Avoidable friction | Docs | Documented; forbidding is owner question Q34 |
| Protocol requirements vs BM25 rules unclear | Avoidable friction | Docs | Fixed: page separates them; promotion is owner question RT9 |
| Recall trusts inputs; unreadable gold counts as miss | Avoidable friction | Docs | Fixed: recall page, with pointer to the permissions limit |
| Custom retriever identity undefined | Avoidable friction | Docs | Fixed: stated as not yet defined |
| Fusion status only implicit | Preference | Docs | Fixed in flow.md |
| `close()` only on SQLAlchemyStore; "all three importable" | Avoidable friction | Docs | Fixed |
| Viewer link, whole-token matching and common words (N1) | Preference | Docs | Fixed |
| Fixture span gold equals passage gold | Preference | Docs | Fixed |
| BM25 indexes only `chunk.text`, no analyzer hook (K1) | Avoidable friction | Capability | Deferred: owner RT8 (tokenizer grows with indexing, stemming later) |
| `engine` attribute renders only one branch | Preference | Tooling | Deferred: griffe rendering, low value |
| Store guide reachable only through navigation | Preference | Docs | Partly addressed by the new links from retrieval; no navigation change |

Fix commit: 6dff94b. Checks: 535 non-model tests, ty, Ruff, Cargo check and strict MkDocs passed;
each changed example was rerun with its documented output.

## Owner questions raised

Q34 (forbid unknown record fields), Q33 (collection-scoped reads, with new evidence) and RT9
(retriever protocol obligations), each with the session's and the peer's independent answers in
the question files. Peer: gpt-6.1-sol (Codex), 2026-11-08; attempted falsifications were analytic
only (no code inspected). Impact: Q34 agreement; Q33 dissent (peer: optional `collection_id`
filter on `sources()` and an explicit BM25 choice); RT9 partial dissent (peer: promote the `k < 1`
rule and add a benchmark reproducibility requirement). The brief misstated BM25's `k < 1`
behaviour as returning `[]`; it raises `ValueError`, noted with RT9.

## Round 2: retry with fresh readers

Three fresh readers, blind to round 1 and the fixes, retried the affected tasks on a site built
from the fixed working tree, with the same access limits.

| Reader | Task | Outcome |
| --- | --- | --- |
| KG researcher (K2) | Cached chunking reused by a second process; progress to stderr; graph retrieval status | Completed: second process reused results, a changed chunk size recomputed and switching back reused; logging worked; the `sys.stderr` error named the reference. Graph retrieval correctly identified as unavailable |
| Senior integrator (S2) | Custom retriever from the docs and API reference; protocol vs BM25 rules; field mistakes; fusion status | Completed: signatures (including `/` and `*`) right from the API pages, ty accepted the retriever, recall ran over SQLite. Fusion correctly identified as unavailable |
| Industry evaluator (I2) | Private-corpus suitability: licences, restricted text, recall under access, reruns; dense comparison status | Completed: licences found; cache advice found; rerun duplication reproduced and the documented fixed id fixed it. Dense comparison correctly identified as not possible yet |

Verified round-2 findings and dispositions:

| Finding | Class | Disposition |
| --- | --- | --- |
| "Filter before choosing the top `k`" in the decisions table but not in the retrieval contract, which round 1 had called complete (S2) | Materially misleading (introduced by round 1) | Fixed: the contract states it, matching the Protocol docstring and AGENTS.md |
| SQLite store file holds restricted text readable by other local users (I2) | Materially misleading | Fixed: store page says access is enforced only through triplum; restrict file permissions |
| Stale copies from an earlier run zero recall silently (I2) | Avoidable friction | Fixed: recall page note linking the rerun warning |
| Transitive dependencies not recorded (I2) | Avoidable friction | Fixed: stated on the licences page |
| `RetrievalHit` ignores unknown fields (S2) | Avoidable friction | Documented; same decision as Q34 |
| Cross-process reuse needs facts from three places (K2) | Avoidable friction | Fixed: one sentence and link in "Cache a chunker" |
| Empty graph API page (K2) | Avoidable friction | Fixed: module docstring says not implemented |
| `cache stats` shows only digests (K2) | Rejected | `--details` and `--name` show names; documented in administration |
| Logfire telemetry default, per-viewer BM25 statistics, access revocation (I2) | Open | Unverified or planned; no change |

The wave stops here: no task was blocked in either round, and the remaining items are owner
questions (Q33, Q34, RT9) or deferred by owner policy (RT7, RT8).
