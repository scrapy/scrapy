"""Non-keyboard events used in bpython curtsies REPL"""

import time
from typing import Sequence

import curtsies.events


class ReloadEvent(curtsies.events.Event):
    """Request to rerun REPL session ASAP because imported modules changed"""

    def __init__(self, files_modified: Sequence[str] = ("?",)) -> None:
        self.files_modified = files_modified

    def __repr__(self) -> str:
        return "<ReloadEvent from {}>".format(" & ".join(self.files_modified))


class RefreshRequestEvent(curtsies.events.Event):
    """Request to refresh REPL display ASAP"""

    def __repr__(self) -> str:
        return "<RefreshRequestEvent for now>"


class ScheduledRefreshRequestEvent(curtsies.events.ScheduledEvent):
    """Request to refresh the REPL display at some point in the future

    Used to schedule the disappearance of status bar message that only shows
    for a few seconds"""

    def __init__(self, when: float) -> None:
        super().__init__(when)

    def __repr__(self) -> str:
        return "<RefreshRequestEvent for {} seconds from now>".format(
            self.when - time.time()
        )


class RunStartupFileEvent(curtsies.events.Event):
    """Request to run the startup file."""


class UndoEvent(curtsies.events.Event):
    """Request to undo."""

    def __init__(self, n: int = 1) -> None:
        self.n = n
