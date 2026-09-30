# Senior library integrator

Coordinator: use the [workflow README](README.md) and
[shared reader prompt](reader-prompt.md). Reader: start at the coordinator-supplied
entry page; these workflow links do not extend your permitted corpus.

## Prior-knowledge hypotheses

Assume substantial Python library integration experience, structural typing,
storage abstractions and testing. Do not assume knowledge of triplum's contracts
or project history. These are scope assumptions, not claims about senior readers.

## Goal

Determine what can be safely composed into an existing application and what
behavior still requires clarification or investigation.

## Starter tasks

1. Trace one tiny input through the documented source, chunk and step boundaries.
   Write a compact contract table covering inputs, outputs, identity and stated
   guarantees, leaving unspecified behavior explicitly open.
2. Attempt to substitute a deterministic custom implementation for one documented
   step. Check how the docs establish conformance and how you can exercise that
   implementation without adopting a larger pipeline.
3. Design a small store-and-cache integration exercise for that input. Use the
   documented surfaces to test the guarantees they actually promise, including
   reuse or reopening only where described. Name unanswered ownership, persistence
   or invalidation questions that matter to the integration.

## Completion evidence

Supply the contract table, minimal exercise and observed results, with a citation
for each relied-on guarantee. Separate an explicit contract from example behavior
and from your inference. If source inspection is allowed by the shared prompt,
report source inspection as a separate assisted attempt, preserving the original
documentation-only outcome. An implementation detail is not a public guarantee.

## Optional variations

- **Extension:** integrate an existing application step rather than a toy one.
- **Debugging:** investigate a supplied discrepancy between documentation and a
  store or cache observation.
- **Returning user:** assess a supplied older integration against current docs,
  listing changes needed and uncertainty without assuming compatibility.
