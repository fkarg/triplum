"""Dirty builds must retain links to API pages that were not rendered again."""

import os
from pathlib import Path

import pytest
from mkdocs.commands.build import build
from mkdocs.config import load_config
from mkdocstrings import Inventory

ROOT = Path(__file__).resolve().parents[1]


def test_dirty_build_retains_api_links_without_rendering_unchanged_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fresh plugin instances previously forgot targets from unchanged API pages.
    docs = tmp_path / "docs"
    docs.mkdir()
    source = tmp_path / "src"
    package = source / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('from .__main__ import Hidden\n__all__ = ["Hidden"]\n')
    (package / "__main__.py").write_text('class Hidden:\n    """An alias target."""\n')
    module = package / "models.py"
    module.write_text('class Widget:\n    """A widget."""\n')
    guide = docs / "index.md"
    guide.write_text(
        "# Guide\n\nA [`Widget`][sample.models.Widget].\n\nAn [`alias`][sample.__main__.Hidden].\n"
    )
    site = tmp_path / "site"
    api_html = site / "api/sample/models/index.html"
    first_mtime = None
    for iteration in range(3):
        config = load_config(
            str(ROOT / "mkdocs.yml"),
            docs_dir=str(docs),
            site_dir=str(site),
            nav=[{"Home": "index.md"}, {"API reference": []}],
        )
        monkeypatch.setattr(config.plugins["scripts/api_reference.py"], "SRC", source)
        config.plugins["mkdocstrings"].config.handlers["python"]["paths"] = [str(source)]
        if iteration == 0:
            config.plugins.on_startup(command="serve", dirty=True)
        else:
            guide.write_text(guide.read_text() + f"\nEdit {iteration}.\n")
            # Explicitly make the guide newer, even on low-resolution filesystems.
            html_mtime = (site / "index.html").stat().st_mtime
            os.utime(guide, (html_mtime + 1, html_mtime + 1))
        build(config, dirty=True)
        html = (site / "index.html").read_text()
        assert 'href="api/sample/models/#sample.models.Widget"' in html
        assert "[sample.models.Widget]" not in html
        assert 'href="api/sample/#sample.Hidden"' in html
        if first_mtime is None:
            first_mtime = api_html.stat().st_mtime_ns
        else:
            assert api_html.stat().st_mtime_ns == first_mtime

    # Replacing a definition must not resurrect its old anchor from the inventory.
    module.write_text('class Replacement:\n    """A [hidden target][sample.__main__.Hidden]."""\n')
    assert first_mtime is not None
    modified = first_mtime / 1_000_000_000 + 1
    os.utime(module, (modified, modified))
    guide.write_text("# Guide\n\n[`Replacement`][sample.models.Replacement].\n")
    modified = (site / "index.html").stat().st_mtime + 1
    os.utime(guide, (modified, modified))
    config = load_config(
        str(ROOT / "mkdocs.yml"),
        docs_dir=str(docs),
        site_dir=str(site),
        nav=[{"Home": "index.md"}, {"API reference": []}],
    )
    config.plugins["mkdocstrings"].config.handlers["python"]["paths"] = [str(source)]
    build(config, dirty=True)
    assert (
        'href="api/sample/models/#sample.models.Replacement"' in (site / "index.html").read_text()
    )
    with (site / "objects.inv").open("rb") as inventory_file:
        inventory = Inventory.parse_sphinx(inventory_file)
    assert 'href="../#sample.Hidden"' in api_html.read_text()
    assert "sample.models.Widget" not in inventory
    assert "sample.models.Replacement" in inventory
    # After one module was regenerated, its peers must survive another inventory round trip.
    modified = api_html.stat().st_mtime - 1
    os.utime(module, (modified, modified))
    guide.write_text("# Guide\n\n[`Alias`][sample.__main__.Hidden].\n")
    modified = (site / "index.html").stat().st_mtime + 1
    os.utime(guide, (modified, modified))
    config = load_config(
        str(ROOT / "mkdocs.yml"),
        docs_dir=str(docs),
        site_dir=str(site),
        nav=[{"Home": "index.md"}, {"API reference": []}],
    )
    config.plugins["mkdocstrings"].config.handlers["python"]["paths"] = [str(source)]
    build(config, dirty=True)
    assert 'href="api/sample/#sample.Hidden"' in (site / "index.html").read_text()
    config.plugins.on_shutdown()
