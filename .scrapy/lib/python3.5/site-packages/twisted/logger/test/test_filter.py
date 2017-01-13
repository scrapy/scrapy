# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._filter}.
"""

from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.trial import unittest

from .._levels import InvalidLogLevelError
from .._levels import LogLevel
from .._observer import ILogObserver
from .._observer import LogPublisher
from .._filter import FilteringLogObserver
from .._filter import PredicateResult
from .._filter import LogLevelFilterPredicate



class FilteringLogObserverTests(unittest.TestCase):
    """
    Tests for L{FilteringLogObserver}.
    """

    def test_interface(self):
        """
        L{FilteringLogObserver} is an L{ILogObserver}.
        """
        observer = FilteringLogObserver(lambda e: None, ())
        try:
            verifyObject(ILogObserver, observer)
        except BrokenMethodImplementation as e:
            self.fail(e)


    def filterWith(self, filters, other=False):
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

        @type filters: iterable of str

        @param other: Whether to return a list of filtered events as well.
        @type other: L{bool}

        @return: event numbers or 2-tuple of lists of event numbers.
        @rtype: L{list} of L{int} or 2-L{tuple} of L{list} of L{int}
        """
        events = [
            dict(count=0),
            dict(count=1),
            dict(count=2),
            dict(count=3),
        ]

        class Filters(object):
            @staticmethod
            def twoMinus(event):
                """
                count <= 2

                @param event: an event
                @type event: dict

                @return: L{PredicateResult.yes} if C{event["count"] <= 2},
                    otherwise L{PredicateResult.maybe}.
                """
                if event["count"] <= 2:
                    return PredicateResult.yes
                return PredicateResult.maybe

            @staticmethod
            def twoPlus(event):
                """
                count >= 2

                @param event: an event
                @type event: dict

                @return: L{PredicateResult.yes} if C{event["count"] >= 2},
                    otherwise L{PredicateResult.maybe}.
                """
                if event["count"] >= 2:
                    return PredicateResult.yes
                return PredicateResult.maybe

            @staticmethod
            def notTwo(event):
                """
                count != 2

                @param event: an event
                @type event: dict

                @return: L{PredicateResult.yes} if C{event["count"] != 2},
                    otherwise L{PredicateResult.maybe}.
                """
                if event["count"] == 2:
                    return PredicateResult.no
                return PredicateResult.maybe

            @staticmethod
            def no(event):
                """
                No way, man.

                @param event: an event
                @type event: dict

                @return: L{PredicateResult.no}
                """
                return PredicateResult.no

            @staticmethod
            def bogus(event):
                """
                Bogus result.

                @param event: an event
                @type event: dict

                @return: something other than a valid predicate result.
                """
                return None

        predicates = (getattr(Filters, f) for f in filters)
        eventsSeen = []
        eventsNotSeen = []
        trackingObserver = eventsSeen.append
        if other:
            extra = [eventsNotSeen.append]
        else:
            extra = []
        filteringObserver = FilteringLogObserver(
            trackingObserver, predicates, *extra
        )
        for e in events:
            filteringObserver(e)

        if extra:
            return (
                [e["count"] for e in eventsSeen],
                [e["count"] for e in eventsNotSeen],
            )
        return [e["count"] for e in eventsSeen]


    def test_shouldLogEventNoFilters(self):
        """
        No filters: all events come through.
        """
        self.assertEqual(self.filterWith([]), [0, 1, 2, 3])


    def test_shouldLogEventNoFilter(self):
        """
        Filter with negative predicate result.
        """
        self.assertEqual(self.filterWith(["notTwo"]), [0, 1, 3])


    def test_shouldLogEventOtherObserver(self):
        """
        Filtered results get sent to the other observer, if passed.
        """
        self.assertEqual(self.filterWith(["notTwo"], True), ([0, 1, 3], [2]))


    def test_shouldLogEventYesFilter(self):
        """
        Filter with positive predicate result.
        """
        self.assertEqual(self.filterWith(["twoPlus"]), [0, 1, 2, 3])


    def test_shouldLogEventYesNoFilter(self):
        """
        Series of filters with positive and negative predicate results.
        """
        self.assertEqual(self.filterWith(["twoPlus", "no"]), [2, 3])


    def test_shouldLogEventYesYesNoFilter(self):
        """
        Series of filters with positive, positive and negative predicate
        results.
        """
        self.assertEqual(
            self.filterWith(["twoPlus", "twoMinus", "no"]),
            [0, 1, 2, 3]
        )


    def test_shouldLogEventBadPredicateResult(self):
        """
        Filter with invalid predicate result.
        """
        self.assertRaises(TypeError, self.filterWith, ["bogus"])


    def test_call(self):
        """
        Test filtering results from each predicate type.
        """
        e = dict(obj=object())

        def callWithPredicateResult(result):
            seen = []
            observer = FilteringLogObserver(
                lambda e: seen.append(e),
                (lambda e: result,)
            )
            observer(e)
            return seen

        self.assertIn(e, callWithPredicateResult(PredicateResult.yes))
        self.assertIn(e, callWithPredicateResult(PredicateResult.maybe))
        self.assertNotIn(e, callWithPredicateResult(PredicateResult.no))


    def test_trace(self):
        """
        Tracing keeps track of forwarding through the filtering observer.
        """
        event = dict(log_trace=[])

        oYes = lambda e: None
        oNo = lambda e: None

        def testObserver(e):
            self.assertIs(e, event)
            self.assertEqual(
                event["log_trace"],
                [
                    (publisher, yesFilter),
                    (yesFilter, oYes),
                    (publisher, noFilter),
                    # ... noFilter doesn't call oNo
                    (publisher, oTest),
                ]
            )
        oTest = testObserver

        yesFilter = FilteringLogObserver(
            oYes,
            (lambda e: PredicateResult.yes,)
        )
        noFilter = FilteringLogObserver(
            oNo,
            (lambda e: PredicateResult.no,)
        )

        publisher = LogPublisher(yesFilter, noFilter, testObserver)
        publisher(event)



class LogLevelFilterPredicateTests(unittest.TestCase):
    """
    Tests for L{LogLevelFilterPredicate}.
    """

    def test_defaultLogLevel(self):
        """
        Default log level is used.
        """
        predicate = LogLevelFilterPredicate()

        self.assertEqual(
            predicate.logLevelForNamespace(None),
            predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace(""),
            predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("rocker.cool.namespace"),
            predicate.defaultLogLevel
        )


    def test_setLogLevel(self):
        """
        Setting and retrieving log levels.
        """
        predicate = LogLevelFilterPredicate()

        predicate.setLogLevelForNamespace(None, LogLevel.error)
        predicate.setLogLevelForNamespace("twext.web2", LogLevel.debug)
        predicate.setLogLevelForNamespace("twext.web2.dav", LogLevel.warn)

        self.assertEqual(
            predicate.logLevelForNamespace(None),
            LogLevel.error
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twisted"),
            LogLevel.error
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2"),
            LogLevel.debug
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav"),
            LogLevel.warn
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav.test"),
            LogLevel.warn
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav.test1.test2"),
            LogLevel.warn
        )


    def test_setInvalidLogLevel(self):
        """
        Can't pass invalid log levels to C{setLogLevelForNamespace()}.
        """
        predicate = LogLevelFilterPredicate()

        self.assertRaises(
            InvalidLogLevelError,
            predicate.setLogLevelForNamespace, "twext.web2", object()
        )

        # Level must be a constant, not the name of a constant
        self.assertRaises(
            InvalidLogLevelError,
            predicate.setLogLevelForNamespace, "twext.web2", "debug"
        )


    def test_clearLogLevels(self):
        """
        Clearing log levels.
        """
        predicate = LogLevelFilterPredicate()

        predicate.setLogLevelForNamespace("twext.web2", LogLevel.debug)
        predicate.setLogLevelForNamespace("twext.web2.dav", LogLevel.error)

        predicate.clearLogLevels()

        self.assertEqual(
            predicate.logLevelForNamespace("twisted"),
            predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2"),
            predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav"),
            predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav.test"),
            predicate.defaultLogLevel
        )
        self.assertEqual(
            predicate.logLevelForNamespace("twext.web2.dav.test1.test2"),
            predicate.defaultLogLevel
        )


    def test_filtering(self):
        """
        Events are filtered based on log level/namespace.
        """
        predicate = LogLevelFilterPredicate()

        predicate.setLogLevelForNamespace(None, LogLevel.error)
        predicate.setLogLevelForNamespace("twext.web2", LogLevel.debug)
        predicate.setLogLevelForNamespace("twext.web2.dav", LogLevel.warn)

        def checkPredicate(namespace, level, expectedResult):
            event = dict(log_namespace=namespace, log_level=level)
            self.assertEqual(expectedResult, predicate(event))

        checkPredicate("", LogLevel.debug, PredicateResult.no)
        checkPredicate("", LogLevel.error, PredicateResult.maybe)

        checkPredicate("twext.web2", LogLevel.debug, PredicateResult.maybe)
        checkPredicate("twext.web2", LogLevel.error, PredicateResult.maybe)

        checkPredicate("twext.web2.dav", LogLevel.debug, PredicateResult.no)
        checkPredicate("twext.web2.dav", LogLevel.error, PredicateResult.maybe)

        checkPredicate(None, LogLevel.critical, PredicateResult.no)
        checkPredicate("twext.web2", None, PredicateResult.no)
