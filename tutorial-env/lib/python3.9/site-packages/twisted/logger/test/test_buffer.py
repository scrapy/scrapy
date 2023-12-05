# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._buffer}.
"""

from typing import List, cast

from zope.interface.exceptions import BrokenMethodImplementation
from zope.interface.verify import verifyObject

from twisted.trial import unittest
from .._buffer import LimitedHistoryLogObserver
from .._interfaces import ILogObserver, LogEvent


class LimitedHistoryLogObserverTests(unittest.TestCase):
    """
    Tests for L{LimitedHistoryLogObserver}.
    """

    def test_interface(self) -> None:
        """
        L{LimitedHistoryLogObserver} provides L{ILogObserver}.
        """
        observer = LimitedHistoryLogObserver(0)
        try:
            verifyObject(ILogObserver, observer)
        except BrokenMethodImplementation as e:
            self.fail(e)

    def test_order(self) -> None:
        """
        L{LimitedHistoryLogObserver} saves history in the order it is received.
        """
        size = 4
        events = [dict(n=n) for n in range(size // 2)]
        observer = LimitedHistoryLogObserver(size)

        for event in events:
            observer(event)

        outEvents: List[LogEvent] = []
        observer.replayTo(cast(ILogObserver, outEvents.append))
        self.assertEqual(events, outEvents)

    def test_limit(self) -> None:
        """
        When more events than a L{LimitedHistoryLogObserver}'s maximum size are
        buffered, older events will be dropped.
        """
        size = 4
        events = [dict(n=n) for n in range(size * 2)]
        observer = LimitedHistoryLogObserver(size)

        for event in events:
            observer(event)

        outEvents: List[LogEvent] = []
        observer.replayTo(cast(ILogObserver, outEvents.append))
        self.assertEqual(events[-size:], outEvents)
