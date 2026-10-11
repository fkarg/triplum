"""Thin cache administration commands with forgiving finite command discovery."""

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import asdict
from difflib import get_close_matches
from pathlib import Path

from triplum.cache.admin import cache_stats, clear_cache


def match_selector(value: str, choices: Sequence[str], *, kind: str = "command") -> str:
    """Resolve exact, prefix, substring, then typo matches; ambiguity is an error.

    Only finite command/function names use this matching. Paths and computation identities
    pass through untouched to the library boundary.
    """
    if value in choices:
        return value
    if not choices:
        raise argparse.ArgumentTypeError(f"unknown {kind} {value!r}; none are recorded")
    matches = [choice for choice in choices if choice.startswith(value)]
    if not matches:
        matches = [choice for choice in choices if value in choice]
    if not matches:
        matches = get_close_matches(value, choices, n=len(choices), cutoff=0.6)
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise argparse.ArgumentTypeError(
            f"ambiguous {kind} {value!r}; choices: {', '.join(matches)}"
        )
    raise argparse.ArgumentTypeError(f"unknown {kind} {value!r}; choices: {', '.join(choices)}")


def _resolve(value: str, choices: Sequence[str], kind: str) -> str:
    """Match a selector and report any non-exact resolution on stderr."""
    resolved = match_selector(value, choices, kind=kind)
    if resolved != value:
        print(f"triplum: {kind} {value!r} matched {resolved!r}", file=sys.stderr)
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    """Run cache stats or clear; explicit clear commands require no confirmation."""
    parser = argparse.ArgumentParser(
        prog="triplum",
        description="Inspect or clear computation caches: cache stats | cache clear.",
        allow_abbrev=False,
    )
    parser.add_argument("command", nargs="?")
    parser.add_argument("action", nargs="?")
    parser.add_argument(
        "--path", type=Path, help="cache database path (default: shared user cache)"
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--computation", help="exact full SHA-256 computation identity")
    selector.add_argument("--name", help="function name; selects all its recorded fingerprints")
    parser.add_argument(
        "--details", action="store_true", help="stats: scan exact entry/payload totals"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    parser.add_argument(
        "--no-input", action="store_true", help="disable prompts (commands never prompt)"
    )
    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("missing command; choices: cache")
    if args.action is None:
        parser.error("missing cache command; choices: stats, clear")
    try:
        _resolve(args.command, ("cache",), "command")
        action = _resolve(args.action, ("stats", "clear"), "cache command")
        if action == "clear" and args.details:
            parser.error("--details applies only to cache stats")
        name = None
        if args.name is not None:
            choices = sorted({row.name for row in cache_stats(args.path).computations if row.name})
            name = _resolve(args.name, choices, "function name")
        if action == "stats":
            stats = cache_stats(
                args.path, computation=args.computation, name=name, details=args.details
            )
            if args.json:
                data = asdict(stats)
                data["path"] = str(stats.path)
                print(json.dumps(data))
            else:
                print(f"Cache: {stats.path}")
                print(f"Exists: {stats.exists}")
                print(f"Database bytes: {stats.database_bytes}")
                print(f"WAL bytes: {stats.wal_bytes}")
                print(f"Reusable bytes: {stats.reusable_bytes}")
                print(f"Computations: {len(stats.computations)}")
                for computation in stats.computations:
                    line = computation.computation
                    if args.details:
                        line += f"  entries={computation.entries}  payload_bytes={computation.payload_bytes}"
                        if computation.name:
                            line += f"  {computation.name}"
                        if computation.source_path:
                            line += f"  {computation.source_path}"
                            if computation.source_line is not None:
                                line += f":{computation.source_line}"
                    print(line)
        else:
            count = clear_cache(args.path, computation=args.computation, name=name)
            if args.json:
                print(json.dumps({"cleared_computations": count, "name": name}))
            else:
                print(
                    f"Cleared {count} computation table(s); running writers may repopulate the cache."
                )
    except (OSError, ValueError, sqlite3.Error, argparse.ArgumentTypeError) as error:
        parser.error(str(error))
    return 0
