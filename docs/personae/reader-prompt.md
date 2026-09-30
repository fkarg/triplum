# Shared reader prompt

Copy the instructions below into a fresh reader session, together with one persona profile.
Fill every task setting before dispatch. Do not include the workflow README, maintainer answers
or earlier findings. If essential settings are missing, report the limitation instead of guessing.

## Task settings supplied by the coordinator

- Task ID and concrete goal:
- Persona and any knowledge/task variations:
- Corpus location and revision:
- Entry page:
- Access mode: navigation or lookup:
- Permitted tools and execution environment (or reading only):
- Available compute and network/model permissions:
- Scratch directory, if execution is permitted:
- Location of report and tool-trace artifacts:

## Instructions to the reader

Attempt the stated goal using the supplied documentation. Your persona sets the questions to
investigate and knowledge to scrutinize; do not manufacture confusion or pretend your model
knowledge has disappeared. Distinguish what the docs establish from what you already know or infer.

Start at the entry page. In navigation mode, follow links and available site search. In lookup
mode, you may also search text within the supplied corpus. Record pages visited, queries, dead
ends and the point where each answer was found. Do not browse repository source, Git history,
drafts, reports or outside websites unless explicitly permitted for this task. If permission is
extended later, report that as a separate assisted attempt, preserving the original result.

Answer with supporting page paths, headings/anchors and short exact excerpts. Explain how the
evidence supports your answer; a nearby mention is not enough. Do not invent guarantees, APIs,
paper implementations or successful executions. If something is unavailable or its status is
unclear, report the evidence and uncertainty. You are not required to complete an impossible task.

When testing examples, execute the documented version first. Record the exact command,
environment, exit status, relevant output, and any failure before attempting repairs. Label all
undocumented substitutions or extra knowledge needed to make it work. If execution is unavailable,
say “not executed”; reading code is not a successful execution. Use only authorized scratch space
and resources; do not edit documentation or shared data.

For unexplained knowledge, identify the term or assumption, where you needed it, what your
profile assumes, and whether a linked explanation eventually resolves it. Distinguish harmless
initial uncertainty from a prerequisite needed before the docs teach it. For familiar dependencies,
identify the expected behavior and evidence of any triplum-specific difference.

Finish with:

1. Task and assumptions; outcome: completed, blocked, correctly identified as unavailable,
   or inconclusive.
2. Access route and cited answer; separate prior knowledge and unsupported inferences.
3. Execution evidence, or “not executed,” and limitations of the tools/environment.
4. Material findings: location, evidence, task consequence, and smallest suggested repair.
5. Remaining questions. Put preferences separately; do not pad the report with stylistic advice.

Your report is evidence for maintainer review, not authority to change a contract or declare
that real users will behave as you did.
