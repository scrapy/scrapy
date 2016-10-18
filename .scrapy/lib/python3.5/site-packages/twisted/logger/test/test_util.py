# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._util}.
"""

from twisted.trial import unittest

from .._observer import LogPublisher
from .._util import formatTrace



class UtilTests(unittest.TestCase):
    """
    Utility tests.
    """

    def test_trace(self):
        """
        Tracing keeps track of forwarding done by the publisher.
        """
        publisher = LogPublisher()

        event = dict(log_trace=[])

        o1 = lambda e: None

        def o2(e):
            self.assertIs(e, event)
            self.assertEqual(
                e["log_trace"],
                [
                    (publisher, o1),
                    (publisher, o2),
                    # Event hasn't been sent to o3 yet
                ]
            )

        def o3(e):
            self.assertIs(e, event)
            self.assertEqual(
                e["log_trace"],
                [
                    (publisher, o1),
                    (publisher, o2),
                    (publisher, o3),
                ]
            )

        publisher.addObserver(o1)
        publisher.addObserver(o2)
        publisher.addObserver(o3)
        publisher(event)


    def test_formatTrace(self):
        """
        Format trace as string.
        """
        event = dict(log_trace=[])

        def noOp(e):
            pass

        o1, o2, o3, o4, o5 = noOp, noOp, noOp, noOp, noOp

        o1.name = "root/o1"
        o2.name = "root/p1/o2"
        o3.name = "root/p1/o3"
        o4.name = "root/p1/p2/o4"
        o5.name = "root/o5"

        def testObserver(e):
            self.assertIs(e, event)
            trace = formatTrace(e["log_trace"])
            self.assertEqual(
                trace,
                (
                    u"{root} ({root.name})\n"
                    u"  -> {o1} ({o1.name})\n"
                    u"  -> {p1} ({p1.name})\n"
                    u"    -> {o2} ({o2.name})\n"
                    u"    -> {o3} ({o3.name})\n"
                    u"    -> {p2} ({p2.name})\n"
                    u"      -> {o4} ({o4.name})\n"
                    u"  -> {o5} ({o5.name})\n"
                    u"  -> {oTest}\n"
                ).format(
                    root=root,
                    o1=o1, o2=o2, o3=o3, o4=o4, o5=o5,
                    p1=p1, p2=p2,
                    oTest=oTest
                )
            )
        oTest = testObserver

        p2 = LogPublisher(o4)
        p1 = LogPublisher(o2, o3, p2)

        p2.name = "root/p1/p2/"
        p1.name = "root/p1/"

        root = LogPublisher(o1, p1, o5, oTest)
        root.name = "root/"
        root(event)
