"""pytest plugin for ``scripts/mutation.py``: credit coverage to the running test, and record
failing tests for the kill matrix.

Failures go to the file named by ``TRIPLUM_MUTATION_FAILURES``, one ``node-id<TAB>kind`` per
line. The kind classifies the exception, which approximates oracle versus crash: ``assert`` is
an ``AssertionError`` raised outside the package source (a test's ``assert``, ``pytest.raises``
regex mismatch) or ``pytest.fail`` (including ``DID NOT RAISE``) during the call phase;
``error`` is everything else: other exceptions (also a wrong exception type inside
``pytest.raises``), an ``assert`` inside the package, exception groups, strict XPASS, and
setup/teardown failures. Collection errors are ``collect:<path>`` with kind ``error``.

The in-process collector switches its dynamic context per test. Subprocesses read the rc file
themselves through ``COVERAGE_PROCESS_START``; its ``context = ${TRIPLUM_MUTATION_CONTEXT}``
then expands to the test that started them. (``patch = subprocess`` alone passes children the
parent's already-expanded configuration, which credits every subprocess line to no test.)
"""

import os
from collections.abc import Generator
from pathlib import Path

import coverage
import pytest

VARIABLE = "TRIPLUM_MUTATION_CONTEXT"
FAILURES = "TRIPLUM_MUTATION_FAILURES"


def _record_failure(nodeid: str, kind: str) -> None:
    if path := os.environ.get(FAILURES):
        with open(path, "a") as handle:
            handle.write(f"{nodeid}\t{kind}\n")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if report.failed:
        excinfo = call.excinfo
        package = item.config.rootpath / "src"
        oracle = (
            call.when == "call"
            and excinfo is not None
            and (
                excinfo.errisinstance(pytest.fail.Exception)
                or (
                    excinfo.errisinstance(AssertionError)
                    and not Path(str(excinfo.traceback[-1].path)).is_relative_to(package)
                )
            )
        )
        _record_failure(report.nodeid, "assert" if oracle else "error")
    return report


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.failed:
        _record_failure(f"collect:{report.nodeid}", "error")


def pytest_configure(config: pytest.Config) -> None:
    cov = coverage.Coverage.current()
    if cov is not None and cov.config.config_file:
        os.environ.pop("COVERAGE_PROCESS_CONFIG", None)
        os.environ["COVERAGE_PROCESS_START"] = cov.config.config_file


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> object:
    cov = coverage.Coverage.current()
    os.environ[VARIABLE] = item.nodeid
    if cov is not None:
        cov.switch_context(item.nodeid)
    try:
        return (yield)
    finally:
        os.environ.pop(VARIABLE, None)
        if cov is not None:
            cov.switch_context("")
