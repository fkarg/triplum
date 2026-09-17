"""Forgiving CLI selection; library identities remain exact.

Exact matches and single prefix, substring or typo matches resolve automatically.
Multiple plausible matches require a terminal choice. All interaction goes to stderr, leaving stdout for data.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from contextlib import redirect_stdout
from difflib import SequenceMatcher

import typer
from typer.core import TyperGroup


def is_interactive() -> bool:
    """Both the input and diagnostic streams must be terminals."""
    return sys.stdin.isatty() and sys.stderr.isatty()


def no_input_callback(ctx: typer.Context, value: bool) -> bool:
    """Store the eager option before command resolution or parameter callbacks."""
    if value:
        ctx.meta["no_input"] = True
    return value


def resolve(
    value: str | None,
    choices: Iterable[str],
    label: str,
    *,
    ctx: typer.Context | None = None,
    descriptions: Mapping[str, str] | None = None,
    prompt: bool = True,
) -> str:
    """Resolve a finite CLI choice, or raise a usage error with canonical candidates."""
    choices = list(dict.fromkeys(choices))
    if value in choices:
        return value
    if not choices:
        raise typer.BadParameter(f"No {label} choices available.")
    candidates = choices
    if value:
        query = value.casefold()
        candidates = [c for c in choices if c.casefold() == query]
        if not candidates:
            candidates = [c for c in choices if c.casefold().startswith(query)]
        if not candidates:
            candidates = [c for c in choices if query in c.casefold()]
        if not candidates:
            scores = [(SequenceMatcher(None, query, c.casefold()).ratio(), c) for c in choices]
            candidates = [
                c for score, c in sorted(scores, key=lambda x: (-x[0], x[1])) if score >= 0.6
            ]
        if not candidates:
            raise typer.BadParameter(
                f"No {label} matches {value!r}. Available: {', '.join(choices)}"
            )
        if len(candidates) == 1:
            typer.echo(f"Using {label}: {candidates[0]}", err=True)
            return candidates[0]
    reason = f"Choose {label}" if value is None else f"{label} {value!r} needs a choice"
    if not prompt or (ctx is not None and ctx.meta.get("no_input")) or not is_interactive():
        raise typer.BadParameter(f"{reason}. Use an exact value: {', '.join(candidates)}")
    typer.echo(reason + ":", err=True)
    for i, candidate in enumerate(candidates, 1):
        detail = f"  {descriptions[candidate]}" if descriptions else ""
        typer.echo(f"  {i}. {candidate}{detail}", err=True)
    while True:
        # Typer delegates the final prompt character to input(), which uses stdout.
        with redirect_stdout(sys.stderr):
            answer = typer.prompt("Select a number (q to cancel)", type=str, err=True)
        if answer.casefold() == "q":
            raise typer.Abort()
        if answer.isdecimal() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        typer.echo(f"Enter a number from 1 to {len(candidates)}, or q.", err=True)


def adapter(value: str, kinds: Iterable[str], label: str, ctx: typer.Context | None) -> str:
    """Resolve only the adapter kind, preserving the model suffix byte for byte."""
    kind, separator, model = value.partition(":")
    kind = resolve(kind, kinds, label, ctx=ctx)
    if kind != "fake" and (not separator or not model):
        raise typer.BadParameter(f"{label} {kind!r} requires {kind}:<model>.")
    if kind == "fake" and separator:
        raise typer.BadParameter(f"{label} fake does not accept a model suffix.")
    return kind + separator + model


class SelectionGroup(TyperGroup):
    """Resolve registered command names without rewriting option tokens or values."""

    def resolve_command(self, ctx, args):
        if args and not args[0].startswith("-") and not ctx.resilient_parsing:
            name = resolve(
                args[0],
                self.commands,
                "command",
                ctx=ctx,
                prompt=not any(a in ("--help", "--no-input") for a in args),
            )
            return name, self.commands[name], args[1:]
        return super().resolve_command(ctx, args)
