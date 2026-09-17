# Releasing

Releases go to PyPI from GitHub Actions with trusted publishing: no API token is stored
anywhere. The workflow is `.github/workflows/release.yml`.

## One-time setup (done in the PyPI and GitHub UIs)

1. On PyPI, add a *pending* trusted publisher for the project name `triplum` with owner
   `fkarg`, repository `triplum`, workflow `release.yml`, environment `pypi`. A pending publisher
   does not reserve the name; the first successful publish creates the project.
2. On GitHub, the `pypi` environment is created automatically the first time the workflow
   references it (this happened with v0.0.1). Restricting it to tags and to the repository
   owner in the repository settings is worth the two clicks but not required.

## Cutting a release

1. Set the same version in `pyproject.toml` and the workspace `Cargo.toml`; commit. The Python
   package reads its version from the installed metadata, so there is no third copy.
2. Tag and push: `git tag v0.0.2 && git push origin v0.0.2`.
3. The workflow refuses a tag that does not match the `pyproject.toml` version, builds one abi3
   wheel per platform (Linux x86_64 and aarch64, macOS arm64) plus the sdist, smoke
   tests each wheel, and publishes with attestations. Watch it with
   `gh run watch` or on the Actions tab.

If the publish step fails halfway (v0.0.1 did: PyPI accepted the wheels and rejected the
sdist), fix the cause, bump the version and tag again; a PyPI version cannot be reused. The
publish step passes `skip-existing`, so a re-run of the same tag only adds missing files.

The extension targets the stable ABI for Python 3.12 and later, so one wheel per platform
covers every supported interpreter. Windows is not built; add a matrix row when someone
needs it. Installing from the sdist needs a Rust toolchain.
