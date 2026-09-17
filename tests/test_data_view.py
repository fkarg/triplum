from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from triplum.bench.data_view import print_overview
from triplum.bench.inputs import Benchmark
from triplum.datasets.base import Entry


def unused_builder(settings) -> Benchmark:
    raise AssertionError("Rendering must not build, parse or fetch datasets")


def _entry(name: str, family: str, **kw) -> Entry:
    return Entry(name=name, family=family, licence="MIT", build=unused_builder, **kw)


@pytest.mark.parametrize("width", [48, 63, 64, 80, 120])
def test_overview_preserves_names_states_flags_without_color(width):
    rows = [
        (_entry("hotpotqa", "multihop", default=True), False, "verified"),
        (_entry("ectqa", "temporal"), False, "partial"),
        (_entry("broken", "control"), False, "invalid"),
        (_entry("graphjudge_genwiki", "extraction"), False, "not downloaded"),
        (_entry("browsecomp_plus", "multihop"), True, "not downloaded"),
    ]
    stream = StringIO()
    print_overview(
        rows, Path("/tmp/data[local]"), console=Console(file=stream, width=width, color_system=None)
    )
    out = stream.getvalue()
    assert "\x1b" not in out
    assert all(len(line) <= width for line in out.splitlines())
    # Text may wrap, but no identifier, state or flag may be elided.
    compact = "".join(out.split())
    for entry, _, state in rows:
        assert entry.name in compact and state.replace(" ", "") in compact
        assert entry.family in compact
    assert "default" in out and "large" in out
    assert "5 datasets" in out
    assert "1 verified" in out and "1 partial" in out and "1 invalid" in out
    assert "2 not downloaded" in out
    assert "/tmp/data[local]" in out  # Literal brackets must not become Rich markup.
    assert "Remove invalid files" in out


def test_redirected_overview_verified_only_has_no_recovery_warning():
    stream = StringIO()
    print_overview(
        [(_entry("ready", "multihop"), False, "verified")],
        Path("/tmp/data"),
        console=Console(file=stream, width=80, force_terminal=False),
    )
    out = stream.getvalue()
    assert "\x1b" not in out
    assert "1 dataset" in out and "1 verified" in out
    assert "Remove invalid files" not in out


@pytest.mark.parametrize("no_color", [False, True])
def test_terminal_color_respects_no_color(monkeypatch, no_color):
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    stream = StringIO()
    console = Console(file=stream, width=80, force_terminal=True, color_system="standard")
    print_overview(
        [(_entry("ready", "multihop"), False, "verified")], Path("/tmp/data"), console=console
    )
    assert ("\x1b[32m" in stream.getvalue()) == (not no_color)
