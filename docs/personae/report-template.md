# Reader run report

Copy this template for an actual run. Keep the reader's evidence separate from maintainer checks.

## Run

- Corpus revision, relevant uncommitted changes, build command and output location:
- Selected tasks, profiles and variations:
- Agent serving models and fresh-context setup:
- Access mode, entry pages, tools, execution environment and permissions:
- Reports/tool traces and limitations (including any unavailable access evidence):

## Reader evidence (one section per task)

- Task ID, goal and assumed prior knowledge:
- Outcome: completed / blocked / correctly identified as unavailable / inconclusive:
- Route: visited pages, queries and dead ends:
- Answer with page/anchor, short supporting excerpt and reasoning:
- Prior knowledge, undocumented inference or intervention:
- Execution: exact commands, environment, first failure, exit status and relevant output;
  otherwise “not executed”:
- Confusion: prerequisite, where needed, explanation found or missing, task consequence:

## Maintainer findings and decisions

For each distinct finding record:

- Stable ID, task ID and page/section; duplicate of an earlier finding, if applicable:
- Verified evidence and access-trace check (or retrieval unverified):
- Impact: task blocker / materially misleading / avoidable friction / preference:
- Cause: documentation / unavailable capability / environment / unsupported reader inference:
- Smallest correction; owner decision needed and alternatives, if material:
- Disposition: fixed / deferred with reason / rejected with reason / awaiting owner:

## Retry and stopping decision

- Changed files, strict build result and example execution results:
- Fresh readers, corpus revision, tasks retried and outcomes:
- Unresolved material findings and owner dispositions:
- Stop or continue, with concrete reason:

These outcomes describe agent task attempts, not measured human usability or overall KG coverage.
