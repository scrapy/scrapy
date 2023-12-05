# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._observer}.
"""

from typing import Dict, List, Tuple, cast

from zope.interface import implementer
from zope.interface.exceptions import BrokenMethodImplementation
from zope.interface.verify import verifyObject

from twisted.trial import unittest
from .._interfaces import ILogObserver, LogEvent
from .._logger import Logger
from .._observer import LogPublisher


class LogPublisherTests(unittest.TestCase):
    """
    Tests for L{LogPublisher}.
    """

    def test_interface(self) -> None:
        """
        L{LogPublisher} is an L{ILogObserver}.
        """
        publisher = LogPublisher()
        try:
            verifyObject(ILogObserver, publisher)
        except BrokenMethodImplementation as e:
            self.fail(e)

    def test_observers(self) -> None:
        """
        L{LogPublisher.observers} returns the observers.
        """
        o1 = cast(ILogObserver, lambda e: None)
        o2 = cast(ILogObserver, lambda e: None)

        publisher = LogPublisher(o1, o2)
        self.assertEqual({o1, o2}, set(publisher._observers))

    def test_addObserver(self) -> None:
        """
        L{LogPublisher.addObserver} adds an observer.
        """
        o1 = cast(ILogObserver, lambda e: None)
        o2 = cast(ILogObserver, lambda e: None)
        o3 = cast(ILogObserver, lambda e: None)

        publisher = LogPublisher(o1, o2)
        publisher.addObserver(o3)
        self.assertEqual({o1, o2, o3}, set(publisher._observers))

    def test_addObserverNotCallable(self) -> None:
        """
        L{LogPublisher.addObserver} refuses to add an observer that's
        not callable.
        """
        publisher = LogPublisher()
        self.assertRaises(TypeError, publisher.addObserver, object())

    def test_removeObserver(self) -> None:
        """
        L{LogPublisher.removeObserver} removes an observer.
        """
        o1 = cast(ILogObserver, lambda e: None)
        o2 = cast(ILogObserver, lambda e: None)
        o3 = cast(ILogObserver, lambda e: None)

        publisher = LogPublisher(o1, o2, o3)
        publisher.removeObserver(o2)
        self.assertEqual({o1, o3}, set(publisher._observers))

    def test_removeObserverNotRegistered(self) -> None:
        """
        L{LogPublisher.removeObserver} removes an observer that is not
        registered.
        """
        o1 = cast(ILogObserver, lambda e: None)
        o2 = cast(ILogObserver, lambda e: None)
        o3 = cast(ILogObserver, lambda e: None)

        publisher = LogPublisher(o1, o2)
        publisher.removeObserver(o3)
        self.assertEqual({o1, o2}, set(publisher._observers))

    def test_fanOut(self) -> None:
        """
        L{LogPublisher} calls its observers.
        """
        event = dict(foo=1, bar=2)

        events1: List[LogEvent] = []
        events2: List[LogEvent] = []
        events3: List[LogEvent] = []

        o1 = cast(ILogObserver, events1.append)
        o2 = cast(ILogObserver, events2.append)
        o3 = cast(ILogObserver, events3.append)

        publisher = LogPublisher(o1, o2, o3)
        publisher(event)
        self.assertIn(event, events1)
        self.assertIn(event, events2)
        self.assertIn(event, events3)

    def test_observerRaises(self) -> None:
        """
        Observer raises an exception during fan out: a failure is logged, but
        not re-raised.  Life goes on.
        """
        event = dict(foo=1, bar=2)
        exception = RuntimeError("ARGH! EVIL DEATH!")

        events: List[LogEvent] = []

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            shouldRaise = not events
            events.append(event)
            if shouldRaise:
                raise exception

        collector: List[LogEvent] = []

        publisher = LogPublisher(observer, cast(ILogObserver, collector.append))
        publisher(event)

        # Verify that the observer saw my event
        self.assertIn(event, events)

        # Verify that the observer raised my exception
        errors = [e["log_failure"] for e in collector if "log_failure" in e]
        self.assertEqual(len(errors), 1)
        self.assertIs(errors[0].value, exception)
        # Make sure the exceptional observer does not receive its own error.
        self.assertEqual(len(events), 1)

    def test_observerRaisesAndLoggerHatesMe(self) -> None:
        """
        Observer raises an exception during fan out and the publisher's Logger
        pukes when the failure is reported.  The exception does not propagate
        back to the caller.
        """
        event = dict(foo=1, bar=2)
        exception = RuntimeError("ARGH! EVIL DEATH!")

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            raise RuntimeError("Sad panda")

        class GurkLogger(Logger):
            def failure(self, *args: object, **kwargs: object) -> None:
                raise exception

        publisher = LogPublisher(observer)
        publisher.log = GurkLogger()
        publisher(event)

        # Here, the lack of an exception thus far is a success, of sorts

    def test_trace(self) -> None:
        """
        Tracing keeps track of forwarding to observers.
        """
        event = dict(foo=1, bar=2, log_trace=[])

        traces: Dict[int, Tuple[Tuple[Logger, ILogObserver]]] = {}

        # Copy trace to a tuple; otherwise, both observers will store the same
        # mutable list, and we won't be able to see o1's view distinctly.

        @implementer(ILogObserver)
        def o1(e: LogEvent) -> None:
            traces.setdefault(
                1, cast(Tuple[Tuple[Logger, ILogObserver]], tuple(e["log_trace"]))
            )

        @implementer(ILogObserver)
        def o2(e: LogEvent) -> None:
            traces.setdefault(
                2, cast(Tuple[Tuple[Logger, ILogObserver]], tuple(e["log_trace"]))
            )

        publisher = LogPublisher(o1, o2)
        publisher(event)

        self.assertEqual(traces[1], ((publisher, o1),))
        self.assertEqual(traces[2], ((publisher, o1), (publisher, o2)))
