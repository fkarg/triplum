import json
import subprocess
import sys
from pathlib import Path


def test_pipeline_demo_reuses_values_across_upstream_processes_and_reopen() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "cached_pipeline.py"
    result = subprocess.run(
        [sys.executable, str(example)], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == {
        "lowercase_computations": 2,
        "casefold_computations": 1,
        "analysis_computations": 2,
        "reopened_analysis_computations": 0,
    }
