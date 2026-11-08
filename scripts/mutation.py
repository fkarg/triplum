"""Mutation testing on an isolated copy: cosmic-ray mutants, per-mutant test selection.

Run with ``uv run --group mutation python scripts/mutation.py [--diff REF]``.

1. Copy the working tree (tracked and untracked, not ignored) into ``--out``, once per worker.
2. Generate mutants with cosmic-ray, plus one body-removal mutant per function (body replaced by
   ``return None``, after any docstring; the pseudo-tested check). Skip arid ones (inside
   annotations) and, with ``--diff``, those outside the lines changed since REF.
3. Run the suite once under coverage with per-test contexts, subprocesses included, to map each
   line to the tests that execute it. The run must pass.
4. Per mutant, run only the tests covering its lines. Mutants on import-time lines run the full
   suite; mutants on statements no test executes are reported as uncovered without a run.
   Every survivor of a selected run is re-run against the full suite before it is reported, so
   selection can cost time but cannot invent survivors.

Every selected or full run goes to completion (no ``-x``) and records each failing test with its
kind (assertion or crash), so ``results.jsonl`` holds a kill matrix; ``scripts/mutation_report.py``
derives test-quality indicators from it.

Results: ``results.jsonl`` (one line per mutant), ``survivors.md`` and cosmic-ray's
``session.sqlite`` (for ``cr-report``/``cr-html``; cosmic-ray mutants only) in ``--out``.
Mutants are not a score to gate on: review the survivors.
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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import coverage
from cosmic_ray.commands import init
from cosmic_ray.modules import find_modules
from cosmic_ray.mutating import _make_diff, mutate_code
from cosmic_ray.plugins import get_operator
from cosmic_ray.work_db import WorkDB, use_db
from cosmic_ray.work_item import MutationSpec, TestOutcome, WorkerOutcome, WorkResult

REPO = Path(__file__).resolve().parent.parent
PACKAGE = Path("src/triplum")
PYTEST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
BODY = "body/ReturnNone"
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
        TRIPLUM_MUTATION_FAILURES=str(tree / ".failures"),  # written by mutation_context
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


def pytest(
    tree: Path, tests: list[str] | None, timeout: float
) -> tuple[int | None, str, dict[str, str]]:
    """Exit code, output tail and every failing test with its kind ("assert" or "error"): no
    `-x`, so the kill matrix is complete. An assertion in the test body outranks a teardown
    error of the same test."""
    failures = tree / ".failures"
    failures.unlink(missing_ok=True)
    command = [*PYTEST, f"--basetemp={tree / '.pytest-tmp'}", "-p", "mutation_context"]
    code, output = run([*command, *(tests or [])], tree, timeout)
    killers: dict[str, str] = {}
    for line in failures.read_text().splitlines() if failures.exists() else ():
        test, kind = line.rsplit("\t", 1)
        killers[test] = "assert" if "assert" in (kind, killers.get(test)) else kind
    return code, output, killers


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


def _trivial(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Expr):
        return isinstance(statement.value, ast.Constant)
    if isinstance(statement, ast.Return):
        value = statement.value
        return value is None or (isinstance(value, ast.Constant) and value.value is None)
    return False


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
        self.bodies: list[tuple[str, int, int, str]] = []  # name, first and last line, mutant
        self._bodies(tree, lines, "")
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

    def _bodies(self, node: ast.AST, lines: list[str], prefix: str) -> None:
        """Body-removal mutants: functions whose body (after any docstring) starts on a line of
        its own; trivial bodies (`pass`, `...`, `return`/`return None`) give none."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                self._bodies(child, lines, f"{prefix}{child.name}.")
                continue
            if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                self._bodies(child, lines, prefix)  # definitions under if/try/with/...
                continue
            name = f"{prefix}{child.name}"
            self._bodies(child, lines, f"{name}.")
            body = child.body
            if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]  # keep the docstring
            if not body or (len(body) == 1 and _trivial(body[0])):
                continue
            head = body[0]
            decorators = getattr(head, "decorator_list", [])
            first = min([head.lineno, *(d.lineno for d in decorators)])
            column = decorators[0].col_offset - 1 if decorators else head.col_offset
            indent = lines[first - 1][:column]
            if indent.strip():
                continue  # the body shares its first line with the header or the docstring
            last = child.end_lineno or head.lineno
            mutant = [*lines[: first - 1], f"{indent}return None", *lines[last:]]
            self.bodies.append((name, first, last, "\n".join(mutant) + "\n"))

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
        "--full",
        action="store_true",
        help="run the full suite for every mutant: complete killer sets for mutation_report.py",
    )
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

    modules = {str(path.relative_to(base)): Module(path) for path in find_modules([base / PACKAGE])}
    changed = changed_lines(args.diff) if args.diff else None
    results: list[dict] = []
    pending: list[tuple[dict, Callable[[str], str | None]]] = []
    candidates: list[tuple[dict, range, set[int], Callable[[str], str | None]]] = []
    for item in items:
        (spec,) = item.mutations
        name = str(Path(spec.module_path).relative_to(base))
        operator = get_operator(spec.operator_name)(**spec.operator_args)
        record: dict = {
            "job_id": item.job_id,
            "module": name,
            "function": spec.definition_name,
            "start": list(spec.start_pos),
            "end": list(spec.end_pos),
            "operator": spec.operator_name,
        }
        if modules[name].arid(spec):
            record["status"] = "arid"
        lines = modules[name].lines(spec)
        mutate = partial(mutate_code, operator=operator, occurrence=spec.occurrence)
        candidates.append((record, range(spec.start_pos[0], spec.end_pos[0] + 1), lines, mutate))
    for name, module in modules.items():
        for function, first, last, mutant in module.bodies:
            record: dict = {
                "job_id": f"body:{name}:{first}",
                "module": name,
                "function": function,
                "start": [first, 0],
                "end": [last, 0],
                "operator": BODY,
            }
            body = range(first, last + 1)
            candidates.append((record, body, set(body), lambda _, m=mutant: m))
    for record, span, lines, mutate in candidates:
        name = record["module"]
        if changed is not None and not any((name, n) in changed for n in span):
            continue
        if record.get("status") == "arid":
            results.append(record)
            continue
        contexts = [covered[name, n] for n in lines if (name, n) in covered]
        record["covering"] = sorted({test for tests in contexts for test in tests if test})
        if not contexts:
            if any((name, n) in unexecuted for n in lines):
                results.append(record | {"status": "uncovered"})
                continue
            record["tests"] = None  # no statement found: be safe
        elif args.full or any("" in c for c in contexts):
            record["tests"] = None  # full suite: requested, or import-time code affects all
        else:
            record["tests"] = record["covering"]
        pending.append((record, mutate))
    if args.sample is not None and args.sample < len(pending):
        pending = random.Random(args.seed).sample(pending, args.sample)
    print(f"running {len(pending)} mutants on {args.workers} workers", file=sys.stderr)

    free: queue.Queue[Path] = queue.Queue()
    for tree in trees:
        free.put(tree)

    def mutate_and_test(job: tuple[dict, Callable[[str], str | None]]) -> dict:
        record, mutate = job
        tree = free.get()
        try:
            path = tree / record["module"]
            original = path.read_text()
            began = time.monotonic()
            mutated = mutate(original)
            if mutated is None or mutated == original:
                return record | {"status": "no-mutation"}
            record["diff"] = "\n".join(_make_diff(original, mutated, record["module"]))
            try:  # cosmic-ray 8.8 rewrites e.g. `{**x}` to `{>>x}`
                with warnings.catch_warnings(action="ignore"):  # tests still see them
                    compile(mutated, path, "exec")
            except SyntaxError:
                return record | {"status": "invalid"}
            try:
                path.write_text(mutated)
                runs = []
                if record["tests"] is not None:
                    runs.append(("selected", *pytest(tree, record["tests"], timeout)))
                verify = args.verify_selection and runs and runs[0][1] is not None
                if record["tests"] is None or runs[0][1] == 0 or verify:
                    runs.append(("full", *pytest(tree, None, timeout)))
            finally:
                path.write_text(original)
            record["runs"] = [(phase, code) for phase, code, _, _ in runs]
            record["killers"] = {}
            for *_, killers in runs:  # an assertion seen in either run outranks an error
                for test, kind in killers.items():
                    if record["killers"].get(test) != "assert":
                        record["killers"][test] = kind
            # Keep diagnostics where the exit code alone does not say a test failed.
            record["output"] = [out for _, code, out, _ in runs if code not in (0, 1, None)]
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
            if record["operator"] == BODY:
                continue
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
