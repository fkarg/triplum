# Cache documentation reader trial

Input: built site from main at 3911751 plus the working documentation revision. This is a
synthetic reader trial, not a measurement of human comprehension or browser/search usability.

## Task and evidence

One fresh-context newcomer reader started at Home, followed the cache-guide link and then
Fingerprints. Its allowed corpus was /tmp/triplum-docs-review-site; source and development
records were excluded. It reported no generated-source/API lookup. Access mode was local HTML
navigation; the route is agent-reported, not independently audited from a retained access trace.

The task was to run the miss/hit/changed-input/original-input example, explain Source compatibility
and computation revision responsibilities, and distinguish the two cache classes then present.
It extracted the complete example unchanged into a temporary Python file and ran it with the
provided virtual environment and isolated XDG_CACHE_HOME. Output matched:
Computing, hello, hello, Computing, world, hello. It cited the cache identity section and
Fingerprints' record-properties section to correctly explain the property/method mismatch and
explicit revision responsibilities. No task blockers were reported. Installation was not tested.
An unavailable BeautifulSoup dependency in its reading helper was replaced with the standard
library HTML parser; it was not a documentation failure.

The legacy-class answer described the frozen input correctly. The owner subsequently requested
removal of that class, so it does not validate the final removal note. Maintainer verification
covers that cleanup and the final strict build. No unchanged reader task requires another round.

## Maintainer and peer findings

- Fixed: Source examples incorrectly supplied Path instead of str; local MarkdownFolder display
  disagreed with absolute origins; store portability and filtering guarantees were overstated.
- Fixed: mixed fingerprint concepts, brittle literal digest output, missing CachedStep example,
  implicit continuation blocks, late source-file requirement, and dense introductory lifecycle prose.
- Added: download-free batching example, key-change decision table, explicit type restrictions,
  and computation fingerprint mapping to process_id / CacheKey.process / CLI --computation.
- Preserved: one cache page and existing navigation; no new documentation taxonomy or API.

Claude Opus 5.5 (claude-opus-5-5), review 3be43288979a4d1baddcff1757c5493b, independently ran
blocks, tried stdin execution, Source caching, generic Fingerprinted with CachedStep, Path defaults
and lambdas, checked CLI behavior and traced legacy callers. Its review added the incompatible
mixin/default-type explanation, consistent terminology and moving lifecycle details later.
Its preference to retain the old class was rejected by the owner's explicit removal instruction.
A fresh local audit independently found the invalid Source example. One initial chunking-output
finding was retracted after execution showed the existing output was correct; no change was made.

External research favored concrete first/repeated/changed calls and incremental improvement:
[Joblib's guide](https://joblib.readthedocs.io/en/stable/user_guide/memory.html),
[Diátaxis tutorials](https://diataxis.fr/tutorials/), and
[incremental application](https://www.diataxis.fr/how-to-use-diataxis/).
Those informed teaching order, not cache contracts. A separate operations page was deferred:
local headings suffice without changing navigation.

## Verification

Maintainers ran cache, mixin, identity, dataset, chunk and store examples from temporary files
or isolated directories. The strict build and repository checks are recorded with the commit
and task report. Benchmark downloads were not rerun; no retrieval pipeline was added or implied.
