# SOTA discovery pipeline

How we find new techniques to adopt, and how a found paper turns into code. State of the sources
as of 2026-09-16.

## Why a pipeline

Conference papers in this niche (SEMANTiCS, ISWC, ESWC, CIKM, SIGIR, ACL/EMNLP, NeurIPS/ICLR, VLDB
workshops) are new, barely cited, and often not on arXiv at all. Model training data misses them
entirely. A scripted monitor plus a reading ledger is the only way to stay current.

## Sources and access

| Source | Access | Notes |
|---|---|---|
| arXiv API | `http://export.arxiv.org/api/query?search_query=cat:cs.CL+AND+all:graphrag` | No key. Terms of use: one request per three seconds, single connection. Spurious 429s reported in 2026. OAI-PMH for category listings. Categories: cs.CL, cs.AI, cs.DB, cs.IR. |
| Hugging Face papers | `GET /api/daily_papers?date|week|month&p&limit&sort`, `GET /api/papers/search?q=` | No auth, verified live 2026-09-16. Spec at `huggingface.co/.well-known/openapi.md`. |
| OpenAlex | `api.openalex.org/works?search=...&api_key=` | A key is **not** mandatory (the Feb 2026 announcement was walked back; docs updated 2026-08-19). Model is a daily dollar budget: keyless 0.10 USD/day, free key 1 USD/day. Polite pool and `mailto` are gone. Bulk snapshot still CC0 on S3. |
| Semantic Scholar | `api.semanticscholar.org/graph/v1/paper/search`, `/search/bulk` | Free key via `x-api-key` header gives 1 request/s; without a key you share one pool with every other unauthenticated user and get 429s readily. The older "5,000 per 5 min" figures are obsolete. |
| dblp | SPARQL endpoint / RDF dumps | The JSON search API is behind Anubis anti-bot; automated fetches got 403 on 2026-09-16. Use SPARQL. |
| CEUR-WS | probe `ceur-ws.org/Vol-NNNN/` | No RSS. Volumes are sequential (around Vol-4226 in Sept 2026); diff the homepage or probe the next numbers. Volume pages carry RDFa. ESWC 2026 workshop volumes are out (4205, 4212). SEMANTiCS research papers are LNCS (Springer), not CEUR; workshops (e.g. SGKi) are CEUR. |
| alphaXiv | MCP server `https://api.alphaxiv.org/mcp/v1` | OAuth or bearer key; no documented public REST. |
| Papers With Code | revived at `paperswithcode.co` | The original `.com` was sunset 2025-07-24 and still redirects to HF Trending Papers with deep links dead; snapshot in HF org `pwc-archive`. A revival at **paperswithcode.co** (`.co`) exists (Niels Rogge's Hugging Face post of 2026-08-21 dates it to about three months earlier; the exact shutdown and revival dates are not documented at a primary source); its leaderboards are unchecked. |
| Conference programmes | scrape | The `fkarg/semantics_2026_schedule` site is the seed for SEMANTiCS 2026 (61 talks with abstracts). ISWC 2026 is Bari, 25–29 Oct. |

## Tooling

- **paper-qa** (FutureHouse, Apache-2.0, 2026.8.12): reading piles of PDFs with citations; CalVer,
  LiteLLM-based, OpenAlex metadata, OpenReview conference pull. Use it for *reading*, not
  monitoring.
- Agentic literature monitors (URSA, DeepXiv-SDK, PaSa) are research prototypes; nothing
  production-grade found. We write our own small monitor instead.

## Planned layout

```
research/
  monitor/        scripts: arxiv.py, hf_papers.py, openalex.py, ceur.py; one cron entry
  digests/        YYYY-WW.md weekly digest, auto-generated, triaged by hand
  papers/         one note per adopted or rejected paper: claim, setup, what we implement, status
  ledger.md       table: paper, venue, date, status (candidate | reading | adopting | rejected), link to note and to pipeline
```

Rules:
- The digest is generated; the triage marks are human.
- A paper enters `papers/` only when someone reads it. The note records the exact experimental
  setup so the reproduction is comparable.
- A paper reaches `adopting` only with a benchmark run in the harness showing the delta.

## Search terms to seed the monitor

graphrag, "graph retrieval-augmented", "knowledge graph construction" llm, "triple extraction" llm,
"entity resolution" llm, "temporal knowledge graph" rag, "bi-temporal", "permission-aware rag",
"access control" rag, text2kgbench, "ontology-aware" extraction, "hypothetical question" retrieval,
"multi-hop" rag benchmark, "llm-as-a-judge" rag, shacl llm.

## Sources

<https://info.arxiv.org/help/api/tou.html>, <https://huggingface.co/.well-known/openapi.md>,
<https://help.openalex.org/api/authentication/>, <https://www.semanticscholar.org/product/api/tutorial>,
<https://dblp.org/faq/How+to+use+the+dblp+search+API.html>, <https://ceur-ws.org/>,
<https://www.alphaxiv.org/docs/mcp>, <https://hyper.ai/en/news/42900>,
<https://github.com/Future-House/paper-qa>.
