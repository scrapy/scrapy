# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._util}.
"""

from zope.interface import implementer

from twisted.trial import unittest
from .._interfaces import ILogObserver, LogEvent
from .._observer import LogPublisher
from .._util import formatTrace


class UtilTests(unittest.TestCase):
    """
    Utility tests.
    """

    def test_trace(self) -> None:
        """
        Tracing keeps track of forwarding done by the publisher.
        """
        publisher = LogPublisher()

        event: LogEvent = dict(log_trace=[])

        @implementer(ILogObserver)
        def o1(e: LogEvent) -> None:
            pass

        @implementer(ILogObserver)
        def o2(e: LogEvent) -> None:
            self.assertIs(e, event)
            self.assertEqual(
                e["log_trace"],
                [
                    (publisher, o1),
                    (publisher, o2),
                    # Event hasn't been sent to o3 yet
                ],
            )

        @implementer(ILogObserver)
        def o3(e: LogEvent) -> None:
            self.assertIs(e, event)
            self.assertEqual(
                e["log_trace"],
                [
                    (publisher, o1),
                    (publisher, o2),
                    (publisher, o3),
                ],
            )

        publisher.addObserver(o1)
        publisher.addObserver(o2)
        publisher.addObserver(o3)
        publisher(event)

    def test_formatTrace(self) -> None:
        """
        Format trace as string.
        """
        event: LogEvent = dict(log_trace=[])

        @implementer(ILogObserver)
        def o1(e: LogEvent) -> None:
            pass

        @implementer(ILogObserver)
        def o2(e: LogEvent) -> None:
            pass

        @implementer(ILogObserver)
        def o3(e: LogEvent) -> None:
            pass

        @implementer(ILogObserver)
        def o4(e: LogEvent) -> None:
            pass

        @implementer(ILogObserver)
        def o5(e: LogEvent) -> None:
            pass

        o1.name = "root/o1"  # type: ignore[attr-defined]
        o2.name = "root/p1/o2"
        o3.name = "root/p1/o3"
        o4.name = "root/p1/p2/o4"
        o5.name = "root/o5"

        @implementer(ILogObserver)
        def testObserver(e: LogEvent) -> None:
            self.assertIs(e, event)
            trace = formatTrace(e["log_trace"])
            self.assertEqual(
                trace,
                (
                    "{root} ({root.name})\n"
                    "  -> {o1} ({o1.name})\n"
                    "  -> {p1} ({p1.name})\n"
                    "    -> {o2} ({o2.name})\n"
                    "    -> {o3} ({o3.name})\n"
                    "    -> {p2} ({p2.name})\n"
                    "      -> {o4} ({o4.name})\n"
                    "  -> {o5} ({o5.name})\n"
                    "  -> {oTest}\n"
                ).format(
                    root=root,
                    o1=o1,
                    o2=o2,
                    o3=o3,
                    o4=o4,
                    o5=o5,
                    p1=p1,
                    p2=p2,
                    oTest=oTest,
                ),
            )

        oTest = testObserver

        p2 = LogPublisher(o4)
        p1 = LogPublisher(o2, o3, p2)

        p2.name = "root/p1/p2/"  # type: ignore[attr-defined]
        p1.name = "root/p1/"  # type: ignore[attr-defined]

        root = LogPublisher(o1, p1, o5, oTest)
        root.name = "root/"  # type: ignore[attr-defined]
        root(event)
