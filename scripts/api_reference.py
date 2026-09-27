"""MkDocs hook: one API reference page per module under src/, listed under "API reference".

Pages exist only in the build. Under `mkdocs serve --dirty`, a page is re-rendered only when its
own module is newer than the built HTML, so editing one module does not re-render the others.
Pages that show members defined elsewhere (re-exports, inherited members) can lag until the next
full build.
"""

import os
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files

SRC = Path(__file__).parent.parent / "src"


class ModulePage(File):
    module: Path

    def is_modified(self) -> bool:
        dest = self.abs_dest_path
        return not os.path.isfile(dest) or os.path.getmtime(dest) < self.module.stat().st_mtime


def _modules() -> dict[str, Path]:
    """Dotted module name -> source file, packages included via their `__init__.py`."""
    modules = {}
    for path in sorted(SRC.rglob("*.py")):
        parts = path.relative_to(SRC).with_suffix("").parts
        if parts[-1] == "__main__":
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules[".".join(parts)] = path
    return modules


def _uri(name: str) -> str:
    return f"api/{name.replace('.', '/')}.md"


def _nav(tree: dict, prefix: str, modules: dict[str, Path]) -> list:
    """Nested nav: each package is a section led by its own page, then its submodules."""
    entries = []
    for part, children in tree.items():
        name = prefix + part
        page = [{part: _uri(name)}] if name in modules else []
        if children:
            entries.append({part: page + _nav(children, name + ".", modules)})
        else:
            entries.extend(page)
    return entries


def on_config(config: MkDocsConfig) -> None:
    modules = _modules()
    tree: dict = {}
    for name in modules:
        node = tree
        for part in name.split("."):
            node = node.setdefault(part, {})
    for item in config.nav or []:
        if isinstance(item, dict) and "API reference" in item:
            item["API reference"] = _nav(tree, "", modules)


def on_files(files: Files, config: MkDocsConfig) -> None:
    for name, path in _modules().items():
        page = ModulePage.generated(config, _uri(name), content=f"::: {name}\n")
        assert isinstance(page, ModulePage)
        page.module = path
        files.append(page)
