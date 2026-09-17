"""Every Python block on the datasets page runs, in order, against the committed fixtures."""

import re
from pathlib import Path

PAGE = Path(__file__).parents[1] / "docs" / "datasets.md"


def test_datasets_page_examples_run():
    blocks = re.findall(r"```python\n(.*?)```", PAGE.read_text(), re.DOTALL)
    assert len(blocks) >= 5
    namespace: dict = {}
    for i, block in enumerate(blocks):
        exec(compile(block, f"docs/datasets.md#{i}", "exec"), namespace)  # noqa: S102 - repository-owned examples
