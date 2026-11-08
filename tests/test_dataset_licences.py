import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from mkdocs.exceptions import PluginError

from triplum.datasets.catalogue import CATALOGUE

_spec = importlib.util.spec_from_file_location(
    "dataset_licences", Path(__file__).resolve().parents[1] / "scripts" / "dataset_licences.py"
)
assert _spec and _spec.loader
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


def _page(src_uri: str):
    return SimpleNamespace(file=SimpleNamespace(src_uri=src_uri))


def test_the_licences_page_gets_one_row_per_catalogued_dataset():
    rendered = hook.on_page_markdown(f"before\n{hook.MARKER}\nafter", _page("licences.md"))
    rows = [line for line in rendered.splitlines() if line.startswith("| ") and "---" not in line]
    assert rows[1:] == [
        f"| {e.name} | `triplum.datasets.{e.name}` | {e.licence} | {e.commercial_reuse} |"
        for e in CATALOGUE.values()
    ]
    assert rendered.startswith("before\n") and rendered.endswith("\nafter")


def test_the_checked_in_licences_page_has_the_marker():
    page = Path(__file__).resolve().parents[1] / "docs" / "licences.md"
    assert hook.MARKER in page.read_text()


def test_a_missing_marker_fails_the_build_and_other_pages_are_untouched():
    with pytest.raises(PluginError, match="lacks the marker"):
        hook.on_page_markdown("no marker", _page("licences.md"))
    assert hook.on_page_markdown(hook.MARKER, _page("index.md")) == hook.MARKER
