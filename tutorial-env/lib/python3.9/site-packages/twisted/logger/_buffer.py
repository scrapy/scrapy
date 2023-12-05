# -*- test-case-name: twisted.logger.test.test_buffer -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Log observer that maintains a buffer.
"""

from collections import deque
from typing import Deque, Optional

from zope.interface import implementer

from ._interfaces import ILogObserver, LogEvent

_DEFAULT_BUFFER_MAXIMUM = 64 * 1024


@implementer(ILogObserver)
class LimitedHistoryLogObserver:
    """
    L{ILogObserver} that stores events in a buffer of a fixed size::

        >>> from twisted.logger import LimitedHistoryLogObserver
        >>> history = LimitedHistoryLogObserver(5)
        >>> for n in range(10): history({'n': n})
        ...
        >>> repeats = []
        >>> history.replayTo(repeats.append)
        >>> len(repeats)
        5
        >>> repeats
        [{'n': 5}, {'n': 6}, {'n': 7}, {'n': 8}, {'n': 9}]
        >>>
    """

    def __init__(self, size: Optional[int] = _DEFAULT_BUFFER_MAXIMUM) -> None:
        """
        @param size: The maximum number of events to buffer.  If L{None}, the
            buffer is unbounded.
        """
        self._buffer: Deque[LogEvent] = deque(maxlen=size)

    def __call__(self, event: LogEvent) -> None:
        self._buffer.append(event)

    def replayTo(self, otherObserver: ILogObserver) -> None:
        """
        Re-play the buffered events to another log observer.

        @param otherObserver: An observer to replay events to.
        """
        for event in self._buffer:
            otherObserver(event)
