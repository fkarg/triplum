"""Every example script runs to completion, offline, in its own process."""

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parents[1] / "examples"


@pytest.mark.parametrize("script", sorted(p.name for p in EXAMPLES.glob("*.py")))
def test_example_runs(script):
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / script)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
