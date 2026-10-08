"""MkDocs hook: one API reference page per module under src/, listed under "API reference".

Pages exist only in the build. Under `mkdocs serve --dirty`, a page is re-rendered only when its
own module is newer than the built HTML, so editing one module does not re-render the others.
Pages that show members defined elsewhere (re-exports, inherited members) can lag until the next
full build.
"""

import os
from pathlib import Path

from jinja2 import Environment
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import event_priority
from mkdocs.structure.files import File, Files
from mkdocs_autorefs import AutorefsPlugin
from mkdocstrings import Inventory, MkdocstringsPlugin

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


@event_priority(0)
def on_env(env: Environment, *, config: MkDocsConfig, files: Files) -> Environment:
    """Restore object links for skipped API pages before inventory writing and resolution.

    Dirty builds create new plugin instances, but do not render unchanged module pages.
    Their public object inventory survives on disk; use it only for pages still served
    unchanged. Freshly rendered targets take precedence over these fallback URLs.
    """
    skipped = {
        file.page.url
        for file in files
        if isinstance(file, ModulePage) and file.page is not None and file.page.content is None
    }
    inventory_path = Path(config.site_dir) / "objects.inv"
    if not skipped or not inventory_path.is_file():
        return env
    with inventory_path.open("rb") as stream:
        previous = Inventory.parse_sphinx(stream)
    autorefs = config.plugins["autorefs"]
    mkdocstrings = config.plugins["mkdocstrings"]
    assert isinstance(autorefs, AutorefsPlugin)
    assert isinstance(mkdocstrings, MkdocstringsPlugin)
    inventory = mkdocstrings.handlers.inventory
    for name, item in previous.items():
        if item.uri.partition("#")[0] in skipped:
            autorefs.register_url(name, item.uri)
            inventory.setdefault(name, item)
    return env
