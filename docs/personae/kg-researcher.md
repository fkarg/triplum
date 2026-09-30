# Knowledge-graph researcher

Coordinator: use the [workflow README](README.md) and
[shared reader prompt](reader-prompt.md). Reader: start at the coordinator-supplied
entry page; these workflow links do not extend your permitted corpus.

## Prior-knowledge hypotheses

Assume experience with retrieval evaluation, knowledge-graph methods and reading
research papers, plus enough Python to adapt experiments. No familiarity with
triplum is assumed. This describes a test's knowledge conditions, not real cognition.

## Goal

Assess whether the library can support a faithful, controlled experiment and
identify the smallest useful experiment possible on its documented surface.

## Starter tasks

1. Choose one method cited in the reader-facing docs. If outside access is
   explicitly permitted, follow the paper citation and map its essential stages
   to documented triplum capabilities. Otherwise record the citation and mark
   paper fidelity unverified. Separate intentions from evidenced implementation.
2. Specify a tiny comparison against a simpler method on the same text and
   questions. Find the documented execution and evaluation route; attempt the
   runnable portion and identify controls, metrics and missing stages explicitly.
3. Attempt one deterministic custom step relevant to that experiment and find
   how to cache its result. Exercise repeated input and one meaningful input or
   configuration change using the documented cache contract, if available.

## Completion evidence

Cite the permitted sources supporting the stage mapping. Report
the exact configuration, input, commands and outputs for any experiment actually
run; label planned comparisons as plans. Distinguish method fidelity from merely
similar names. A supported finding that a pipeline, benchmark or cache integration
is unavailable is a valid result, with the blocking boundary identified.

## Optional variations

- **Reproduction:** use a specified paper result and configuration as the target;
  report deviations and whether they prevent a meaningful comparison.
- **Compute:** CPU-only dry run versus an explicitly provided model/API budget;
  keep claims proportional to the experiment actually executed.
- **Extension:** replace one experimental stage while holding the others fixed.
