"""What code ran: a process-wide monitor that records every code object entered while a
recording is active, at no cost after the first entry.

`sys.monitoring` reports the first entry into each function; the callback stores the code
object in every active recording and disables further reports for that code object. A recording
re-enables reports on entry, so a function already seen by an earlier recording is reported
again to the new one. Recordings nest: an inner one and its outer both receive every entry.
Monitoring is per interpreter, so code entered on any thread while a recording is active is
attributed to it, which invalidates more, never less.
"""

from __future__ import annotations

import sys
from types import CodeType
from typing import Self

TOOL = 3
_active: list[set[CodeType]] = []
_enabled = False


def _on_start(code: CodeType, offset: int) -> object:
    for codes in _active:
        codes.add(code)
    return sys.monitoring.DISABLE


def _enable() -> None:
    global _enabled
    if _enabled:
        return
    mon = sys.monitoring
    mon.use_tool_id(TOOL, "triplum")
    mon.register_callback(TOOL, mon.events.PY_START, _on_start)
    mon.set_events(TOOL, mon.events.PY_START)
    _enabled = True


class Recording:
    """The set of code objects entered between `start()` and `stop()`; usable as a context
    manager, or held open by hand across the pulls of a stream."""

    def __init__(self) -> None:
        self.codes: set[CodeType] = set()
        self.open = False

    def start(self) -> Self:
        _enable()
        if not self.open:
            _active.append(self.codes)
            self.open = True
        sys.monitoring.restart_events()
        return self

    def stop(self) -> None:
        if self.open:
            _active.remove(self.codes)
            self.open = False

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()
