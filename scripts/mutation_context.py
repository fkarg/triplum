"""pytest plugin for ``scripts/mutation.py``: credit coverage to the running test.

The in-process collector switches its dynamic context per test. Subprocesses read the rc file
themselves through ``COVERAGE_PROCESS_START``; its ``context = ${TRIPLUM_MUTATION_CONTEXT}``
then expands to the test that started them. (``patch = subprocess`` alone passes children the
parent's already-expanded configuration, which credits every subprocess line to no test.)
"""

import os

import coverage
import pytest

VARIABLE = "TRIPLUM_MUTATION_CONTEXT"


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
