# Data-model fingerprint implementation plan

Owner-authorized execution in the existing checkout; parent owns production code, docs author owns
concept page sync, independent peer reviews the declaration and final diff.

Spec: [Data-model fingerprints](../specs/data-model-fingerprints.md).

- [x] Review the exact field projection and encoding boundary with host Opus.
- [x] Add failing behavior tests for the simple data base, nested identity/exclusions, type distinctions,
      extras, and codec detection of serialization loss.
- [x] Implement `datatype.fingerprint.FingerprintedModel` and export it from `datatype`.
- [x] Exercise bare `@cached` with the new type and a temporary default-cache directory, including
      repeated calls and cache reopen; preserve explicit methods for external types.
- [x] Simplify the pipeline's Text and Analysis declarations and concept-page examples.
- [x] Update implementation status, record peer findings, run relevant tests and documented examples,
      typing/lint, full suite and strict docs; commit the coherent change.

Keep computation identity independent. No record UUID/property migration, dataset redesign, global
content_key changes, or new storage/codec format namespaces. The concurrent dirty-serving fix owns
its hook/config/test changes and is committed separately.
