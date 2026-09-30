# Documentation reader workflow

Use fresh agents to attempt concrete tasks through the documentation, then improve the docs
from verified findings. These are estimates of reader needs and behavior, not human usability
measurements. A model cannot forget its expertise by being told to act like a beginner.

This is a contributor workflow, excluded from the published site and search. It can be used
manually now; it requires no triplum retrieval pipeline or evaluation runner. No reader trial
has yet validated this workflow.

## Choose readers and tasks

Usually choose two or three profiles relevant to the change, with one concrete task each:

| Reader | Distinct documentation need |
| --- | --- |
| [Eager newcomer](eager-newcomer.md) | Learn concepts and dependencies from Python foundations. |
| [Dependency-familiar developer](dependency-familiar.md) | Understand our use of familiar tools and surprising behavior. |
| [Senior integrator](senior-integrator.md) | Find contracts, invariants, guarantees and extension boundaries. |
| [KG researcher](kg-researcher.md) | Establish paper fidelity, comparison conditions and research extensibility. |
| [Industry evaluator](industry-evaluator.md) | Assess adaptation, comparative experiments and operational limits. |

Profiles specify default knowledge, not credentials or personality. Vary Python experience,
domain knowledge and available compute independently when relevant. Reproduction, debugging,
extension-writing and returning with stale expectations are task variations, not separate
personas. Do not run every combination. Occasionally give different readers the same task.

## Prepare a run

1. Pick a task with an observable outcome: a cited answer, a working example, or a supported
   determination that the capability is unavailable. Include at least one status question when
   testing rebuild-sensitive material. Do not plant the expected answer in the reader's prompt.
2. Record the revision and any relevant working changes. Build a fresh site with
   `uv run mkdocs build --strict --site-dir <temporary-output-directory>`. Freeze the input for
   the round; if concurrent changes matter, build from a temporary copy of the selected files.
   A committed export alone cannot test unpublished edits.
3. Give readers the built site, including generated API pages, not the whole checkout, draft
   contracts, previous findings or this workflow's maintainer notes. Generated reference pages
   expose live code; their presence alone does not establish that an interface is approved.
4. State the access mode: **navigation** starts at an entry page and follows links/site search;
   **lookup** also permits text search over the built site. If no browser is available, local
   HTML reading can test content and links, but cannot substantiate search/UI usability claims.
5. If execution is part of the task, provide an environment matching that revision and scratch
   space. State installed dependencies, compute and permitted network/model use. No implicit
   paid calls, dataset downloads, secret access or writes to shared stores. Record environmental
   limits instead of treating them as documentation defects.

Fresh context means no inherited maintainer conversation (`fork_turns="none"` where supported).
It does not technically prevent an agent from opening forbidden files: retain its tool trace,
check compliance, and invalidate contaminated evidence. Use restricted tooling when available.

## Run, verify and improve

1. Send each reader the [shared prompt](reader-prompt.md), one profile, and its task settings.
   Readers work independently and read-only except for authorized scratch execution.
2. Collect [reports](report-template.md). Require paths/anchors and supporting excerpts for
   answers; commands, first failures and outputs for execution. Keep tool traces when available.
   A plausible answer or a cited page without supporting content is insufficient.
3. A maintainer verifies each material finding against the cited pages, actual access trace,
   relevant code and approved contracts. If a trace is unavailable, mark retrieval unverified;
   a matching quotation establishes textual support, not proof of navigation. Do not give this
   privileged investigation back to the original reader as a hint.
4. Group duplicates by task, page/section and underlying problem. Classify findings as blocking
   a task, materially misleading, avoidable friction, or preference. Separately record whether
   the cause is documentation, an unavailable capability, the environment, or reader inference.
5. Fix small, verified errors within approved behavior: broken links/examples, missing local
   explanations and inaccurate descriptions. Ask the owner before changing teaching structure,
   navigation, substantial tutorial scope, contracts or guarantees. Present the problem,
   smallest repair, alternatives and tradeoffs; group decisions instead of asking about wording.
6. Rebuild, rerun changed examples, and retry affected tasks with fresh readers who have not seen
   the fixes or earlier reports. A source-reading follow-up may be useful for an integrator, but
   report it separately: source-assisted success must not hide a documentation-only failure.

The verifier keeps dispositions: fixed, deferred with reason, rejected with reason, or awaiting
owner decision. Readers remain blind to them; the verifier filters repeated nitpicks afterward.
Save a concise run report under `docs/personae/runs/` when performing an actual run; link supporting
artifacts without copying secrets. There is no need to create empty run records in advance.

## Stop deliberately

Stop when fresh retries resolve the material findings, remaining blockers have explicit owner
dispositions, and remaining suggestions are preferences without a demonstrated task consequence.
Do not require extra clean rounds just to obtain a score. If a retry uncovers another material
failure, verify and address it; do not manufacture new tasks merely to keep reviewing.

Correctly discovering an unavailable capability is a success. Failing to find its status is a
documentation finding. An unavailable feature is not permission to implement it or document an
imagined workflow. Record deferred needs separately. Reopen a rejected finding only with new
evidence or a changed contract. Do not report synthetic pass rates as human comprehension rates.

## What good teaching should provide

Manual pages introduce one concept at a time, show a small runnable example, and explain the
necessary terms and dependency behavior at first use. Initial uncertainty is fine when the
learning path resolves it before the knowledge is needed. Link to authoritative upstream
explanations for general dependency knowledge; explain triplum-specific choices locally.
Generated reference supplies precise signatures and exhaustive detail. Test the connections
between these surfaces rather than forcing either to do both jobs.

Over successive runs, rotate through exposed concepts so the easy examples do not monopolize
review. This is a coverage intention, not a demand to add pages for unapproved interfaces.

## Basis and design review

[GOV.UK's usability guidance](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing)
supports realistic tasks without giving away navigation; its advice concerns human participants.
[Diátaxis](https://www.diataxis.fr/how-to-use-diataxis/) supports incremental improvements rather
than wholesale taxonomy changes. [FastAPI's tutorial](https://fastapi.tiangolo.com/tutorial/)
provides a model for progressive, example-led teaching.
[UXAgent](https://arxiv.org/abs/2504.09407) explores persona agents with observable interactions
as preparation for human studies, not a replacement for them.

A fresh agent proposed separating knowledge from tasks and adding debugging, extension and
returning-user lenses. Impact: incorporated as variations. The owner approved named profiles
with variations and rejected a separate curious reproducer; reproduction and compute constraints
now cut across profiles.

Claude Opus 5.5 (`claude-opus-5-5`) independently challenged the initial design. It tested corpus
leakage from ignored checkout artifacts, overlap between proposed readers, exclusion of drafts,
and whether a genuine quotation can still support a false answer. Impact: added corpus/access
checks, independent evidence verification and explicit status outcomes. Its overlap argument was
based on document size, not observed trials. Its proposals to merge profiles, require approved
answer banks, automate quotation checks and impose numerical stopping thresholds were not
adopted: they add maintenance before a pilot establishes a need. Run fewer profiles rather than
discarding distinct future needs. No automated checker is implied by this workflow.

See [the future benchmark idea](future-benchmark.md) for a possible later library example.
