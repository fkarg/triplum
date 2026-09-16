# Releasing

Releases go to PyPI from GitHub Actions with trusted publishing: no API token is stored
anywhere. The workflow is `.github/workflows/release.yml`.

## One-time setup (done in the PyPI and GitHub UIs)

1. On PyPI, add a *pending* trusted publisher for the project name `triplum` with owner
   `fkarg`, repository `triplum`, workflow `release.yml`, environment `pypi`. A pending publisher
   does not reserve the name; the first successful publish creates the project.
2. On GitHub, create the `pypi` environment for the repository. Restricting it to tags and to
   the repository owner is worth the two clicks.

## Cutting a release

1. Set the same version in `pyproject.toml` and the workspace `Cargo.toml`; commit.
2. Tag and push: `git tag v0.0.2 && git push origin v0.0.2`.
3. The workflow refuses a tag that does not match the `pyproject.toml` version, builds one abi3
   wheel per platform (Linux x86_64 and aarch64, macOS arm64 and x86_64) plus the sdist, smoke
   tests each wheel, and publishes with attestations. Watch it with
   `gh run watch` or on the Actions tab.

The extension targets the stable ABI for Python 3.12 and later, so one wheel per platform
covers every supported interpreter. Windows is not built; add a matrix row when someone
needs it. Installing from the sdist needs a Rust toolchain.
