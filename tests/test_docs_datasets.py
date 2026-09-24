"""Every Python block on selected guide pages runs against the committed fixtures.

Each page runs as a module whose source is registered with `linecache`, the way a notebook cell
is, so functions defined on a page have a resolvable module and readable source."""

import linecache
import re
import sys
import types
from pathlib import Path

import pytest

DOCS = Path(__file__).parents[1] / "docs"


@pytest.mark.parametrize(
    "page", ["datasets.md", "guide/benchmark.md", "guide/variants.md", "guide/search.md"]
)
def test_page_examples_run(page):
    blocks = re.findall(r"```python\n(.*?)```", (DOCS / page).read_text(), re.DOTALL)
    assert blocks
    name = "docs_" + re.sub(r"\W", "_", page)
    filename = f"<{page}>"
    module = types.ModuleType(name)
    module.__file__ = filename
    sys.modules[name] = module
    try:
        for i, block in enumerate(blocks):
            # pad with the earlier blocks' lines so line numbers stay true for the whole page
            source = "\n" * sum(b.count("\n") for b in blocks[:i]) + block
            lines = source.splitlines(keepends=True)
            linecache.cache[filename] = (len(source), None, lines, filename)
            exec(compile(source, filename, "exec"), module.__dict__)  # noqa: S102 - repository-owned examples
    finally:
        sys.modules.pop(name, None)
        linecache.cache.pop(filename, None)
