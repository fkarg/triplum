# Cache interface documentation trials

## Scope and corpus

The owner requested the existing reader personas, cache subpages and examples for implementing
each exposed interface. These are synthetic task attempts, not human usability measurements.

Baseline: main at 3081381, built to `/tmp/triplum-identity-personae-site`. Uncommitted identity
specs are excluded from the site. Two fresh-context readers received only the shared prompt,
one persona and the frozen built HTML. Lookup mode permitted links and text search within that
corpus. Source checkout, Markdown guides, draft specs, Git and outside sites were prohibited.
Execution used the provided `.venv/bin/python`, isolated XDG_CACHE_HOME and temporary scratch
files; no network, models or shared stores. Installation was not tested.

Access routes and serving-model information below are reader-reported. The coordinator checked
cited documentation and reproduced examples, but did not independently audit a retained full
access trace; retrieval is unverified. Source exposure is stated separately rather than hidden.

## Dependency-familiar reader: custom value and configured step

Task `identity-baseline` completed. The reader followed Home → Cache → Fingerprints → Source.
It executed the original miss/hit example, the configured-step example and the value projection
example unchanged before creating its own `ObservedText` model and `Append` step. All application
runs passed on first execution. Artifacts were under `/tmp/triplum-identity-reader/`.

The adaptation reused results for equal text with different observation times and matching
suffix settings; changed suffix and changed text each computed. The reader correctly cited the
method/property boundary to conclude built-in Source could not be substituted directly. No
embedded source or generated API source was used, and no material task gaps were reported.
Python/Pydantic knowledge was assumed; choosing the model and configuration was the task.

## Senior integrator: custom codec and storage

Task `extension-baseline` completed using Home → Cache → generated cache API. The reader
reported GPT-6.1-sol. It ran the original example and then a stateless UTF-8 codec plus a locked
dictionary backend, with cold/repeated calls, flush and close. Output showed one computation,
one backend entry after flush and a background writer. Artifacts were under
`/tmp/triplum-extension-reader/`.

The initial generated-reference extraction included embedded source snippets. This baseline is
therefore source-exposed, even though the reader subsequently found the required contracts in
prose/signatures. It is not evidence of an entirely source-blind extension success. An initial
BeautifulSoup import failure was a reading-tool limitation; standard-library parsing replaced it
without changing application examples.

Verified findings:

| Finding | Impact | Disposition |
| --- | --- | --- |
| EXT-1: codec concurrency was implicit | Integration risk for stateful codecs | State that encode/decode run in caller threads and a shared codec must support concurrent calls |
| EXT-2: Cache constructor arguments absent from visible reference | Configuration required inference/source | Enable constructor signatures; verify pending_bytes and policy appear outside expandable source |
| EXT-3: no backend/codec extension walkthrough | Discovery friction | Add complete runnable extension pages linked from the cache parent |
| Owner/backend sharing unclear | Lifecycle ambiguity | Explain one owner closes its supplied backend; independent SQLite owners use separate backend instances |

The constructor setting follows
[mkdocstrings' documented merge_init_into_class option](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#merge_init_into_class).
Existing runtime behavior establishes codec concurrency and backend closure; no production
interface or behavior was changed to make the documentation true.

## Revision and retry

The parent cache guide now links six subpages: value fingerprints, computation fingerprints,
serialization, storage, ownership/write policy, and administration. Every extension page names
its contract and demonstrates current APIs. Identity redesign alternatives remain in an excluded
owner-review spec. The original fingerprint guide links the cache identity pages and retains
record/dataset and legacy object-helper distinctions.

Maintainer verification ran all nine initial Python blocks across the parent and subpages, supplying only
the explicitly documented context for two continuation fragments. Outputs matched. The CLI
walkthrough ran on its own temporary database. Strict MkDocs passed; constructor parameters were
confirmed in rendered text with expandable source removed. The full existing suite passed:
132 tests, 90% coverage; no application code changed.

A fresh senior-integrator retry uses `/tmp/triplum-identity-personae-retry`, with the same concrete
extension task and a request to avoid expandable source. Its result is recorded below before
completion. The dependency-familiar baseline had no material findings requiring a separate retry.

The fresh retry completed without task blockers or embedded-source access. It navigated the six
new pages, ran their complete examples unchanged, then combined a codec/backend with a 512-byte
owner budget and a per-step blocking override. Assertions verified one computation across
cold/repeated/post-flush calls, backend visibility, oversized blocking failure, owner skip count,
and backend close. It correctly explained Source incompatibility. The reader's exact serving
variant was not independently exposed; its self-report was Codex/GPT-6. Artifacts were in
`/tmp/triplum-extension-retry/`. No concurrency stress or crash-persistence claims follow.

The retry found one reference defect: CachePolicy rendered an empty constructor even though the
guide's on_full example worked. Maintainer inspection traced it to griffe_fieldz removing fields
before Griffe's dataclass synthesis. Keeping fields available fixed both CachePolicy and CacheKey
signatures; rendered text was checked with source sections excluded. This follows the
[documented dataclass signature generation](https://mkdocstrings.github.io/griffe/extensions/built-in/dataclasses/).
The strict build passed again. No further reader round is needed for this local rendering repair;
all material extension-task findings are resolved.


## Subsequent owner clarification

After the retry, the owner rejected mandatory manual version numbers. The published examples now
use semantic kind names without version counters. The configured-step example includes the
existing source_hash helper and selected configuration; the codec example uses normal function
inference. These examples were rerun by the maintainer, with identical observable output. The
reader evidence above concerns the prior frozen examples, not this subsequent authoring choice.
Documentation explicitly states source_hash's bounded scope and the current lack of automatic
external schema/codec discovery. A revised API proposal remains under review; no automatic
dependency-discovery guarantee was added.
