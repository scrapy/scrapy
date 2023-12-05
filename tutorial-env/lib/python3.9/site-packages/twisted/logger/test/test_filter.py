# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._filter}.
"""

from typing import Iterable, List, Tuple, Union, cast

from zope.interface import implementer
from zope.interface.exceptions import BrokenMethodImplementation
from zope.interface.verify import verifyObject

from constantly import NamedConstant  # type: ignore[import]

from twisted.trial import unittest
from .._filter import (
    FilteringLogObserver,
    ILogFilterPredicate,
    LogLevelFilterPredicate,
    PredicateResult,
)
from .._interfaces import ILogObserver, LogEvent
from .._levels import InvalidLogLevelError, LogLevel
from .._observer import LogPublisher, bitbucketLogObserver


class FilteringLogObserverTests(unittest.TestCase):
    """
    Tests for L{FilteringLogObserver}.
    """

    def test_interface(self) -> None:
        """
        L{FilteringLogObserver} is an L{ILogObserver}.
        """
        observer = FilteringLogObserver(cast(ILogObserver, lambda e: None), ())
        try:
            verifyObject(ILogObserver, observer)
        except BrokenMethodImplementation as e:
            self.fail(e)

    def filterWith(
        self, filters: Iterable[str], other: bool = False
    ) -> Union[List[int], Tuple[List[int], List[int]]]:
        """
        Apply a set of pre-defined filters on a known set of events and return
        the filtered list of event numbers.

        The pre-defined events are four events with a C{count} attribute set to
        C{0}, C{1}, C{2}, and C{3}.

        @param filters: names of the filters to apply.
            Options are:
                - C{"twoMinus"} (count <=2),
                - C{"twoPlus"} (count >= 2),
                - C{"notTwo"} (count != 2),
                - C{"no"} (False).
        @param other: Whether to return a list of filtered events as well.

        @return: event numbers or 2-tuple of lists of event numbers.
        """
        events: List[LogEvent] = [
            dict(count=0),
            dict(count=1),
            dict(count=2),
            dict(count=3),
        ]

        class Filters:
            @staticmethod
            def twoMinus(event: LogEvent) -> NamedConstant:
                """
                count <= 2

                @param event: an event

                @return: L{PredicateResult.yes} if C{event["count"] <= 2},
                    otherwise L{PredicateResult.maybe}.
                """
                if event["count"] <= 2:
                    return PredicateResult.yes
                return PredicateResult.maybe

            @staticmethod
            def twoPlus(event: LogEvent) -> NamedConstant:
                """
                count >= 2

                @param event: an event

                @return: L{PredicateResult.yes} if C{event["count"] >= 2},
                    otherwise L{PredicateResult.maybe}.
                """
                if event["count"] >= 2:
                    return PredicateResult.yes
                return PredicateResult.maybe

            @staticmethod
            def notTwo(event: LogEvent) -> NamedConstant:
                """
                count != 2

                @param event: an event

                @return: L{PredicateResult.yes} if C{event["count"] != 2},
                    otherwise L{PredicateResult.maybe}.
                """
                if event["count"] == 2:
                    return PredicateResult.no
                return PredicateResult.maybe

            @staticmethod
            def no(event: LogEvent) -> NamedConstant:
                """
                No way, man.

                @param event: an event

                @return: L{PredicateResult.no}
                """
                return PredicateResult.no

            @staticmethod
            def bogus(event: LogEvent) -> NamedConstant:
                """
                Bogus result.

                @param event: an event

                @return: something other than a valid predicate result.
                """
                return None

        predicates = (getattr(Filters, f) for f in filters)
        eventsSeen: List[LogEvent] = []
        eventsNotSeen: List[LogEvent] = []
        trackingObserver = cast(ILogObserver, eventsSeen.append)

        if other:
            negativeObserver = cast(ILogObserver, eventsNotSeen.append)
        else:
            negativeObserver = bitbucketLogObserver

        filteringObserver = FilteringLogObserver(
            trackingObserver, predicates, negativeObserver
        )

        for e in events:
            filteringObserver(e)

        if other:
            return (
                [cast(int, e["count"]) for e in eventsSeen],
                [cast(int, e["count"]) for e in eventsNotSeen],
            )
        else:
            return [cast(int, e["count"]) for e in eventsSeen]

    def test_shouldLogEventNoFilters(self) -> None:
        """
        No filters: all events come through.
        """
        self.assertEqual(self.filterWith([]), [0, 1, 2, 3])

    def test_shouldLogEventNoFilter(self) -> None:
        """
        Filter with negative predicate result.
        """
        self.assertEqual(self.filterWith(["notTwo"]), [0, 1, 3])

    def test_shouldLogEventOtherObserver(self) -> None:
        """
        Filtered results get sent to the other observer, if passed.
        """
        self.assertEqual(self.filterWith(["notTwo"], True), ([0, 1, 3], [2]))

    def test_shouldLogEventYesFilter(self) -> None:
        """
        Filter with positive predicate result.
        """
        self.assertEqual(self.filterWith(["twoPlus"]), [0, 1, 2, 3])

    def test_shouldLogEventYesNoFilter(self) -> None:
        """
        Series of filters with positive and negative predicate results.
        """
        self.assertEqual(self.filterWith(["twoPlus", "no"]), [2, 3])

    def test_shouldLogEventYesYesNoFilter(self) -> None:
        """
        Series of filters with positive, positive and negative predicate
        results.
        """
        self.assertEqual(self.filterWith(["twoPlus", "twoMinus", "no"]), [0, 1, 2, 3])

    def test_shouldLogEventBadPredicateResult(self) -> None:
        """
        Filter with invalid predicate result.
        """
        self.assertRaises(TypeError, self.filterWith, ["bogus"])

    def test_call(self) -> None:
        """
        Test filtering results from each predicate type.
        """
        e: LogEvent = dict(obj=object())

        def callWithPredicateResult(result: NamedConstant) -> List[LogEvent]:
            seen: List[LogEvent] = []
            observer = FilteringLogObserver(
                cast(ILogObserver, lambda e: seen.append(e)),
                (cast(ILogFilterPredicate, lambda e: result),),
            )
            observer(e)
            return seen

        self.assertIn(e, callWithPredicateResult(PredicateResult.yes))
        self.assertIn(e, callWithPredicateResult(PredicateResult.maybe))
        self.assertNotIn(e, callWithPredicateResult(PredicateResult.no))

    def test_trace(self) -> None:
        """
        Tracing keeps track of forwarding through the filtering observer.
        """
        event: LogEvent = dict(log_trace=[])

        oYes = cast(ILogObserver, lambda e: None)
        oNo = cast(ILogObserver, lambda e: None)

        @implementer(ILogObserver)
        def testObserver(e: LogEvent) -> None:
            self.assertIs(e, event)
            self.assertEqual(
                event["log_trace"],
                [
                    (publisher, yesFilter),
                    (yesFilter, oYes),
                    (publisher, noFilter),
                    # ... noFilter doesn't call oNo
                    (publisher, oTest),
                ],
            )

        oTest = testObserver

        yesFilter = FilteringLogObserver(
            oYes, (cast(ILogFilterPredicate, lambda e: PredicateResult.yes),)
        )
        noFilter = FilteringLogObserver(
            oNo, (cast(ILogFilterPredicate, lambda e: PredicateResult.no),)
        )

        publisher = LogPublisher(yesFilter, noFilter, testObserver)
        publisher(event)


class LogLevelFilterPredicateTests(unittest.TestCase):
    """
    Tests for L{LogLevelFilterPredicate}.
    """

    def test_defaultLogLevel(self) -> None:
        """
        Default log level is used.
        """
        predicate = LogLevelFilterPredicate()

        # Test using both "" and None as default namespace, because None was the
        # documented default value in the past.

        for default in ("", cast(str, None)):
            self.assertEqual(
                predicate.logLevelForNamespace(default), predicate.defaultLogLevel
            )
            self.assertEqual(
                predicate.logLevelForNamespace("rocker.cool.namespace"),
                predicate.defaultLogLevel,
            )

    def test_setLogLevel(self) -> None:
        """
        Setting and retrieving log levels.
        """
        predicate = LogLevelFilterPredicate()

        # Test using both "" and None as default namespace, because None was the
        # documented default value in the past.

        for default in ("", cast(str, None)):
            predicate.setLogLevelForNamespace(default, LogLevel.error)
            predicate.setLogLevelForNamespace("twext.web2", LogLevel.debug)
            predicate.setLogLevelForNamespace("twext.web2.dav", LogLevel.warn)

            self.assertEqual(predicate.logLevelForNamespace(""), LogLevel.error)
            self.assertEqual(
                predicate.logLevelForNamespace(cast(str, None)), LogLevel.error
            )
            self.assertEqual(predicate.logLevelForNamespace("twisted"), LogLevel.error)
            self.assertEqual(
                predicate.logLevelForNamespace("twext.web2"), LogLevel.debug
            )
            self.assertEqual(
                predicate.logLevelForNamespace("twext.web2.dav"), LogLevel.warn
            )
            self.assertEqual(
                predicate.logLevelForNamespace("twext.web2.dav.test"), LogLevel.warn
            )
            self.assertEqual(
                predicate.logLevelForNamespace("twext.web2.dav.test1.test2"),
                LogLevel.warn,
            )

    def test_setInvalidLogLevel(self) -> None:
        """
        Can't pass invalid log levels to C{setLogLevelForNamespace()}.
        """
        predicate = LogLevelFilterPredicate()

        self.assertRaises(
            InvalidLogLevelError,
            predicate.setLogLevelForNamespace,
            "twext.web2",
            object(),
        )

        # Level must be a constant, not the name of a constant
        self.assertRaises(
            InvalidLogLevelError,
            predicate.setLogLevelForNamespace,
            "twext.web2",
            "debug",
        )

    def test_clearLogLevels(self) -> None:
        """
        Clearing log levels.
        """
        predicate = LogLevelFilterPredicate()

        predicate.setLogLevelForNamespace("twext.web2", LogLevel.debug)
        predicate.setLogLevelForNamespace("twext.web2.dav", LogLevel.error)

        predicate.clearLogLevels()

        self.assertEqual(
            predicate.logLevelForNamespace("twisted"), predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2"), predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav"), predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav.test"),
            predicate.defaultLogLevel,
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav.test1.test2"),
            predicate.defaultLogLevel,
        )

    def test_filtering(self) -> None:
        """
        Events are filtered based on log level/namespace.
        """
        predicate = LogLevelFilterPredicate()

        predicate.setLogLevelForNamespace("", LogLevel.error)
        predicate.setLogLevelForNamespace("twext.web2", LogLevel.debug)
        predicate.setLogLevelForNamespace("twext.web2.dav", LogLevel.warn)

        def checkPredicate(
            namespace: str, level: NamedConstant, expectedResult: NamedConstant
        ) -> None:
            event: LogEvent = dict(log_namespace=namespace, log_level=level)
            self.assertEqual(expectedResult, predicate(event))

        checkPredicate("", LogLevel.debug, PredicateResult.no)
        checkPredicate(cast(str, None), LogLevel.debug, PredicateResult.no)
        checkPredicate("", LogLevel.error, PredicateResult.no)
        checkPredicate(cast(str, None), LogLevel.error, PredicateResult.no)

        checkPredicate("twext.web2", LogLevel.debug, PredicateResult.maybe)
        checkPredicate("twext.web2", LogLevel.error, PredicateResult.maybe)

        checkPredicate("twext.web2.dav", LogLevel.debug, PredicateResult.no)
        checkPredicate("twext.web2.dav", LogLevel.error, PredicateResult.maybe)

        checkPredicate("", LogLevel.critical, PredicateResult.no)
        checkPredicate(cast(str, None), LogLevel.critical, PredicateResult.no)
        checkPredicate("twext.web2", None, PredicateResult.no)
