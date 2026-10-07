"""Cache operator commands through their installed and module entry points."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "triplum", *args],
        env={**os.environ, "XDG_CACHE_HOME": str(tmp_path / "user-cache")},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "command", [("cache", "stats"), ("ca", "st"), ("ach", "tat"), ("cahce", "sttas")]
)
def test_missing_cache_stats_do_not_create_files(tmp_path: Path, command: tuple[str, str]) -> None:
    path = tmp_path / "absent" / "cache.sqlite3"
    result = run_cli(tmp_path, *command, "--path", str(path), "--json", "--no-input")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "path": str(path),
        "exists": False,
        "database_bytes": 0,
        "wal_bytes": 0,
        "reusable_bytes": 0,
        "computations": [],
    }
    assert not path.parent.exists()


@pytest.mark.parametrize("args", [(), ("cache",), ("unknown",), ("cache", "a")])
def test_missing_unknown_or_ambiguous_commands_offer_choices(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    result = run_cli(tmp_path, *args)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "choices:" in result.stderr
    assert "Traceback" not in result.stderr


def test_invalid_computation_is_not_fuzzily_matched(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "cache", "clear", "--computation", "a")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


def test_help_lists_commands(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "cache", "--help")
    assert result.returncode == 0
    assert "stats" in result.stdout and "clear" in result.stdout
    assert result.stderr == ""


def test_stats_and_clear_real_cache(tmp_path: Path) -> None:
    from triplum.cache.protocols import CacheKey
    from triplum.cache.sqlite import SQLiteBackend

    path = tmp_path / "cache.sqlite3"
    first, second = b"a" * 32, b"b" * 32
    backend = SQLiteBackend(path)
    try:
        backend.put_many(
            [(CacheKey(first, b"i" * 32), b"one"), (CacheKey(second, b"j" * 32), b"four")]
        )
        result = run_cli(tmp_path, "cache", "stats", "--path", str(path), "--details", "--json")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["computations"] == [
            {"computation": first.hex(), "entries": 1, "payload_bytes": 3},
            {"computation": second.hex(), "entries": 1, "payload_bytes": 4},
        ]
        result = run_cli(
            tmp_path, "cache", "clear", "--path", str(path), "--computation", first.hex(), "--json"
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"cleared_computations": 1}
        assert backend.get(CacheKey(first, b"i" * 32)) is None
        assert backend.get(CacheKey(second, b"j" * 32)) == b"four"
        result = run_cli(tmp_path, "cache", "clear", "--path", str(path), "--no-input")
        assert result.returncode == 0, result.stderr
        assert "Cleared 1 computation" in result.stdout
        assert backend.get(CacheKey(second, b"j" * 32)) is None
        assert path.exists()
    finally:
        backend.close()


def test_storage_errors_are_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "broken.sqlite3"
    path.write_text("not a database")
    result = run_cli(tmp_path, "cache", "stats", "--path", str(path), "--json")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_stats_text_and_metadata_only_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from triplum.cache.protocols import CacheKey
    from triplum.cache.sqlite import SQLiteBackend
    from triplum.cli import main

    path = tmp_path / "cache.sqlite3"
    process = b"a" * 32
    backend = SQLiteBackend(path)
    try:
        backend.put_many([(CacheKey(process, b"i" * 32), b"one")])
        assert main(["cache", "stats", "--path", str(path), "--details"]) == 0
        output = capsys.readouterr()
        assert f"{process.hex()}  entries=1  payload_bytes=3" in output.out
        assert output.err == ""
        assert main(["cache", "stats", "--path", str(path), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["computations"] == [
            {"computation": process.hex(), "entries": None, "payload_bytes": None}
        ]
    finally:
        backend.close()


def test_details_cannot_be_used_for_clear(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "cache", "clear", "--details")
    assert result.returncode == 2
    assert "--details applies only to cache stats" in result.stderr
    assert result.stdout == ""


def test_installed_command(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(Path(sys.executable).parent / "triplum"), "cache", "stats", "--json"],
        env={**os.environ, "XDG_CACHE_HOME": str(tmp_path / "user-cache")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["exists"] is False
    assert Path(data["path"]).is_relative_to(tmp_path / "user-cache")
    assert not (tmp_path / "user-cache").exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("stats", "stats"), ("st", "stats"), ("tat", "stats"), ("sttas", "stats")],
)
def test_command_matching(value: str, expected: str) -> None:
    from triplum.cli import match_selector

    assert match_selector(value, ("stats", "clear")) == expected


@pytest.mark.parametrize(("value", "message"), [("a", "ambiguous"), ("unknown", "unknown")])
def test_command_matching_errors(value: str, message: str) -> None:
    import argparse

    from triplum.cli import match_selector

    with pytest.raises(argparse.ArgumentTypeError, match=f"{message} command.*choices:"):
        match_selector(value, ("stats", "clear"))


@pytest.mark.parametrize("args", [[], ["cache"], ["cache", "clear", "--details"]])
def test_main_reports_usage_errors(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    from triplum.cli import main

    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert capsys.readouterr().out == ""


def test_main_empty_cache_and_storage_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from triplum.cli import main

    path = tmp_path / "cache.sqlite3"
    for extra in ([], ["--details"]):
        assert main(["cache", "stats", "--path", str(path), *extra]) == 0
        assert "Computations: 0" in capsys.readouterr().out
    for extra in ([], ["--json"]):
        assert main(["cache", "clear", "--path", str(path), *extra]) == 0
        output = capsys.readouterr()
        if extra:
            assert json.loads(output.out) == {"cleared_computations": 0}
        else:
            assert "Cleared 0 computation" in output.out
        assert output.err == ""
    path.write_text("not a database")
    with pytest.raises(SystemExit) as exc:
        main(["cache", "stats", "--path", str(path)])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "error:" in output.err
    assert output.out == ""
