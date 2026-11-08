"""Mutation testing on an isolated copy: cosmic-ray mutants, per-mutant test selection.

Run with ``uv run --group mutation python scripts/mutation.py [--diff REF]``.

1. Copy the working tree (tracked and untracked, not ignored) into ``--out``, once per worker.
2. Generate mutants with cosmic-ray; skip arid ones (inside annotations) and, with ``--diff``,
   those outside the lines changed since REF.
3. Run the suite once under coverage with per-test contexts, subprocesses included, to map each
   line to the tests that execute it. The run must pass.
4. Per mutant, run only the tests covering its lines. Mutants on import-time lines run the full
   suite; mutants on statements no test executes are reported as uncovered without a run.
   Every survivor of a selected run is re-run against the full suite before it is reported, so
   selection can cost time but cannot invent survivors.

Results: ``results.jsonl`` (one line per mutant), ``survivors.md`` and cosmic-ray's
``session.sqlite`` (for ``cr-report``/``cr-html``) in ``--out``. Mutants are not a score to
gate on: review the survivors.
"""

import argparse
import ast
import contextlib
import json
import os
import queue
import random
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import coverage
from cosmic_ray.commands import init
from cosmic_ray.modules import find_modules
from cosmic_ray.mutating import _make_diff, use_mutation
from cosmic_ray.plugins import get_operator
from cosmic_ray.work_db import WorkDB, use_db
from cosmic_ray.work_item import MutationSpec, TestOutcome, WorkerOutcome, WorkResult

REPO = Path(__file__).resolve().parent.parent
PACKAGE = Path("src/triplum")
PYTEST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
COVERAGE_RC = """\
[run]
source = {package}
core = ctrace
patch = subprocess, _exit
parallel = true
data_file = {data}
context = ${{TRIPLUM_MUTATION_CONTEXT}}
"""
Lines = dict[tuple[str, int], set[str]]


def copy_tree(destination: Path) -> None:
    """Copy tracked and untracked, non-ignored files of the working tree."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "-co", "--exclude-standard"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    for name in filter(None, listing.decode().split("\0")):
        source = REPO / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def environment(tree: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_")}
    env.update(
        PYTHONPATH=os.pathsep.join([str(tree / "src"), str(REPO / "scripts")]),
        PYTHONDONTWRITEBYTECODE="1",  # a same-size mutant in the same second could hit a stale pyc
        XDG_CACHE_HOME=str(tree / ".cache"),
        # numpy's BLAS threads otherwise multiply each process's CPU use about sixfold.
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    return env


def run(command: list[str], tree: Path, timeout: float) -> tuple[int | None, str]:
    """Exit code (None on timeout) and output tail. Kills the whole process group afterwards,
    so no descendant outlives the run into the next mutant."""
    shutil.rmtree(tree / ".cache", ignore_errors=True)
    process = subprocess.Popen(
        command,
        cwd=tree,
        env=environment(tree),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output[-2000:].decode(errors="replace")
    except subprocess.TimeoutExpired:
        return None, "timeout"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def pytest(tree: Path, tests: list[str] | None, timeout: float) -> tuple[int | None, str]:
    command = [*PYTEST, f"--basetemp={tree / '.pytest-tmp'}", "-x"]
    return run([*command, *(tests or [])], tree, timeout)


def coverage_map(tree: Path, out: Path) -> tuple[Lines, set[tuple[str, int]], float]:
    """Line → covering tests, never-executed statements, and the run's seconds."""
    data = out / "coverage" / "data"
    data.parent.mkdir()
    rc = out / "coverage" / "rc"
    rc.write_text(COVERAGE_RC.format(package=tree / PACKAGE, data=data))
    command = [sys.executable, "-m", "coverage", "run", f"--rcfile={rc}", "-m"]
    command += [*PYTEST[2:], f"--basetemp={tree / '.pytest-tmp'}", "-p", "mutation_context"]
    started = time.monotonic()
    code, output = run(command, tree, timeout=3600)
    if code != 0:
        sys.exit(f"{output}\nthe unmutated suite failed under coverage (exit {code}); fix it")
    seconds = time.monotonic() - started
    subprocess.run([*command[:3], "combine", "-q", f"--rcfile={rc}"], cwd=tree, check=True)
    covered: Lines = {}
    unexecuted: set[tuple[str, int]] = set()
    collected = coverage.CoverageData(basename=str(data))
    collected.read()
    analysis = coverage.Coverage(data_file=str(data), config_file=str(rc))
    analysis.load()
    for filename in collected.measured_files():
        name = str(Path(filename).relative_to(tree))
        for line, contexts in collected.contexts_by_lineno(filename).items():
            covered[name, line] = set(contexts)
        _, _, _, missing, _ = analysis.analysis2(filename)
        unexecuted |= {(name, line) for line in missing}
    return covered, unexecuted, seconds


class Module:
    """Annotation spans (arid code) and statement extents of one source file."""

    def __init__(self, path: Path) -> None:
        source = path.read_text()
        tree = ast.parse(source)
        lines = source.splitlines()

        def position(line: int, byte: int) -> tuple[int, int]:  # AST columns count UTF-8 bytes
            return line, len(lines[line - 1].encode()[:byte].decode())

        self.annotations: list[tuple[tuple[int, int], tuple[int, int]]] = []
        self.statements: list[tuple[int, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
                self.statements.append((first, node.end_lineno or node.lineno))
            elif isinstance(node, ast.stmt):
                self.statements.append((node.lineno, node.end_lineno or node.lineno))
            annotation = None
            if isinstance(node, ast.arg | ast.AnnAssign):
                annotation = node.annotation
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                annotation = node.returns
            elif isinstance(node, ast.TypeAlias):
                annotation = node.value
            if annotation is not None and annotation.end_lineno is not None:
                start = position(annotation.lineno, annotation.col_offset)
                end = position(annotation.end_lineno, annotation.end_col_offset or 0)
                self.annotations.append((start, end))

    def arid(self, spec: MutationSpec) -> bool:
        return any(a <= spec.start_pos and spec.end_pos <= b for a, b in self.annotations)

    def lines(self, spec: MutationSpec) -> set[int]:
        """The mutated lines and the first line of the innermost statement around them."""
        start, end = spec.start_pos[0], spec.end_pos[0]
        around = [s for s in self.statements if s[0] <= start <= s[1]]
        lines = set(range(start, end + 1))
        if around:
            lines.add(min(around, key=lambda s: s[1] - s[0])[0])
        return lines


def changed_lines(ref: str) -> set[tuple[str, int]]:
    """Lines under the package added or changed since REF, untracked files included."""
    diff = subprocess.run(
        ["git", "diff", "-U0", "--no-color", ref, "--", str(PACKAGE)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    changed: set[tuple[str, int]] = set()
    name = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            name = line.removeprefix("+++ b/")
        elif match := re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line):
            first, count = int(match[1]), int(match[2] or 1)
            changed |= {(name, n) for n in range(first, first + count)}
    untracked = subprocess.run(
        ["git", "ls-files", "-o", "--exclude-standard", "--", str(PACKAGE)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    for name in untracked:
        count = len((REPO / name).read_text().splitlines())
        changed |= {(name, n) for n in range(1, count + 1)}
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--diff", metavar="REF", help="only mutate lines changed since REF")
    parser.add_argument("--sample", type=int, help="run a random sample of this many mutants")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--out", type=Path, help="results directory (default: a new temp dir)")
    parser.add_argument(
        "--verify-selection",
        action="store_true",
        help="also run the full suite after selected kills, to measure selection soundness",
    )
    args = parser.parse_args()
    out = (args.out or Path(tempfile.mkdtemp(prefix="triplum-mutation-"))).resolve()
    if out.is_relative_to(REPO):
        sys.exit("--out must be outside the repository, or the copies would copy each other")
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    trees = [out / f"tree-{i}" for i in range(args.workers)]
    base = trees[0]
    copy_tree(base)
    for tree in trees[1:]:
        shutil.copytree(base, tree)  # one snapshot, even if the checkout changes meanwhile
    session = out / "session.sqlite"
    with use_db(session) as db:
        init(find_modules([base / PACKAGE]), db, {})
        items = list(db.work_items)
    print(f"{len(items)} mutants; mapping coverage", file=sys.stderr)
    covered, unexecuted, suite_seconds = coverage_map(base, out)
    timeout = 3 * suite_seconds + 30

    modules: dict[str, Module] = {}
    changed = changed_lines(args.diff) if args.diff else None
    results: list[dict] = []
    pending = []
    for item in items:
        (spec,) = item.mutations
        name = str(Path(spec.module_path).relative_to(base))
        if name not in modules:
            modules[name] = Module(spec.module_path)
        module = modules[name]
        record = {
            "job_id": item.job_id,
            "module": name,
            "start": list(spec.start_pos),
            "end": list(spec.end_pos),
            "operator": spec.operator_name,
            "occurrence": spec.occurrence,
        }
        span = range(spec.start_pos[0], spec.end_pos[0] + 1)
        if changed is not None and not any((name, n) in changed for n in span):
            continue
        lines = module.lines(spec)
        if module.arid(spec):
            results.append(record | {"status": "arid"})
            continue
        contexts = [covered[name, n] for n in lines if (name, n) in covered]
        if not contexts:
            if any((name, n) in unexecuted for n in lines):
                results.append(record | {"status": "uncovered"})
                continue
            record["tests"] = None  # no statement found: be safe
        elif any("" in c for c in contexts):
            record["tests"] = None  # import-time code affects every test
        else:
            record["tests"] = sorted({test for tests in contexts for test in tests})
        pending.append((item, record))
    if args.sample is not None and args.sample < len(pending):
        pending = random.Random(args.seed).sample(pending, args.sample)
    print(f"running {len(pending)} mutants on {args.workers} workers", file=sys.stderr)

    free: queue.Queue[Path] = queue.Queue()
    for tree in trees:
        free.put(tree)

    def mutate_and_test(job: tuple) -> dict:
        item, record = job
        (spec,) = item.mutations
        tree = free.get()
        try:
            path = tree / record["module"]
            operator = get_operator(spec.operator_name)(**spec.operator_args)
            began = time.monotonic()
            with use_mutation(path, operator, spec.occurrence) as (original, mutated):
                if mutated is None:
                    return record | {"status": "no-mutation"}
                record["diff"] = "\n".join(_make_diff(original, mutated, record["module"]))
                try:  # cosmic-ray 8.8 rewrites e.g. `{**x}` to `{>>x}`
                    with warnings.catch_warnings(action="ignore"):  # tests still see them
                        compile(mutated, path, "exec")
                except SyntaxError:
                    return record | {"status": "invalid"}
                runs = []
                if record["tests"] is not None:
                    runs.append(("selected", *pytest(tree, record["tests"], timeout)))
                verify = args.verify_selection and runs and runs[0][1] is not None
                if record["tests"] is None or runs[0][1] == 0 or verify:
                    runs.append(("full", *pytest(tree, None, timeout)))
            record["runs"] = [(phase, code) for phase, code, _ in runs]
            # Keep diagnostics where the exit code alone does not say a test failed.
            record["output"] = [out for _, code, out in runs if code not in (0, 1, None)]
            record["seconds"] = round(time.monotonic() - began, 2)
            final = runs[-1][1] if runs[0][1] == 0 else runs[0][1]
            # Nonzero is a kill, as in cosmic-ray: exit 2 or 4 when a mutant breaks importing a
            # test module, 3 or a signal on a crash ("output" keeps the evidence). The unmutated
            # coverage run validated the node ids. Exit 5 means nothing was selected.
            if final == 5:
                raise RuntimeError(f"pytest collected no tests for {record}")
            record["status"] = {0: "survived", None: "timeout"}.get(final, "killed")
            return record
        finally:
            free.put(tree)

    with ThreadPoolExecutor(args.workers) as pool:
        for done, record in enumerate(pool.map(mutate_and_test, pending), 1):
            results.append(record)
            if done % 100 == 0:
                print(f"{done}/{len(pending)}", file=sys.stderr)

    with use_db(session, WorkDB.Mode.open) as db:
        for record in results:
            if record["status"] in ("killed", "survived", "timeout"):
                outcome = (
                    TestOutcome.SURVIVED if record["status"] == "survived" else TestOutcome.KILLED
                )
                result = WorkResult(
                    worker_outcome=WorkerOutcome.NORMAL,
                    test_outcome=outcome,
                    output="timeout" if record["status"] == "timeout" else None,  # as cosmic-ray
                    diff=record["diff"],
                )
            else:
                result = WorkResult(worker_outcome=WorkerOutcome.SKIPPED, output=record["status"])
            db.set_result(record["job_id"], result)

    with (out / "results.jsonl").open("w") as handle:
        for record in results:
            handle.write(json.dumps(record) + "\n")
    survivors = defaultdict(list)
    for record in results:
        if record["status"] == "survived":
            survivors[record["module"]].append(record)
    with (out / "survivors.md").open("w") as handle:
        for name in sorted(survivors):
            handle.write(f"## {name}\n\n")
            for record in sorted(survivors[name], key=lambda r: r["start"]):
                handle.write(f"`{record['operator']}` line {record['start'][0]}\n\n")
                handle.write(f"```diff\n{record['diff']}\n```\n\n")

    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    summary = {
        "statuses": Counter(r["status"] for r in results),
        "selected_runs": sum(1 for r in results if r.get("tests")),
        "full_runs": sum(1 for r in results for phase, _ in r.get("runs", ()) if phase == "full"),
        "suite_seconds_under_coverage": round(suite_seconds, 1),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "child_cpu_seconds": round(children.ru_utime + children.ru_stime, 1),
        "workers": args.workers,
        "out": str(out),
    }
    if args.verify_selection:
        summary["selection_disagreements"] = sum(
            1
            for r in results
            if len(r.get("runs", ())) == 2 and (r["runs"][0][1] == 0) != (r["runs"][1][1] == 0)
        )
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
