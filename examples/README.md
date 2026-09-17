# Examples

Small, self-contained demonstrations. Each script runs as is with `uv run python examples/<name>.py`
and needs nothing but the committed fixtures and the fake adapters, so no model, key or download.
Every script here is executed by `tests/test_examples.py`.

| file | shows |
|---|---|
| `run_a_benchmark.py` | run one pipeline on a fixture, run it again and get the same run back, run three replicates and read the variance report |
| `your_own_data.py` | a benchmark from in-memory documents and questions, no registry |
| `stages.py` | two stages of your own under a run: fetch on the second call, recompute on a code or input change, the lineage of an artifact |
| `stages_notebook.py` | the same as a marimo notebook: `uv run marimo edit examples/stages_notebook.py` (for Jupyter: `uv run --with nbformat marimo export ipynb examples/stages_notebook.py -o stages.ipynb`) |

The tutorial pages go deeper: [`docs/datasets.md`](../docs/datasets.md) for sources and records,
[`docs/api/stage.md`](../docs/api/stage.md) for stages, [`docs/benchmarking.md`](../docs/benchmarking.md)
for identity and caching.

## marimo, and how it compares to Jupyter

The repository uses [marimo](https://docs.marimo.io) for notebooks (design record D9). It is
not a Jupyter fork; it is a different notebook model in the same role. Facts below are from the
marimo docs ([FAQ](https://docs.marimo.io/faq/),
[coming from Jupyter](https://docs.marimo.io/guides/coming_from/jupyter/)).

| | marimo | Jupyter |
|---|---|---|
| file format | plain `.py`, git-diffable, importable, runnable as a script; outputs are not stored | `.ipynb` JSON with outputs embedded |
| execution | reactive: cells form a dependency graph on the variables they define and read; running a cell reruns every cell that reads its variables; deleting a cell removes its variables | a REPL: cells run in whatever order you click, and state from deleted or edited cells lingers |
| consistency | code, outputs and program state always agree | out-of-order execution and hidden state are the usual reproducibility failure |
| constraints | a global name may be defined in only one cell (prefix temporaries with `_` to keep them cell-local); no `%magic` or `!shell` lines, use Python instead | none of those |
| running | `marimo edit` to develop, `marimo run` to serve as an app, `python notebook.py` as a script | `jupyter lab`, `nbconvert` |
| ecosystem | younger, smaller; marimo UI elements do not work inside Jupyter | everything |

Setup here is nothing beyond the dev environment: marimo is a dev dependency.

```
uv sync                                                   # once
uv run marimo edit examples/stages_notebook.py            # open in the browser, edit, rerun
uv run python examples/stages_notebook.py                 # run it top to bottom as a script
uv run marimo run examples/stages_notebook.py             # serve it as a read-only app
uv run marimo edit notebooks/new.py                       # start a new one
```

Moving between the two:

```
uv run --with nbformat marimo export ipynb examples/stages_notebook.py -o stages.ipynb   # to Jupyter
uv run marimo convert my_notebook.ipynb -o my_notebook.py                                 # from Jupyter
```

If you would rather stay in Jupyter, every script in this folder is plain Python and pastes into
a cell as it is; only the marimo notebook file is marimo-specific.
