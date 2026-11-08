"""Thin cache and dataset commands with forgiving finite command discovery."""

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import asdict
from difflib import get_close_matches
from pathlib import Path

from triplum.cache.admin import cache_stats, clear_cache
from triplum.datasets.admin import dataset_status, remove_dataset, verify_dataset
from triplum.datasets.catalogue import CATALOGUE
from triplum.datasets.files import download

PROMPT_BYTES = 5_000_000_000  # removing more than this asks first


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
    """Run a cache or datasets command; only removing more than 5 GB of datasets asks first.

    Misuse (missing, unknown or conflicting arguments) prints usage and exits 2; a failed
    operation prints one `triplum: error:` line and returns 1.
    """
    parser = argparse.ArgumentParser(
        prog="triplum",
        description="Operator commands: cache stats | cache clear | "
        "datasets list | download | verify | remove | licence.",
        allow_abbrev=False,
    )
    parser.add_argument("command", nargs="?")
    parser.add_argument("action", nargs="?")
    parser.add_argument("target", nargs="?", help="datasets: the dataset name")
    parser.add_argument(
        "--path", type=Path, help="cache database path (default: shared user cache)"
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--computation", help="exact full SHA-256 computation identity")
    selector.add_argument("--name", help="function name; selects all its recorded fingerprints")
    parser.add_argument(
        "--details", action="store_true", help="stats: scan exact entry/payload totals"
    )
    parser.add_argument(
        "--yes", action="store_true", help="datasets remove: do not ask before removing > 5 GB"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    parser.add_argument("--no-input", action="store_true", help="never prompt")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("missing command; choices: cache, datasets")
    try:
        command = _resolve(args.command, ("cache", "datasets"), "command")
        if command == "cache":
            return _cache(parser, args)
        return _datasets(parser, args)
    except argparse.ArgumentTypeError as error:  # an unknown or ambiguous name: misuse
        parser.error(str(error))
    except (OSError, ValueError, sqlite3.Error) as error:  # the operation itself failed
        message = str(error)
        if "CERTIFICATE_VERIFY_FAILED" in message:
            message += " (point SSL_CERT_FILE at your CA bundle; do not disable verification)"
        print(f"triplum: error: {message}", file=sys.stderr)
        return 1


def _cache(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.action is None:
        parser.error("missing cache command; choices: stats, clear")
    if args.target is not None or args.yes:
        parser.error("cache commands take no dataset name or --yes")
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
    return 0


def _datasets(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    actions = ("list", "download", "verify", "remove", "licence")
    if args.action is None:
        parser.error(f"missing datasets command; choices: {', '.join(actions)}")
    if args.path or args.computation or args.name or args.details:
        parser.error("--path, --computation, --name and --details apply only to cache commands")
    action = _resolve(args.action, actions, "datasets command")
    if action == "list":
        if args.target is not None:
            parser.error("datasets list takes no dataset name")
        statuses = [dataset_status(entry) for entry in CATALOGUE.values()]
        if args.json:
            print(json.dumps([{**asdict(s), "folder": str(s.folder)} for s in statuses]))
            return 0
        for status in statuses:
            print(f"{status.name}  {status.status}  {status.folder}")
            for file in status.files:
                found = "missing" if file.bytes is None else f"{file.bytes} bytes"
                print(f"  {file.name}  {found}, expected {file.expected_bytes} bytes")
        return 0
    if args.target is None:
        parser.error(f"datasets {action} needs a dataset name; choices: {', '.join(CATALOGUE)}")
    entry = CATALOGUE[_resolve(args.target, list(CATALOGUE), "dataset")]
    if action == "download":
        print(f"Downloading {entry.name} if missing…", file=sys.stderr)
        folder = download(entry)
        print(json.dumps({"dataset": entry.name, "folder": str(folder)}) if args.json else folder)
    elif action == "verify":
        problems = verify_dataset(entry)
        if args.json:
            print(json.dumps({"dataset": entry.name, "ok": not problems, "problems": problems}))
        else:
            print("\n".join(problems) or f"{entry.name}: all files verified")
        return 1 if problems else 0
    elif action == "remove":
        size = sum(f.bytes or 0 for f in dataset_status(entry).files)
        if size > PROMPT_BYTES and not args.yes:
            if args.no_input or not sys.stdin.isatty():
                print(
                    f"triplum: error: {entry.name} holds {size} bytes; pass --yes to remove it",
                    file=sys.stderr,
                )
                return 1
            print(f"Remove {size} bytes of {entry.name}? [y/N] ", end="", file=sys.stderr)
            if sys.stdin.readline().strip().lower() not in ("y", "yes"):
                print("Nothing removed.", file=sys.stderr)
                return 1
        removed = remove_dataset(entry)
        if args.json:
            print(json.dumps({"dataset": entry.name, "removed_bytes": removed}))
        else:
            print(f"Removed {removed} bytes of {entry.name}.")
    elif args.json:
        print(
            json.dumps(
                {
                    "dataset": entry.name,
                    "licence": entry.licence,
                    "commercial_reuse": entry.commercial_reuse,
                }
            )
        )
    else:
        print(f"{entry.name}: {entry.licence}")
        print(f"Commercial reuse: {entry.commercial_reuse}")
    return 0
