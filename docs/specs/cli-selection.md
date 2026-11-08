# Command-line contract

The command line is the operator interface for repetitive tasks; see [Goals](../goals.md). Each
command is a thin layer over importable library functions. Pipelines are composed in Python, not
configured through command-line options, and no step runs as its own command.

## Scope

Implemented: cache management and dataset utilities (below). Owner-agreed but not yet specified or built; each needs
its own contract here before implementation:

- Datasets and models: datasets download automatically on first use; the CLI shows download
  status and offers some management (list, download ahead of use, verify, remove, show recorded
  licence terms including commercial-reuse implications). The same applies to model weights
  (embedders, rerankers, local LLMs). Dataset utilities are specified and implemented below;
  model weights are not.
  Owner (2026-11-07): provided datasets use the same cache as computations and download
  automatically when missing. Implemented: `utils.paths.cache_home()` (`$XDG_CACHE_HOME/triplum`)
  holds `cache.sqlite` and `datasets/`; `datasets.files.fetch` downloads pinned files into a
  per-call temporary file, verifies sha256, then renames.
- Benchmark runs: launch a Python pipeline factory in benchmark mode (no cache reads or writes,
  seeded replicates, recorded run identity) with operator options only: seed, replicate count,
  dataset, output location. Depends on the unbuilt benchmark runner and run identity.
- Results: list, show and compare recorded runs as a table of EM, F1, Contain-Acc, Judge-Acc,
  R@2, R@5 and cost across runs and baselines, including replicate variance. Read-only over the
  run store; depends on benchmark runs.
- Stores: counts per record type, a source with its chunks, and ad-hoc search for checking an
  index by eye. Depends on the index/retrieval interfaces and on Viewer (search takes a viewer).
- Environment check: required keys set (never printed), dataset/model/cache locations reachable
  and writable, network/TLS working. Motivating case: uv-managed Python on NixOS failed TLS
  verification for the MultiHop-RAG download until `SSL_CERT_FILE` was set.

## Cache utilities

The owner authorized per-computation tables and cache utility commands. This re-establishes command
selection for these utilities, not the historical CLI or benchmark runner.

```text
triplum cache stats [--path PATH] [--computation SHA256 | --name NAME] [--details] [--json] [--no-input]
triplum cache clear [--path PATH] [--computation SHA256 | --name NAME] [--json] [--no-input]
```

- Use the default cache path unless --path is given. Inspection must not create/open a writable
  database, start a writer or create directories. Missing caches report empty/missing.
- Finite command names match exact, then unique prefix, substring or close typo. Ambiguities list
  choices; missing commands show usage/choices. Paths and full SHA-256 identities remain exact.
  A selector resolved by anything but an exact match reports its resolution on stderr
  (for example `cache c → cache clear`), so destructive commands never act on a silent guess.
- stats reports committed computation tables, database/WAL file sizes and reusable SQLite pages.
  --details opts into scans for exact entry counts and serialized payload bytes. Runtime counters
  and other owners' pending writes are not visible to this process.
- clear drops all cache computation tables, or the exact selected computation table. The command
  explicitly authorizes recomputable-data deletion: no prompt, on terminals or otherwise.
  --no-input is accepted. Clear does not unlink an open database or run VACUUM.
- Clearing is transactional and point-in-time. Writers may recreate tables with later commits.
  Freed pages become reusable; the file need not shrink. Unrecognized tables, including the former
  cache_entries table, remain untouched; there is no migration or legacy cleanup.
- Human output is concise; --json produces structured stdout. Errors/diagnostics go to stderr
  without tracebacks. Plain text is the baseline so NO_COLOR requires no special handling.
- --name selects recorded function names across computation fingerprints with the same forgiving
  matching as commands. The resolved names are reported on stderr and included in --json output.
- Commands wrap importable cache_stats(path, ...) and clear_cache(path, ...).

## Dataset utilities

Status: **approved** by the owner (2026-11-08) and implemented: `datasets/files.py` (`PinnedFile`,
`DatasetEntry`, `fetch`, `download`), `datasets/catalogue.py`, `datasets/admin.py`, the `datasets`
commands in `cli.py`, and `scripts/dataset_licences.py`, which renders the dataset rows of
`docs/licences.md` from the catalogue (owner: one source of truth, generated).

Settled in round 9 ([questions](../plans/questions/datasets.md)): DS2 commands with the peer's
additions and a prompt above 5 GB, DS3 hash on every construction, DS4 no offline mode, DS1
direction (dataset modules with their constants, a small catalogue now, the full manifest list
later).

Catalogue (proposal, following scikit-learn's per-fetcher `RemoteFileMetadata` and torchvision's
explicit dataset list; research in the questions file):

```python
# src/triplum/datasets/files.py
class PinnedFile(BaseModel):  # frozen
    name: str  # path inside the dataset's folder
    url: str
    sha256: str
    bytes: int  # recorded for every file; list shows it as the expected size


class DatasetEntry(BaseModel):  # frozen
    name: str  # catalogue key and folder name under datasets_home()
    files: list[PinnedFile]
    licence: str  # the recorded terms, e.g. "CC BY-SA 4.0 (HippoRAG files MIT)"
    commercial_reuse: str  # implications, as in docs/licences.md


def download(entry: DatasetEntry, root: Path | None = None) -> Path: ...  # the entry's folder


# src/triplum/datasets/hotpotqa.py (likewise multihoprag.py)
ENTRY = DatasetEntry(name="hotpotqa", files=[...], licence=..., commercial_reuse=...)

# src/triplum/datasets/catalogue.py
CATALOGUE: dict[str, DatasetEntry] = {e.name: e for e in (hotpotqa.ENTRY, multihoprag.ENTRY)}
```

- Each dataset module keeps its own entry beside its parser; the catalogue is the explicit list
  the CLI iterates. The licences page's dataset rows are generated from the entries at build
  time; the page keeps only a marker, and a missing marker fails the build.
- Per-module `download()` functions become `download(ENTRY, root)`. Shared parsers for format
  families wait until more loaders exist; `manifest.json` stays, unused, until the full list.

```text
triplum datasets list [--json] [--no-input]
triplum datasets download NAME [--json] [--no-input]
triplum datasets verify NAME [--json] [--no-input]
triplum datasets remove NAME [--yes] [--json] [--no-input]
triplum datasets licence NAME [--json] [--no-input]
```

- Location: `datasets_home()` (`$XDG_CACHE_HOME/triplum/datasets`); no `--root` and no offline
  mode. Commands wrap importable library functions, as the cache commands do.
- Names: the catalogue's dataset names, matched like command names (exact, unique prefix,
  substring, close typo); a resolution other than exact is reported on stderr; ambiguity lists
  the choices and does nothing. One dataset per command.
- list: every catalogued dataset with status `missing` (no expected file), `partial` (some) or
  `present` (all), per-file sizes on disk and expected sizes. It never downloads
  or hashes, so `present` does not mean verified. Unreadable files are errors, not `missing`.
- download: what constructors do on first use, file by file in catalogue order: a verified file is
  kept, a missing one is fetched into a per-call temporary file, verified, then renamed into place.
  Files installed before a failure stay; the first failure stops the command. An existing file
  whose hash does not match fails with expected and actual digests, **in constructors too**
  (today `fetch` silently re-downloads it; this changes), and is left untouched; recovery is
  `remove`, then `download`.
- verify: hashes every expected file, continuing past failures, and reports each missing,
  mismatched or unreadable one; nonzero exit if any. It never downloads or repairs. Hashing reads
  in bounded chunks.
- remove: deletes only the dataset's declared files and its folder if then empty; missing files
  succeed. Re-downloadable data needs no prompt, except **above 5 GB**: the sum of the actual
  sizes of the declared files present, compared as `> 5_000_000_000` bytes. On a terminal it asks;
  `--yes` skips the question; without a terminal or with `--no-input` and no `--yes` it refuses
  with guidance. `cache.sqlite` and unrelated files are untouched. Remove is not cancellation: a
  download running at the same time may reinstall files afterwards, and its temporary file can
  keep the folder from being removed.
- licence: the recorded terms and commercial-reuse implications, without downloading; unknown
  implications are shown as unknown.
- Paths: a declared file is a plain name inside the dataset's folder (no subfolders). A directory,
  broken link or other non-file at its path is an error, not `missing`.
- Guarantees cover installing each downloaded file (never a partial or unverified file under its
  name); they do not make a multi-file dataset atomic or keep a file in place against a
  concurrent `remove`.
- Output follows the cache commands: concise human text, `--json` structured stdout, diagnostics
  and resolutions on stderr, no tracebacks, nonzero exit on failure. Download failures name the
  dataset, file, destination and cause; TLS failures mention `SSL_CERT_FILE` and never suggest
  disabling verification.

### Implementation review (dataset utilities)

- Cross-model diff review gpt-6.1-sol `861532b54aee45408c54444387c602e8` (traversal in a
  disposable folder, permission-denied files and folders, malformed HTTP over loopback, injected
  connection resets, hashing and empty-catalogue mutations). Unique defects, all fixed with tests:
  `../` file names escaped the dataset folder; unreadable files read as present and unreadable
  folders as missing; protocol errors escaped as tracebacks; download errors lacked file and
  destination; human `list` lacked per-file sizes; the HippoRAG licence-text obligation was
  dropped in migration. Added verification: the status test fails if status hashes; the catalogue
  test fails on empty file lists. Nits applied (unreachable return, inlined helper).
- General reviewer (its peer gpt-6.1-sol, same findings independently, plus cache-command parity
  against HEAD in 8 cases): no must-fix in the final code. Applied: dataset names validated like
  file names; licence and commercial-reuse terms must be non-empty ("unknown" recorded
  explicitly); hash-mismatch downloads name the destination; a TLS-hint test; `remove` tolerates a
  concurrent download's temporary file (`ENOTEMPTY`) and needs no read permission, so an
  unreadable corrupt file can be removed; downloads time out after 60 s without data. Not
  changed: argparse prints its usage block before every error, as the cache commands always have
  (owner decision pending); the licence table assumes module name = dataset name and no `|` in
  terms.
