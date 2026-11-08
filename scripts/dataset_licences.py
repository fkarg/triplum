"""MkDocs hook: render the dataset rows of the licences page from the dataset catalogue.

The catalogue entries are the one record of dataset terms; `docs/licences.md` holds only a
marker where the generated table goes.
"""

from mkdocs.exceptions import PluginError
from mkdocs.structure.pages import Page

from triplum.datasets.catalogue import CATALOGUE

MARKER = "<!-- dataset licences: generated from triplum.datasets.catalogue -->"


def table() -> str:
    """One Markdown row per catalogued dataset: name, module, licence, commercial reuse."""
    rows = [
        "| Dataset | Loader | Licence | Commercial reuse |",
        "| --- | --- | --- | --- |",
        *(
            f"| {e.name} | `triplum.datasets.{e.name}` | {e.licence} | {e.commercial_reuse} |"
            for e in CATALOGUE.values()
        ),
    ]
    return "\n".join(rows)


def on_page_markdown(markdown: str, page: Page, **kwargs: object) -> str:
    if page.file.src_uri != "licences.md":
        return markdown
    if MARKER not in markdown:
        raise PluginError(f"licences.md lacks the marker {MARKER!r}")
    return markdown.replace(MARKER, table())
