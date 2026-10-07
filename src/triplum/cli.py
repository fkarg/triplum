"""Thin cache administration commands with forgiving finite command discovery."""

import argparse
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import asdict
from difflib import get_close_matches
from pathlib import Path

from triplum.cache.admin import cache_stats, clear_cache


def match_selector(value: str, choices: Sequence[str]) -> str:
    """Resolve exact, prefix, substring, then typo matches; ambiguity is an error.

    Only finite command names use this matching. Paths and computation identities
    pass through untouched to the library boundary.
    """
    if value in choices:
        return value
    matches = [choice for choice in choices if choice.startswith(value)]
    if not matches:
        matches = [choice for choice in choices if value in choice]
    if not matches:
        matches = get_close_matches(value, choices, n=len(choices), cutoff=0.6)
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise argparse.ArgumentTypeError(
            f"ambiguous command {value!r}; choices: {', '.join(matches)}"
        )
    raise argparse.ArgumentTypeError(f"unknown command {value!r}; choices: {', '.join(choices)}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run cache stats or clear; explicit clear commands require no confirmation."""
    parser = argparse.ArgumentParser(
        prog="triplum",
        description="Inspect or clear computation caches: cache stats | cache clear.",
        allow_abbrev=False,
    )
    parser.add_argument("command", nargs="?", type=lambda value: match_selector(value, ("cache",)))
    parser.add_argument(
        "action", nargs="?", type=lambda value: match_selector(value, ("stats", "clear"))
    )
    parser.add_argument(
        "--path", type=Path, help="cache database path (default: shared user cache)"
    )
    parser.add_argument("--computation", help="exact full SHA-256 computation identity")
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
    if args.action == "clear" and args.details:
        parser.error("--details applies only to cache stats")
    try:
        if args.action == "stats":
            stats = cache_stats(args.path, computation=args.computation, details=args.details)
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
                    print(line)
        else:
            count = clear_cache(args.path, computation=args.computation)
            if args.json:
                print(json.dumps({"cleared_computations": count}))
            else:
                print(
                    f"Cleared {count} computation table(s); running writers may repopulate the cache."
                )
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.error(str(error))
    return 0
