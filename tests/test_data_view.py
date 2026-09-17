from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from triplum.bench.data_view import print_overview
from triplum.eval.datasets.base import File, Frames, Spec


def unused_parser(paths: dict[str, Path], n: int | None) -> Frames:
    raise AssertionError("Rendering must not parse or fetch datasets")


@pytest.mark.parametrize("width", [48, 63, 64, 80, 120])
def test_overview_preserves_names_states_flags_without_color(width):
    rows = [
        (Spec("hotpotqa", "multihop", (), "MIT", unused_parser, default=True), "verified"),
        (Spec("ectqa", "temporal", (), "MIT", unused_parser), "partial"),
        (Spec("broken", "control", (), "MIT", unused_parser), "invalid"),
        (Spec("graphjudge_genwiki", "extraction", (), "MIT", unused_parser), "not downloaded"),
        (
            Spec(
                "browsecomp_plus",
                "multihop",
                (File("u", "f", "h", 400 << 20),),
                "MIT",
                unused_parser,
            ),
            "not downloaded",
        ),
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
    for spec, state in rows:
        assert spec.name in compact and state.replace(" ", "") in compact
        assert spec.family in compact
    assert "default" in out and "large" in out
    assert "5 datasets" in out
    assert "1 verified" in out and "1 partial" in out and "1 invalid" in out
    assert "2 not downloaded" in out
    assert "/tmp/data[local]" in out  # Literal brackets must not become Rich markup.
    assert "Remove invalid files" in out


def test_overview_verified_only_has_no_recovery_warning():
    stream = StringIO()
    spec = Spec("ready", "multihop", (), "MIT", unused_parser)
    print_overview([(spec, "verified")], Path("/tmp/data"), console=Console(file=stream, width=80))
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
    spec = Spec("ready", "multihop", (), "MIT", unused_parser)
    console = Console(file=stream, width=80, force_terminal=True, color_system="standard")
    print_overview([(spec, "verified")], Path("/tmp/data"), console=console)
    assert ("\x1b[32m" in stream.getvalue()) == (not no_color)
