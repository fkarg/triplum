import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    from triplum.bench.report import summary
    from triplum.bench.runstore import RunStore
    from triplum.cache import default_root

    return RunStore, default_root, mo, summary


@app.cell
def _(default_root, mo):
    path = mo.ui.text(value=str(default_root() / "runs.db"), label="run store")
    path
    return (path,)


@app.cell
def _(RunStore, path, summary):
    rs = RunStore(path.value)
    table = summary(rs)
    table
    return rs, table


@app.cell
def _(mo, table):
    pick = mo.ui.dropdown(options=table["run_id"].to_list() if table.height else [], label="run")
    pick
    return (pick,)


@app.cell
def _(pick, rs):
    rs.questions(pick.value) if pick.value else None


if __name__ == "__main__":
    app.run()
