# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#

"""
Tests for L{twisted.trial.util}
"""


import locale
import os
import sys
from io import StringIO

from zope.interface import implementer

from hamcrest import assert_that, equal_to

from twisted.internet.base import DelayedCall
from twisted.internet.interfaces import IProcessTransport
from twisted.python import filepath
from twisted.python.failure import Failure
from twisted.trial import util
from twisted.trial.unittest import SynchronousTestCase
from twisted.trial.util import (
    DirtyReactorAggregateError,
    _Janitor,
    acquireAttribute,
    excInfoOrFailureToExcInfo,
    openTestLog,
)


class MktempTests(SynchronousTestCase):
    """
    Tests for L{TestCase.mktemp}, a helper function for creating temporary file
    or directory names.
    """

    def test_name(self):
        """
        The path name returned by C{mktemp} is directly beneath a directory
        which identifies the test method which created the name.
        """
        name = self.mktemp()
        dirs = os.path.dirname(name).split(os.sep)[:-1]
        self.assertEqual(
            dirs, ["twisted.trial.test.test_util", "MktempTests", "test_name"]
        )

    def test_unique(self):
        """
        Repeated calls to C{mktemp} return different values.
        """
        name = self.mktemp()
        self.assertNotEqual(name, self.mktemp())

    def test_created(self):
        """
        The directory part of the path name returned by C{mktemp} exists.
        """
        name = self.mktemp()
        dirname = os.path.dirname(name)
        self.assertTrue(os.path.exists(dirname))
        self.assertFalse(os.path.exists(name))

    def test_location(self):
        """
        The path returned by C{mktemp} is beneath the current working directory.
        """
        path = os.path.abspath(self.mktemp())
        self.assertTrue(path.startswith(os.getcwd()))


class DirtyReactorAggregateErrorTests(SynchronousTestCase):
    """
    Tests for the L{DirtyReactorAggregateError}.
    """

    def test_formatDelayedCall(self):
        """
        Delayed calls are formatted nicely.
        """
        error = DirtyReactorAggregateError(["Foo", "bar"])
        self.assertEqual(
            str(error),
            """\
Reactor was unclean.
DelayedCalls: (set twisted.internet.base.DelayedCall.debug = True to debug)
Foo
bar""",
        )

    def test_formatSelectables(self):
        """
        Selectables are formatted nicely.
        """
        error = DirtyReactorAggregateError([], ["selectable 1", "selectable 2"])
        self.assertEqual(
            str(error),
            """\
Reactor was unclean.
Selectables:
selectable 1
selectable 2""",
        )

    def test_formatDelayedCallsAndSelectables(self):
        """
        Both delayed calls and selectables can appear in the same error.
        """
        error = DirtyReactorAggregateError(["bleck", "Boozo"], ["Sel1", "Sel2"])
        self.assertEqual(
            str(error),
            """\
Reactor was unclean.
DelayedCalls: (set twisted.internet.base.DelayedCall.debug = True to debug)
bleck
Boozo
Selectables:
Sel1
Sel2""",
        )


class StubReactor:
    """
    A reactor stub which contains enough functionality to be used with the
    L{_Janitor}.

    @ivar iterations: A list of the arguments passed to L{iterate}.
    @ivar removeAllCalled: Number of times that L{removeAll} was called.
    @ivar selectables: The value that will be returned from L{removeAll}.
    @ivar delayedCalls: The value to return from L{getDelayedCalls}.
    """

    def __init__(self, delayedCalls, selectables=None):
        """
        @param delayedCalls: See L{StubReactor.delayedCalls}.
        @param selectables: See L{StubReactor.selectables}.
        """
        self.delayedCalls = delayedCalls
        self.iterations = []
        self.removeAllCalled = 0
        if not selectables:
            selectables = []
        self.selectables = selectables

    def iterate(self, timeout=None):
        """
        Increment C{self.iterations}.
        """
        self.iterations.append(timeout)

    def getDelayedCalls(self):
        """
        Return C{self.delayedCalls}.
        """
        return self.delayedCalls

    def removeAll(self):
        """
        Increment C{self.removeAllCalled} and return C{self.selectables}.
        """
        self.removeAllCalled += 1
        return self.selectables


class StubErrorReporter:
    """
    A subset of L{twisted.trial.itrial.IReporter} which records L{addError}
    calls.

    @ivar errors: List of two-tuples of (test, error) which were passed to
        L{addError}.
    """

    def __init__(self):
        self.errors = []

    def addError(self, test, error):
        """
        Record parameters in C{self.errors}.
        """
        self.errors.append((test, error))


class JanitorTests(SynchronousTestCase):
    """
    Tests for L{_Janitor}!
    """

    def test_cleanPendingSpinsReactor(self):
        """
        During pending-call cleanup, the reactor will be spun twice with an
        instant timeout. This is not a requirement, it is only a test for
        current behavior. Hopefully Trial will eventually not do this kind of
        reactor stuff.
        """
        reactor = StubReactor([])
        jan = _Janitor(None, None, reactor=reactor)
        jan._cleanPending()
        self.assertEqual(reactor.iterations, [0, 0])

    def test_cleanPendingCancelsCalls(self):
        """
        During pending-call cleanup, the janitor cancels pending timed calls.
        """

        def func():
            return "Lulz"

        cancelled = []
        delayedCall = DelayedCall(300, func, (), {}, cancelled.append, lambda x: None)
        reactor = StubReactor([delayedCall])
        jan = _Janitor(None, None, reactor=reactor)
        jan._cleanPending()
        self.assertEqual(cancelled, [delayedCall])

    def test_cleanPendingReturnsDelayedCallStrings(self):
        """
        The Janitor produces string representations of delayed calls from the
        delayed call cleanup method. It gets the string representations
        *before* cancelling the calls; this is important because cancelling the
        call removes critical debugging information from the string
        representation.
        """
        delayedCall = DelayedCall(
            300, lambda: None, (), {}, lambda x: None, lambda x: None, seconds=lambda: 0
        )
        delayedCallString = str(delayedCall)
        reactor = StubReactor([delayedCall])
        jan = _Janitor(None, None, reactor=reactor)
        strings = jan._cleanPending()
        self.assertEqual(strings, [delayedCallString])

    def test_cleanReactorRemovesSelectables(self):
        """
        The Janitor will remove selectables during reactor cleanup.
        """
        reactor = StubReactor([])
        jan = _Janitor(None, None, reactor=reactor)
        jan._cleanReactor()
        self.assertEqual(reactor.removeAllCalled, 1)

    def test_cleanReactorKillsProcesses(self):
        """
        The Janitor will kill processes during reactor cleanup.
        """

        @implementer(IProcessTransport)
        class StubProcessTransport:
            """
            A stub L{IProcessTransport} provider which records signals.
            @ivar signals: The signals passed to L{signalProcess}.
            """

            def __init__(self):
                self.signals = []

            def signalProcess(self, signal):
                """
                Append C{signal} to C{self.signals}.
                """
                self.signals.append(signal)

        pt = StubProcessTransport()
        reactor = StubReactor([], [pt])
        jan = _Janitor(None, None, reactor=reactor)
        jan._cleanReactor()
        self.assertEqual(pt.signals, ["KILL"])

    def test_cleanReactorReturnsSelectableStrings(self):
        """
        The Janitor returns string representations of the selectables that it
        cleaned up from the reactor cleanup method.
        """

        class Selectable:
            """
            A stub Selectable which only has an interesting string
            representation.
            """

            def __repr__(self) -> str:
                return "(SELECTABLE!)"

        reactor = StubReactor([], [Selectable()])
        jan = _Janitor(None, None, reactor=reactor)
        self.assertEqual(jan._cleanReactor(), ["(SELECTABLE!)"])

    def test_postCaseCleanupNoErrors(self):
        """
        The post-case cleanup method will return True and not call C{addError}
        on the result if there are no pending calls.
        """
        reactor = StubReactor([])
        test = object()
        reporter = StubErrorReporter()
        jan = _Janitor(test, reporter, reactor=reactor)
        self.assertTrue(jan.postCaseCleanup())
        self.assertEqual(reporter.errors, [])

    def test_postCaseCleanupWithErrors(self):
        """
        The post-case cleanup method will return False and call C{addError} on
        the result with a L{DirtyReactorAggregateError} Failure if there are
        pending calls.
        """
        delayedCall = DelayedCall(
            300, lambda: None, (), {}, lambda x: None, lambda x: None, seconds=lambda: 0
        )
        delayedCallString = str(delayedCall)
        reactor = StubReactor([delayedCall], [])
        test = object()
        reporter = StubErrorReporter()
        jan = _Janitor(test, reporter, reactor=reactor)
        self.assertFalse(jan.postCaseCleanup())
        self.assertEqual(len(reporter.errors), 1)
        self.assertEqual(reporter.errors[0][1].value.delayedCalls, [delayedCallString])

    def test_postClassCleanupNoErrors(self):
        """
        The post-class cleanup method will not call C{addError} on the result
        if there are no pending calls or selectables.
        """
        reactor = StubReactor([])
        test = object()
        reporter = StubErrorReporter()
        jan = _Janitor(test, reporter, reactor=reactor)
        jan.postClassCleanup()
        self.assertEqual(reporter.errors, [])

    def test_postClassCleanupWithPendingCallErrors(self):
        """
        The post-class cleanup method call C{addError} on the result with a
        L{DirtyReactorAggregateError} Failure if there are pending calls.
        """
        delayedCall = DelayedCall(
            300, lambda: None, (), {}, lambda x: None, lambda x: None, seconds=lambda: 0
        )
        delayedCallString = str(delayedCall)
        reactor = StubReactor([delayedCall], [])
        test = object()
        reporter = StubErrorReporter()
        jan = _Janitor(test, reporter, reactor=reactor)
        jan.postClassCleanup()
        self.assertEqual(len(reporter.errors), 1)
        self.assertEqual(reporter.errors[0][1].value.delayedCalls, [delayedCallString])

    def test_postClassCleanupWithSelectableErrors(self):
        """
        The post-class cleanup method call C{addError} on the result with a
        L{DirtyReactorAggregateError} Failure if there are selectables.
        """
        selectable = "SELECTABLE HERE"
        reactor = StubReactor([], [selectable])
        test = object()
        reporter = StubErrorReporter()
        jan = _Janitor(test, reporter, reactor=reactor)
        jan.postClassCleanup()
        self.assertEqual(len(reporter.errors), 1)
        self.assertEqual(reporter.errors[0][1].value.selectables, [repr(selectable)])


class RemoveSafelyTests(SynchronousTestCase):
    """
    Tests for L{util._removeSafely}.
    """

    def test_removeSafelyNoTrialMarker(self):
        """
        If a path doesn't contain a node named C{"_trial_marker"}, that path is
        not removed by L{util._removeSafely} and a L{util._NoTrialMarker}
        exception is raised instead.
        """
        directory = self.mktemp().encode("utf-8")
        os.mkdir(directory)
        dirPath = filepath.FilePath(directory)
        self.assertRaises(util._NoTrialMarker, util._removeSafely, dirPath)

    def test_removeSafelyRemoveFailsMoveSucceeds(self):
        """
        If an L{OSError} is raised while removing a path in
        L{util._removeSafely}, an attempt is made to move the path to a new
        name.
        """

        def dummyRemove():
            """
            Raise an C{OSError} to emulate the branch of L{util._removeSafely}
            in which path removal fails.
            """
            raise OSError()

        # Patch stdout so we can check the print statements in _removeSafely
        out = StringIO()
        self.patch(sys, "stdout", out)

        # Set up a trial directory with a _trial_marker
        directory = self.mktemp().encode("utf-8")
        os.mkdir(directory)
        dirPath = filepath.FilePath(directory)
        dirPath.child(b"_trial_marker").touch()
        # Ensure that path.remove() raises an OSError
        dirPath.remove = dummyRemove

        util._removeSafely(dirPath)
        self.assertIn("could not remove FilePath", out.getvalue())

    def test_removeSafelyRemoveFailsMoveFails(self):
        """
        If an L{OSError} is raised while removing a path in
        L{util._removeSafely}, an attempt is made to move the path to a new
        name. If that attempt fails, the L{OSError} is re-raised.
        """

        def dummyRemove():
            """
            Raise an C{OSError} to emulate the branch of L{util._removeSafely}
            in which path removal fails.
            """
            raise OSError("path removal failed")

        def dummyMoveTo(path):
            """
            Raise an C{OSError} to emulate the branch of L{util._removeSafely}
            in which path movement fails.
            """
            raise OSError("path movement failed")

        # Patch stdout so we can check the print statements in _removeSafely
        out = StringIO()
        self.patch(sys, "stdout", out)

        # Set up a trial directory with a _trial_marker
        directory = self.mktemp().encode("utf-8")
        os.mkdir(directory)
        dirPath = filepath.FilePath(directory)
        dirPath.child(b"_trial_marker").touch()

        # Ensure that path.remove() and path.moveTo() both raise OSErrors
        dirPath.remove = dummyRemove
        dirPath.moveTo = dummyMoveTo

        error = self.assertRaises(OSError, util._removeSafely, dirPath)
        self.assertEqual(str(error), "path movement failed")
        self.assertIn("could not remove FilePath", out.getvalue())


class ExcInfoTests(SynchronousTestCase):
    """
    Tests for L{excInfoOrFailureToExcInfo}.
    """

    def test_excInfo(self):
        """
        L{excInfoOrFailureToExcInfo} returns exactly what it is passed, if it is
        passed a tuple like the one returned by L{sys.exc_info}.
        """
        info = (ValueError, ValueError("foo"), None)
        self.assertTrue(info is excInfoOrFailureToExcInfo(info))

    def test_failure(self):
        """
        When called with a L{Failure} instance, L{excInfoOrFailureToExcInfo}
        returns a tuple like the one returned by L{sys.exc_info}, with the
        elements taken from the type, value, and traceback of the failure.
        """
        try:
            1 / 0
        except BaseException:
            f = Failure()
        self.assertEqual((f.type, f.value, f.tb), excInfoOrFailureToExcInfo(f))


class AcquireAttributeTests(SynchronousTestCase):
    """
    Tests for L{acquireAttribute}.
    """

    def test_foundOnEarlierObject(self):
        """
        The value returned by L{acquireAttribute} is the value of the requested
        attribute on the first object in the list passed in which has that
        attribute.
        """
        self.value = value = object()
        self.assertTrue(value is acquireAttribute([self, object()], "value"))

    def test_foundOnLaterObject(self):
        """
        The same as L{test_foundOnEarlierObject}, but for the case where the 2nd
        element in the object list has the attribute and the first does not.
        """
        self.value = value = object()
        self.assertTrue(value is acquireAttribute([object(), self], "value"))

    def test_notFoundException(self):
        """
        If none of the objects passed in the list to L{acquireAttribute} have
        the requested attribute, L{AttributeError} is raised.
        """
        self.assertRaises(AttributeError, acquireAttribute, [object()], "foo")

    def test_notFoundDefault(self):
        """
        If none of the objects passed in the list to L{acquireAttribute} have
        the requested attribute and a default value is given, the default value
        is returned.
        """
        default = object()
        self.assertTrue(default is acquireAttribute([object()], "foo", default))


class ListToPhraseTests(SynchronousTestCase):
    """
    Input is transformed into a string representation of the list,
    with each item separated by delimiter (defaulting to a comma) and the final
    two being separated by a final delimiter.
    """

    def test_empty(self):
        """
        If things is empty, an empty string is returned.
        """
        sample = []
        expected = ""
        result = util._listToPhrase(sample, "and")
        self.assertEqual(expected, result)

    def test_oneWord(self):
        """
        With a single item, the item is returned.
        """
        sample = ["One"]
        expected = "One"
        result = util._listToPhrase(sample, "and")
        self.assertEqual(expected, result)

    def test_twoWords(self):
        """
        Two words are separated by the final delimiter.
        """
        sample = ["One", "Two"]
        expected = "One and Two"
        result = util._listToPhrase(sample, "and")
        self.assertEqual(expected, result)

    def test_threeWords(self):
        """
        With more than two words, the first two are separated by the delimiter.
        """
        sample = ["One", "Two", "Three"]
        expected = "One, Two, and Three"
        result = util._listToPhrase(sample, "and")
        self.assertEqual(expected, result)

    def test_fourWords(self):
        """
        If a delimiter is specified, it is used instead of the default comma.
        """
        sample = ["One", "Two", "Three", "Four"]
        expected = "One; Two; Three; or Four"
        result = util._listToPhrase(sample, "or", delimiter="; ")
        self.assertEqual(expected, result)

    def test_notString(self):
        """
        If something in things is not a string, it is converted into one.
        """
        sample = [1, 2, "three"]
        expected = "1, 2, and three"
        result = util._listToPhrase(sample, "and")
        self.assertEqual(expected, result)

    def test_stringTypeError(self):
        """
        If things is a string, a TypeError is raised.
        """
        sample = "One, two, three"
        error = self.assertRaises(TypeError, util._listToPhrase, sample, "and")
        self.assertEqual(str(error), "Things must be a list or a tuple")

    def test_iteratorTypeError(self):
        """
        If things is an iterator, a TypeError is raised.
        """
        sample = iter([1, 2, 3])
        error = self.assertRaises(TypeError, util._listToPhrase, sample, "and")
        self.assertEqual(str(error), "Things must be a list or a tuple")

    def test_generatorTypeError(self):
        """
        If things is a generator, a TypeError is raised.
        """

        def sample():
            yield from range(2)

        error = self.assertRaises(TypeError, util._listToPhrase, sample, "and")
        self.assertEqual(str(error), "Things must be a list or a tuple")


class OpenTestLogTests(SynchronousTestCase):
    """
    Tests for C{openTestLog}.
    """

    def test_utf8(self):
        """
        The log file is opened in text mode and uses UTF-8 for encoding.
        """
        # Modern OSes are running default locale in UTF-8 and this is what is
        # used by Python at startup.  For this test, we force an ASCII default
        # encoding so that we can see that UTF-8 is used even if it isn't the
        # platform default.
        currentLocale = locale.getlocale()
        self.addCleanup(locale.setlocale, locale.LC_ALL, currentLocale)
        locale.setlocale(locale.LC_ALL, ("C", "ascii"))

        text = "Here comes the \N{SUN}"
        p = filepath.FilePath(self.mktemp())
        with openTestLog(p) as f:
            f.write(text)

        with open(p.path, "rb") as f:
            written = f.read()

        assert_that(text.encode("utf-8"), equal_to(written))

    def test_append(self):
        """
        The log file is opened in append mode so if runner configuration specifies
        an existing log file its contents are not wiped out.
        """
        existingText = "Hello, world.\n "
        newText = "Goodbye, world.\n"
        expected = f"Hello, world.{os.linesep} Goodbye, world.{os.linesep}"
        p = filepath.FilePath(self.mktemp())
        with openTestLog(p) as f:
            f.write(existingText)
        with openTestLog(p) as f:
            f.write(newText)

        assert_that(
            p.getContent().decode("utf-8"),
            equal_to(expected),
        )
