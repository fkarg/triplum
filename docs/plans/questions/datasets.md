# Dataset downloads and management

Questions use the `DS` prefix. Process: [questions index](README.md). Contract target:
[command line](../specs/cli-selection.md) (datasets and models).

Settled (owner, 2026-11-07): provided datasets live in the triplum cache folder
(`cache_home()/datasets`, beside `cache.sqlite`) and download automatically when missing.
Implemented for HotpotQA and MultiHop-RAG: pinned URL and sha256 per file, verified on every
construction, per-call temporary file then rename.

Research (web subagent, primary sources, 2026-11-07): HF hub, torch.hub and pooch keep downloads
under the XDG cache and fetch implicitly; torchvision, NLTK and spaCy need an explicit step. HF
does not re-hash on load (`hf cache verify` on demand); pooch hashes on every fetch. HF writes
`CACHEDIR.TAG`; `HF_HUB_OFFLINE` turns downloads into errors. CLIs: `hf cache ls|rm|prune|verify`
(`--dry-run`, `--yes`, `--format json`), `ir_datasets list|clean --list`. Lessons: partial files,
races (filelock unreliable on network filesystems), upstream changes breaking hashes, TLS
problems, disk-usage surprises.

## Open

Round 9, session assessment before peer:

- DS1 (registry): how the CLI finds datasets, their files and licence terms. Lean: one small
  `datasets/registry.py` tuple of entries for implemented datasets only (name, files, licence,
  commercial-reuse note), built from each module's constants; the unreferenced 30-entry
  `manifest.json` stays unused (no restoring deleted loaders). A test checks each entry has a
  `docs/licences.md` row.
- DS2 (commands): `triplum datasets list | download | verify | remove | info`, following the
  cache command conventions (forgiving names, `--json`, `--no-input`, stderr diagnostics, no
  prompt for removing re-downloadable files). Status computed from disk, nothing recorded.
- DS3 (verification on load): keep the full sha256 check on every construction (files up to
  ~15 MB so far) rather than HF-style existence checks.
- DS4 (offline and location overrides): no new environment variables now; `XDG_CACHE_HOME` and
  `root=` suffice, and a failed download names `triplum datasets download`.

Round 9 peer: gpt-6.1-sol, review `733af46e43dd4ffc9f0d7bbdb4c29000`, full JSON read (brief only).
Falsifications: all 30 manifest entries as datasets; same-length corruption; HotpotQA interrupted
after one file; offline construction outside the CLI; offline download with valid files; remove
under a root with unrelated files; verify on a corrupt file; stale verified badge; concurrent
downloads; CLI licence prose diverging from docs/licences.md.

- DS1: agrees on a small catalogue of implemented datasets only. **Divergence**: peer makes the
  catalogue the one home of file metadata (module constants move into it) and renders its dataset
  licence terms into `docs/licences.md`; Claude keeps constants in modules and tests that each
  entry has a licences.md row. Peer deletes the unreferenced `manifest.json` (history in Git);
  Claude leaves it unused.
- DS2: agrees on a `datasets` command group with cache-command conventions and no prompt. Peer
  adds: `licence` instead of `info`; one dataset name per command; `list` reports missing /
  partial / present without hashing, never "verified"; `download` fails on an existing corrupt
  file (recovery: remove, then download) instead of silently replacing it; `verify` reports all
  missing or mismatched files and never repairs; `remove` deletes only declared files.
- DS3: agrees: keep the full sha256 check on every construction until a measurement says
  otherwise.
- DS4: **divergence**: peer adds `TRIPLUM_OFFLINE=1`, `offline=True` and `--offline` so library
  constructors also refuse network fetches, plus `--root`; Claude adds no environment variables.
  Peer: failures name dataset, file, destination, cause and next step (TLS: mention
  `SSL_CERT_FILE`, never disable verification).
