"""
Extensions for debugging Scrapy

See documentation in docs/topics/extensions.rst
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import traceback
from pdb import Pdb
from typing import TYPE_CHECKING

from scrapy.utils.engine import format_engine_status
from scrapy.utils.trackref import format_live_refs

if TYPE_CHECKING:
    from types import FrameType

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


class StackTraceDump:
    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler
        try:
            signal.signal(signal.SIGUSR2, self.dump_stacktrace)  # type: ignore[attr-defined]
            signal.signal(signal.SIGQUIT, self.dump_stacktrace)  # type: ignore[attr-defined]
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def dump_stacktrace(self, signum: int, frame: FrameType | None) -> None:
        assert self.crawler.engine
        log_args = {
            "stackdumps": self._thread_stacks(),
            "enginestatus": format_engine_status(self.crawler.engine),
            "liverefs": format_live_refs(),
        }
        logger.info(
            "Dumping stack trace and engine status\n"
            "%(enginestatus)s\n%(liverefs)s\n%(stackdumps)s",
            log_args,
            extra={"crawler": self.crawler},
        )

    def _thread_stacks(self) -> str:
        id2name = {th.ident: th.name for th in threading.enumerate()}
        dumps = ""
        for id_, frame in sys._current_frames().items():
            name = id2name.get(id_, "")
            dump = "".join(traceback.format_stack(frame))
            dumps += f"# Thread: {name}({id_})\n{dump}\n"
        return dumps


class Debugger:
    def __init__(self) -> None:
        try:
            signal.signal(signal.SIGUSR2, self._enter_debugger)  # type: ignore[attr-defined]
        except AttributeError:
            # win32 platforms don't support SIGUSR signals
            pass

    def _enter_debugger(self, signum: int, frame: FrameType | None) -> None:
        assert frame
        Pdb().set_trace(frame.f_back)  # noqa: T100
