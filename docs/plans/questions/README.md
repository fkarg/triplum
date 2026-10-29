# Design questions by area

Owner questions are tracked in one file per design area. The owner's answers are authoritative.
Specs record the resulting contracts once written; these files record questions, suggestions and
answers, and link to the spec that takes over.

| Area | File | Prefix | Status |
| --- | --- | --- | --- |
| Ingress, record identity and cache binding | [ingress-identity.md](ingress-identity.md) | Q | Active; moved from `open-questions.md` after the ingress session ended |
| Benchmark inputs, evidence and measurement | [benchmark-evidence.md](benchmark-evidence.md) | BE | Active, priority 1 |
| Retrieval results, Viewer and BM25 baseline | [retrieval.md](retrieval.md) | RT | Queued, priority 2 |
| LLM protocol and QA workflow | [llm-qa.md](llm-qa.md) | LQ | Queued, priority 3 |
| Dense retrieval and fusion | [dense-fusion.md](dense-fusion.md) | DF | Queued, priority 4 |

Cache binding against a concrete expensive block (priority 5) continues under the `Q` series.

## Process

- Number questions once per area with its prefix (`BE1`, `BE2`, …) and never reuse a number.
  Cross-area references use the full ID.
- Append new open questions as they arise, including questions left over from a session.
- After each owner answer, derive what follows: answers it implies for other questions (mark them
  "derived" and name the source answer) and new questions it raises, in whichever area they
  belong. When an implication is uncertain, ask it as a new question instead.
- Before presenting a question, ask a peer for an independent answer with `peer-review` (see
  AGENTS.md), without showing it our suggestion. Present both suggestions and name who chose what.
  Record the peer model, the review ID and any divergence.
- Move a question to "Answered" in its file when the owner answers it; keep the suggestions there.
- The active grill-me capture for priorities 1–4 is
  [benchmark baseline](../../brainstorms/2026-10-12-benchmark-baseline.md).
