"""Generate one API reference page per module under src/ plus a literate-nav SUMMARY.

Runs inside `mkdocs build`/`serve` via the gen-files plugin; the pages exist only in the build.
"""

from pathlib import Path

import mkdocs_gen_files

SRC = Path(__file__).parent.parent / "src"
# Prototypes under owner review; never publish them as working APIs (see AGENTS.md).
UNPUBLISHED = {("triplum", "datatype"), ("triplum", "steps")}

nav = mkdocs_gen_files.Nav()

for path in sorted(SRC.rglob("*.py")):
    parts = path.relative_to(SRC).with_suffix("").parts
    if parts[:2] in UNPUBLISHED or parts[-1] == "__main__":
        continue
    doc_path = Path(*parts).with_suffix(".md")
    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")

    nav[parts] = doc_path.as_posix()
    with mkdocs_gen_files.open(Path("api", doc_path), "w") as f:
        f.write(f"::: {'.'.join(parts)}\n")
    mkdocs_gen_files.set_edit_path(Path("api", doc_path), Path("..", path.relative_to(SRC.parent)))

with mkdocs_gen_files.open("api/SUMMARY.md", "w") as f:
    f.writelines(nav.build_literate_nav())
