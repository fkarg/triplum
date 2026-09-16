# Dataset status

## Goal

Make `triplum data` show every dataset currently supported by the local HippoRAG protocol
adapter and whether its two required protocol artifacts are usable on this machine.

## Behaviour

- `triplum data` is read-only: it does not create directories, download files, or change cache
  state.
- It lists the registered datasets in `hipporag.FILES`: HotpotQA, MuSiQue, and 2WikiMultiHopQA.
- For each dataset, it reports one of four states after inspecting its question and corpus files
  below `$TRIPLUM_DATA/hipporag` (or the default data root):
  - `not downloaded`: neither file exists;
  - `partial`: exactly one file exists;
  - `verified`: both files exist and match their pinned SHA-256 hashes;
  - `invalid`: both files exist but either hash does not match.
- The command prints the data root and directs users to `triplum data fetch` when a dataset is not
  usable.
- It prints a brief state legend. In particular, `verified` means the **local** question and
  corpus files match their pinned SHA-256 hashes; it does not describe the remote download source.
- The legend explains that `fetch` downloads only missing artifacts, then verifies both files; it
  does not overwrite an existing invalid artifact.
- After the status rows it renders the normal Typer group help, including every available
  subcommand. This is generated from the group so future data commands do not require a second
  manually maintained list.
- `triplum data fetch` retains its existing behaviour.

## Boundaries

The dataset adapter owns availability inspection because it already owns the artifact names,
location and pinned hashes. The CLI only renders that result. The status check deliberately
reuses the existing hash verifier so a present-but-corrupt corpus is never reported as downloaded.

## Verification

Unit-test all four status outcomes with a temporary data root. Add a CLI workflow test proving
that invoking the bare `data` group renders the dataset list, generated subcommand help, and does
not fetch files. Update the command table and README command examples.
