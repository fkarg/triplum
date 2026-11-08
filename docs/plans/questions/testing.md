# Test-suite quality

Questions use the `TQ` prefix. Process: [questions index](README.md).

Owner (2026-11-08): line and branch coverage are easily gamed and only loosely correlated with
test quality; mutation coverage (which tests catch which code mutations) is the better measure.
Asked for options and the best effort/compute vs quality tradeoff, after extensive research.

## Research (web subagent with experiments in `/tmp`, 2026-11-08; scratch results do not travel)

- Tools: mutmut 3.8.1 (2026-10-28; Python 3.10–3.15) copies the tree to `mutants/`, replaces
  each function by a trampoline holding all mutants, forks per mutant, selects tests from a
  stats run, caches results by function source hash; no diff mode (function-name globs only).
  cosmic-ray 8.7.0 writes mutants to disk, runs the full test command per mutant, has a
  `git diff -U0` filter; officially up to 3.13, observed working on 3.14 (toy package).
  pytest-gremlins 1.13.2 (alpha) rewrites in memory via an import hook, ~20× slower per mutant
  here. MutPy, mutatest, poodle inactive. Meta's ACH (LLM-generated targeted mutants plus tests,
  73% of tests accepted by engineers) is internal only. cargo-mutants on `crates/`: 20 mutants
  in 4 s, none missed (observed).
- **Fingerprinting interaction (observed on a repo copy):** under mutmut, 30 of 508 tests fail
  with no mutant active (trampolines change the bytecode and source triplum fingerprints;
  `UnsupportedFingerprint: slice` from the wrapper's constants), runtime 34 s → 111 s; its stats
  phase stops on the first failure, so those tests must be deselected. Full run without them:
  4,456 mutants, 8 min on 12 workers; 3,072 killed, 1,249 survived (739 in tracing and
  fingerprint code), 62 timeouts, 73 uncovered. Of three survivors re-run on disk with the normal
  suite, two were killed: false survivors from the deselected tests and from a subprocess-based
  CLI test that the stats run cannot see. On-disk mutation keeps fingerprints faithful but runs
  the full suite per mutant (≈ 43 CPU-hours for all 4,456; ≈ 10 for a 1,000-mutant sample).
- Cost reduction: Google applies one mutant per changed, covered line, skips "arid" lines and
  shows survivors in code review (median mutants per change 820 → 7; 82% of surfaced mutants
  rated productive; mutants coupled to real bugs). A random sample of ~1,000 mutants estimates the
  score within ±7% (Gopinath et al. 2015). Diff-only runs miss effects elsewhere (3.5% of
  survivors later killed; cargo-mutants docs).
- Validity: coverage correlates only weakly with effectiveness once suite size is controlled
  (Inozemtseva & Holmes 2014); mutant detection correlates with real-fault detection beyond
  coverage (Just et al. 2014), though weakly when size is controlled; mutation-selected suites
  still find more faults (Papadakis et al. 2018). Redundant and equivalent mutants make the
  score imprecise: review survivors, do not gate on a percentage.
- Side finding: `utils.fingerprint._wrapped` unwraps `__wrapped__` only for `lru_cache`
  wrappers, not for plain functions, so a `functools.wraps` decorator's own code is what gets
  fingerprinted. Possibly intended (the wrapper is what runs); not checked.

## Open

Round 10, session assessment before peer:

- TQ1 (approach). Options: (a) mutmut first pass plus on-disk confirmation of survivors, scoped
  to changed functions, with a periodic full pass and a reviewed-survivor list (researcher's
  pick); (b) on-disk only (cosmic-ray git filter or a small own runner) with coverage-context
  test selection we build, faithful fingerprints, no deselect list; (c) targeted, agent-written
  mutants during review (ACH-style), which this session already does by hand; (d) combinations.
  Lean: (a) for now with a trial and its falsifiers, plus (c) as the review habit, since (b)
  means building and maintaining test selection ourselves.
- TQ2 (coverage in the required checks): coverage stays as a cheap hint or leaves CONTRIBUTING,
  CI and AGENTS.md. Lean: keep it as a report, drop it as a requirement in wording, because
  uncovered lines are still where mutants go untested.
- TQ3 (where it runs): a local script outside pre-commit and the normal pytest run, optional
  scheduled CI later. Lean: local script first; CI after the trial.
- TQ4 (Rust): `cargo mutants --in-diff` when `crates/` changes. Lean: yes, cheap.

Round 10 peer: gpt-6.1-sol, review `703b47b350fa425fb03035cc8029f044`, full JSON read (brief
only). Falsifications (desk checks): rescuing mutmut by excluding only fingerprint modules (fails:
subprocess tests stay invisible); hybrid confirmation as equivalent to full-suite testing (it
cannot catch wrongly "killed" mutants and adds a second runner); cosmic-ray's unofficial 3.14
support (made its pick conditional on a real pilot); retaining coverage against the owner's
criticism; diff-only blind spots; Rust cost generalisation.

- TQ1: **divergence, changed the session's lean.** Peer: on-disk mutation (cosmic-ray with its
  git-diff filter, full normal suite per mutant), gated on a real-repository Python 3.14 pilot;
  mutmut's score does not measure this suite. Session revised: one faithful runner without a
  deselect list is simpler than the hybrid, and a diff-scoped run (~50 mutants × ~35 s ≈ 3 min on
  12 cores) is affordable; mutmut stays optional for fast exploration outside the fingerprint
  and tracing modules. Wrapper tolerance in the fingerprinter, coverage-context test selection
  and property-based tests: only against a concrete pilot bottleneck or survivor.
- TQ2: **divergence.** Peer keeps line/branch coverage in the required checks (it still shows
  unexecuted code; no numeric gate exists). Session: keep it as a report, drop "required" from
  the wording.
- TQ3: agree: local script on an isolated copy first; manual CI later if useful; not in
  pre-commit or automatic PR checks.
- TQ4: agree, with peer adding PR CI when `crates/` changes; no score gate.
- Both: review survivors; record CPU time, elapsed time and review effort in the pilot; no
  score thresholds.

### Round 10 owner answers (2026-11-08)

- **Policy: mutation coverage is the measure of test-suite quality**, substantially better than
  line or branch coverage. Google's mutant rules (changed covered lines, skip arid lines, review
  survivors) apply generally. **Do not wait on CI**: keep checks local and non-blocking for now.
- Owner on the clean-run failures: surprising; investigate for learnings and potential bugs via a
  subagent. Parts of the caching may be excluded from mutation testing (function-based caching
  versus function mutation is a fair conflict). **Direction: code hashing should cover both a
  wrapper and the function it wraps** (today `_wrapped` unwraps only `lru_cache` wrappers);
  becomes a concrete proposal after the investigation.
- TQ1 (partial): **(b) on-disk mutation, but with a filtered test suite instead of the full
  one, if that is possible**; mutmut stays useful as a compromise. Follow-up TQ5: feasibility of
  per-mutant test selection for on-disk runs (coverage contexts, subprocess tests).
- TQ2 (answered): keep the coverage report as a zero-coverage indicator only; drop "required".
- TQ3 (deferred): until the mutmut vs cosmic-ray decision; for cosmic-ray, the local script on an
  isolated copy is agreed.
- TQ4 (closed): Rust is currently unused; no action.
- **Constraint (2026-11-08): no CPU-intensive runs for now** (owner is mobile); P10's pilot waits.

### TQ5 research: per-mutant test selection for on-disk mutation (subagent, 2026-11-08)

Toy experiments only (coverage 7.16.1, pytest-cov 7.1.0, Python 3.14); not run on the repo.

- Feasible with cosmic-ray (latest 8.8.0) plus a ~30-line distributor plugin: cosmic-ray passes no
  mutation location to the test command, but a distributor sees each work item's `module_path`,
  `start_pos` and `end_pos` and can run `pytest <nodeids>` for the tests covering those lines.
  Zero selected tests makes pytest exit 5, which cosmic-ray would count as killed: the plugin must
  record "no coverage" itself.
- Line → tests map from coverage contexts (`--cov-context=test`, `contexts_by_lineno`). Trap
  (observed): Python 3.14's default `sysmon` core records only the first test per line with
  dynamic contexts; `[run] core = ctrace` fixes it. Import-time lines (defs, decorators, module
  constants, defaults, class bodies) get the empty context: fall back to the full suite there.
- Subprocesses (CLI tests in six files): pytest-cov 7 dropped subprocess support; coverage's
  `[run] patch = subprocess` measures them but credits their lines to no test. Observed workaround:
  an autouse fixture sets the child's coverage context to the calling test via
  `COVERAGE_PROCESS_CONFIG` (relies on coverage internals that may change). Tests passing `env=`
  without `os.environ` stay unmeasured.
- mutmut's selection and pytest-testmon both miss subprocess dependencies (testmon documents it).
- Safety: every survivor is re-run against the full suite before it is reported (only survivors
  pay full cost), which bounds false survivors.
- Estimated cost (inferred): ~3 s fixed per mutant (collection, imports) plus selected tests and
  ~1 s per CLI subprocess: ~3–8 s versus ~35 s full suite. Unknown until one real coverage pass:
  tests per line, ctrace overhead, share of import-time mutants.

### Clean-run investigation (subagent, 2026-11-08; scratch under `/tmp/fpinv`, does not travel)

None of mutmut's 30 clean-run failures were stale hits: 24 were extra computations, 6 crashes.

- Cause A (24 tests, tool artifact, conservative): mutmut wraps `tracing._observe`, the
  `sys.monitoring` callback; its `sys._getframe(1)` then sees mutmut's frame, resolution fails and
  nothing is admitted. Observed: restoring the original callback makes 23 of 24 pass.
- Cause B (6 tests): two stacked triplum defects (below, 1 and 3); after patching the slice case
  the same tests fail on mutmut's `os.environ` read inside a walked wrapper (defect 2).
- Slowdown: no evidence of larger fingerprint graphs; trampolines cost ~2× on tiny functions; a
  one-off cold start of ~70 s is unexplained and may account for most of the reported 111 s.

**Defects affecting ordinary users (observed with plain Python reproductions):**

1. **High, stale results.** In a flat/script layout, a root computation that carries a
   third-party `functools.wraps` decorator moves the inferred application directory to the
   decorator's library (`_Definitions.directory` comes from the first code object's file), so
   sibling helpers are treated as external by name and editing them does not change identity:
   `h(x)=x+1` then `x+2` both return 11. Contradicts the spec's standalone-directory promise.
2. **Medium, loud failure.** Third-party `wraps` decorators are walked as application code
   because `__module__` is copied from the wrapped function; a wrapper reading `os.environ` or
   doing a local import makes static `@cached` raise. Contradicts "external functions stop at the
   qualified-name boundary".
3. **Medium-high, crash on valid 3.14 code.** Python 3.14 compiles literal slices (`text[1:]`)
   to a constant `slice`; `_constant` rejects it, so static `@cached` raises and traced mode never
   caches. `_constant` claims a lossless projection of compiler constants.

Not a defect: a `wraps`-decorated helper already hashes both wrapper and wrapped (the wrapped
function is reached through the wrapper's closure); editing the wrapped body changes identity.
Proposal sketch (wrapper and wrapped): classify functions by real origin
(`__globals__["__name__"]`, `__code__.co_filename`), never copied `__module__`; project a
`__wrapped__` function as `{wrapper: definition-or-external-name, wrapped: reference}`; derive
the application scope from the root after following `__wrapped__`, and a class's scope from its
module file; `_triplum_compute` and `lru_cache` handling unchanged; cycles end through existing
visited references. Optional: `_observe` checks `frame.f_code is code` and taints on mismatch.

Fix-proposal peer: gpt-6.1-sol, review `9f361d40c48c463387043948c6e95f8f` (thought experiments:
reversed ownership, decorator factory arguments, edited external wrapper body, wrappers that never
call `__wrapped__`, non-function and cyclic `__wrapped__`, mixed stacks). Dispositions:
- Unique defect in the sketch: deriving scope from the end of the `__wrapped__` chain makes an
  application wrapper around an external function external (its edits stop counting) → scope
  discovery needs its own rule; open question FP2.
- Unique defect: an external decorator factory (`factor * wrapped(x)`, factors 2 and 3) gives
  equal identities under name-only wrapper identity → stale hits unless captured arguments enter
  identity or admission declines; open question FP1, which also settles how "cover both" applies
  to external wrappers.
- Added verification: bounded scope discovery on `__wrapped__` cycles; defined handling of
  non-function `__wrapped__`; mixed stacks with `_triplum_compute` and `lru_cache`; slice tests for
  stability, omitted and negative bounds, each component, static and traced caching.
- Agreed: the slice fix is independent; the tracing frame guard stays out without a reproducer;
  fixing omitted dependencies may legitimately invalidate existing caches.

### Owner answers (2026-11-08, after the investigation)

- P11 (slice constants): **go**.
- FP1: **at least (b)**, captured values of external wrappers enter identity; **(c)** (hash the
  external wrapper's code too) if not too complicated. Owner asks what "external" means here:
  external to Python, to triplum, or to the application. Session to answer from the spec.
- FP2: direction agreed (scope from the outermost function whose source is outside installed
  packages and the standard library); skipping third-party decorators is right. Needs its own
  declaration and peer round.
- TQ1 (answered): **cosmic-ray with the per-mutant test-selection plugin**. TQ3 (cosmic-ray
  half) applies: local script on an isolated copy.
- CPU-heavy runs (P10 pilot, coverage map pass): later on the machine "jolly", not yet.

P11 done: `_constant` projects `slice` constants by start, stop and step; regression tests
(every component distinguishes, stable repeats, static and traced caching) fail before the fix
and pass after (observed); 512 tests pass.
