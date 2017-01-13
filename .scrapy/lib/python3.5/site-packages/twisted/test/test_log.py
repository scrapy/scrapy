# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.log}.
"""

from __future__ import division, absolute_import, print_function

from twisted.python.compat import _PY3, NativeStringIO as StringIO

import os
import sys
import time
import logging
import warnings
import calendar
from io import IOBase

from twisted.trial import unittest

from twisted.python import log, failure
from twisted.logger.test.test_stdlib import handlerAndBytesIO
from twisted.python.log import LogPublisher
from twisted.logger import (
    LoggingFile, LogLevel as NewLogLevel, LogBeginner,
    LogPublisher as NewLogPublisher
)


class FakeWarning(Warning):
    """
    A unique L{Warning} subclass used by tests for interactions of
    L{twisted.python.log} with the L{warnings} module.
    """



class TextFromEventDictTests(unittest.SynchronousTestCase):
    """
    Tests for L{textFromEventDict}.
    """

    def test_message(self):
        """
        The C{"message"} value, when specified, is concatenated to generate the
        message.
        """
        eventDict = dict(message=("a", "b", "c"))
        text = log.textFromEventDict(eventDict)
        self.assertEqual(text, "a b c")



    def test_format(self):
        """
        The C{"format"} value, when specified, is used to format the message.
        """
        eventDict = dict(
            message=(), isError=0, format="Hello, %(foo)s!", foo="dude"
        )
        text = log.textFromEventDict(eventDict)
        self.assertEqual(text, "Hello, dude!")



    def test_noMessageNoFormat(self):
        """
        If C{"format"} is unspecified and C{"message"} is empty, return
        L{None}.
        """
        eventDict = dict(message=(), isError=0)
        text = log.textFromEventDict(eventDict)
        self.assertIsNone(text)



    def test_whySpecified(self):
        """
        The C{"why"} value, when specified, is first part of message.
        """
        try:
            raise RuntimeError()
        except:
            eventDict = dict(
                message=(), isError=1, failure=failure.Failure(), why="foo"
            )
            text = log.textFromEventDict(eventDict)
            self.assertTrue(text.startswith("foo\n"))


    def test_whyDefault(self):
        """
        The C{"why"} value, when unspecified, defaults to C{"Unhandled Error"}.
        """
        try:
            raise RuntimeError()
        except:
            eventDict = dict(message=(), isError=1, failure=failure.Failure())
            text = log.textFromEventDict(eventDict)
            self.assertTrue(text.startswith("Unhandled Error\n"))


    def test_noTracebackForYou(self):
        """
        If unable to obtain a traceback due to an exception, catch it and note
        the error.
        """
        # Invalid failure object doesn't implement .getTraceback()
        eventDict = dict(message=(), isError=1, failure=object())
        text = log.textFromEventDict(eventDict)
        self.assertIn("\n(unable to obtain traceback)", text)



class LogTests(unittest.SynchronousTestCase):

    def setUp(self):
        self.catcher = []
        self.observer = self.catcher.append
        log.addObserver(self.observer)
        self.addCleanup(log.removeObserver, self.observer)


    def testObservation(self):
        catcher = self.catcher
        log.msg("test", testShouldCatch=True)
        i = catcher.pop()
        self.assertEqual(i["message"][0], "test")
        self.assertTrue(i["testShouldCatch"])
        self.assertIn("time", i)
        self.assertEqual(len(catcher), 0)


    def testContext(self):
        catcher = self.catcher
        log.callWithContext({"subsystem": "not the default",
                             "subsubsystem": "a",
                             "other": "c"},
                            log.callWithContext,
                            {"subsubsystem": "b"}, log.msg, "foo", other="d")
        i = catcher.pop()
        self.assertEqual(i['subsubsystem'], 'b')
        self.assertEqual(i['subsystem'], 'not the default')
        self.assertEqual(i['other'], 'd')
        self.assertEqual(i['message'][0], 'foo')


    def testErrors(self):
        for e, ig in [("hello world", "hello world"),
                      (KeyError(), KeyError),
                      (failure.Failure(RuntimeError()), RuntimeError)]:
            log.err(e)
            i = self.catcher.pop()
            self.assertEqual(i['isError'], 1)
            self.flushLoggedErrors(ig)


    def testErrorsWithWhy(self):
        for e, ig in [("hello world", "hello world"),
                      (KeyError(), KeyError),
                      (failure.Failure(RuntimeError()), RuntimeError)]:
            log.err(e, 'foobar')
            i = self.catcher.pop()
            self.assertEqual(i['isError'], 1)
            self.assertEqual(i['why'], 'foobar')
            self.flushLoggedErrors(ig)


    def test_erroneousErrors(self):
        """
        Exceptions raised by log observers are logged but the observer which
        raised the exception remains registered with the publisher.  These
        exceptions do not prevent the event from being sent to other observers
        registered with the publisher.
        """
        L1 = []
        L2 = []

        def broken(event):
            1 // 0

        for observer in [L1.append, broken, L2.append]:
            log.addObserver(observer)
            self.addCleanup(log.removeObserver, observer)

        for i in range(3):
            # Reset the lists for simpler comparison.
            L1[:] = []
            L2[:] = []

            # Send out the event which will break one of the observers.
            log.msg("Howdy, y'all.", log_trace=[])

            # The broken observer should have caused this to be logged.
            excs = self.flushLoggedErrors(ZeroDivisionError)
            del self.catcher[:]
            self.assertEqual(len(excs), 1)

            # Both other observers should have seen the message.
            self.assertEqual(len(L1), 2)
            self.assertEqual(len(L2), 2)

            # The first event is delivered to all observers; then, errors
            # are delivered.
            self.assertEqual(L1[0]['message'], ("Howdy, y'all.",))
            self.assertEqual(L2[0]['message'], ("Howdy, y'all.",))


    def test_showwarning(self):
        """
        L{twisted.python.log.showwarning} emits the warning as a message
        to the Twisted logging system.
        """
        publisher = log.LogPublisher()
        publisher.addObserver(self.observer)

        publisher.showwarning(
            FakeWarning("unique warning message"), FakeWarning,
            "warning-filename.py", 27)
        event = self.catcher.pop()
        self.assertEqual(
            event['format'] % event,
            'warning-filename.py:27: twisted.test.test_log.FakeWarning: '
            'unique warning message')
        self.assertEqual(self.catcher, [])

        # Python 2.6 requires that any function used to override the
        # warnings.showwarning API accept a "line" parameter or a
        # deprecation warning is emitted.
        publisher.showwarning(
            FakeWarning("unique warning message"), FakeWarning,
            "warning-filename.py", 27, line=object())
        event = self.catcher.pop()
        self.assertEqual(
            event['format'] % event,
            'warning-filename.py:27: twisted.test.test_log.FakeWarning: '
            'unique warning message')
        self.assertEqual(self.catcher, [])


    def test_warningToFile(self):
        """
        L{twisted.python.log.showwarning} passes warnings with an explicit file
        target on to the underlying Python warning system.
        """
        message = "another unique message"
        category = FakeWarning
        filename = "warning-filename.py"
        lineno = 31

        output = StringIO()
        log.showwarning(message, category, filename, lineno, file=output)

        self.assertEqual(
            output.getvalue(),
            warnings.formatwarning(message, category, filename, lineno))

        # In Python 2.6 and higher, warnings.showwarning accepts
        # a "line" argument which gives the source line the warning
        # message is to include.
        line = "hello world"
        output = StringIO()
        log.showwarning(message, category, filename, lineno, file=output,
                        line=line)

        self.assertEqual(
            output.getvalue(),
            warnings.formatwarning(message, category, filename, lineno,
                                   line))


    def test_publisherReportsBrokenObserversPrivately(self):
        """
        Log publisher does not use the global L{log.err} when reporting broken
        observers.
        """
        errors = []

        def logError(eventDict):
            if eventDict.get("isError"):
                errors.append(eventDict["failure"].value)

        def fail(eventDict):
            raise RuntimeError("test_publisherLocalyReportsBrokenObservers")

        publisher = log.LogPublisher()
        publisher.addObserver(logError)
        publisher.addObserver(fail)

        publisher.msg("Hello!")
        self.assertEqual(set(publisher.observers), set([logError, fail]))
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)



class FakeFile(list):

    def write(self, bytes):
        self.append(bytes)


    def flush(self):
        pass


IOBase.register(FakeFile)



class EvilStr:
    def __str__(self):
        1 // 0



class EvilRepr:
    def __str__(self):
        return "Happy Evil Repr"


    def __repr__(self):
        1 // 0



class EvilReprStr(EvilStr, EvilRepr):
    pass



class LogPublisherTestCaseMixin:
    def setUp(self):
        """
        Add a log observer which records log events in C{self.out}.  Also,
        make sure the default string encoding is ASCII so that
        L{testSingleUnicode} can test the behavior of logging unencodable
        unicode messages.
        """
        self.out = FakeFile()
        self.lp = log.LogPublisher()
        self.flo = log.FileLogObserver(self.out)
        self.lp.addObserver(self.flo.emit)

        try:
            str(u'\N{VULGAR FRACTION ONE HALF}')
        except UnicodeEncodeError:
            # This is the behavior we want - don't change anything.
            self._origEncoding = None
        else:
            if _PY3:
                self._origEncoding = None
                return
            reload(sys)
            self._origEncoding = sys.getdefaultencoding()
            sys.setdefaultencoding('ascii')


    def tearDown(self):
        """
        Verify that everything written to the fake file C{self.out} was a
        C{str}.  Also, restore the default string encoding to its previous
        setting, if it was modified by L{setUp}.
        """
        for chunk in self.out:
            self.assertIsInstance(chunk, str,
                            "%r was not a string" % (chunk,))

        if self._origEncoding is not None:
            sys.setdefaultencoding(self._origEncoding)
            del sys.setdefaultencoding



class LogPublisherTests(LogPublisherTestCaseMixin,
                        unittest.SynchronousTestCase):
    def testSingleString(self):
        self.lp.msg("Hello, world.")
        self.assertEqual(len(self.out), 1)


    def testMultipleString(self):
        # Test some stupid behavior that will be deprecated real soon.
        # If you are reading this and trying to learn how the logging
        # system works, *do not use this feature*.
        self.lp.msg("Hello, ", "world.")
        self.assertEqual(len(self.out), 1)


    def test_singleUnicode(self):
        """
        L{log.LogPublisher.msg} does not accept non-ASCII Unicode on Python 2,
        logging an error instead.

        On Python 3, where Unicode is default message type, the message is
        logged normally.
        """
        message = u"Hello, \N{VULGAR FRACTION ONE HALF} world."
        self.lp.msg(message)
        self.assertEqual(len(self.out), 1)
        if _PY3:
            self.assertIn(message, self.out[0])
        else:
            self.assertIn('with str error', self.out[0])
            self.assertIn('UnicodeEncodeError', self.out[0])



class FileObserverTests(LogPublisherTestCaseMixin,
                        unittest.SynchronousTestCase):
    """
    Tests for L{log.FileObserver}.
    """
    ERROR_INVALID_FORMAT = 'Invalid format string'
    ERROR_UNFORMATTABLE_OBJECT = 'UNFORMATTABLE OBJECT'
    ERROR_FORMAT = (
        'Invalid format string or unformattable object in log message'
    )
    ERROR_PATHOLOGICAL = 'PATHOLOGICAL ERROR'

    ERROR_NO_FORMAT = 'Unable to format event'
    ERROR_UNFORMATTABLE_SYSTEM = '[UNFORMATTABLE]'
    ERROR_MESSAGE_LOST = 'MESSAGE LOST: unformattable object logged'

    def _getTimezoneOffsetTest(self, tzname, daylightOffset, standardOffset):
        """
        Verify that L{getTimezoneOffset} produces the expected offset for a
        certain timezone both when daylight saving time is in effect and when
        it is not.

        @param tzname: The name of a timezone to exercise.
        @type tzname: L{bytes}

        @param daylightOffset: The number of seconds west of UTC the timezone
            should be when daylight saving time is in effect.
        @type daylightOffset: L{int}

        @param standardOffset: The number of seconds west of UTC the timezone
            should be when daylight saving time is not in effect.
        @type standardOffset: L{int}
        """
        if getattr(time, 'tzset', None) is None:
            raise unittest.SkipTest(
                "Platform cannot change timezone, cannot verify correct "
                "offsets in well-known timezones.")

        originalTimezone = os.environ.get('TZ', None)
        try:
            os.environ['TZ'] = tzname
            time.tzset()

            # The behavior of mktime depends on the current timezone setting.
            # So only do this after changing the timezone.

            # Compute a POSIX timestamp for a certain date and time that is
            # known to occur at a time when daylight saving time is in effect.
            localDaylightTuple = (2006, 6, 30, 0, 0, 0, 4, 181, 1)
            daylight = time.mktime(localDaylightTuple)

            # Compute a POSIX timestamp for a certain date and time that is
            # known to occur at a time when daylight saving time is not in
            # effect.
            localStandardTuple = (2007, 1, 31, 0, 0, 0, 2, 31, 0)
            standard = time.mktime(localStandardTuple)

            self.assertEqual(
                (self.flo.getTimezoneOffset(daylight),
                 self.flo.getTimezoneOffset(standard)),
                (daylightOffset, standardOffset))
        finally:
            if originalTimezone is None:
                del os.environ['TZ']
            else:
                os.environ['TZ'] = originalTimezone
            time.tzset()


    def test_getTimezoneOffsetWestOfUTC(self):
        """
        Attempt to verify that L{FileLogObserver.getTimezoneOffset} returns
        correct values for the current C{TZ} environment setting for at least
        some cases.  This test method exercises a timezone that is west of UTC
        (and should produce positive results).
        """
        self._getTimezoneOffsetTest("America/New_York", 14400, 18000)


    def test_getTimezoneOffsetEastOfUTC(self):
        """
        Attempt to verify that L{FileLogObserver.getTimezoneOffset} returns
        correct values for the current C{TZ} environment setting for at least
        some cases.  This test method exercises a timezone that is east of UTC
        (and should produce negative results).
        """
        self._getTimezoneOffsetTest("Europe/Berlin", -7200, -3600)


    def test_getTimezoneOffsetWithoutDaylightSavingTime(self):
        """
        Attempt to verify that L{FileLogObserver.getTimezoneOffset} returns
        correct values for the current C{TZ} environment setting for at least
        some cases.  This test method exercises a timezone that does not use
        daylight saving time at all (so both summer and winter time test values
        should have the same offset).
        """
        # Test a timezone that doesn't have DST.  mktime() implementations
        # available for testing seem happy to produce results for this even
        # though it's not entirely valid.
        self._getTimezoneOffsetTest("Africa/Johannesburg", -7200, -7200)


    def test_timeFormatting(self):
        """
        Test the method of L{FileLogObserver} which turns a timestamp into a
        human-readable string.
        """
        when = calendar.timegm((2001, 2, 3, 4, 5, 6, 7, 8, 0))

        # Pretend to be in US/Eastern for a moment
        self.flo.getTimezoneOffset = lambda when: 18000
        self.assertEqual(self.flo.formatTime(when), '2001-02-02 23:05:06-0500')

        # Okay now we're in Eastern Europe somewhere
        self.flo.getTimezoneOffset = lambda when: -3600
        self.assertEqual(self.flo.formatTime(when), '2001-02-03 05:05:06+0100')

        # And off in the Pacific or someplace like that
        self.flo.getTimezoneOffset = lambda when: -39600
        self.assertEqual(self.flo.formatTime(when), '2001-02-03 15:05:06+1100')

        # One of those weird places with a half-hour offset timezone
        self.flo.getTimezoneOffset = lambda when: 5400
        self.assertEqual(self.flo.formatTime(when), '2001-02-03 02:35:06-0130')

        # Half-hour offset in the other direction
        self.flo.getTimezoneOffset = lambda when: -5400
        self.assertEqual(self.flo.formatTime(when), '2001-02-03 05:35:06+0130')

        # Test an offset which is between 0 and 60 minutes to make sure the
        # sign comes out properly in that case.
        self.flo.getTimezoneOffset = lambda when: 1800
        self.assertEqual(self.flo.formatTime(when), '2001-02-03 03:35:06-0030')

        # Test an offset between 0 and 60 minutes in the other direction.
        self.flo.getTimezoneOffset = lambda when: -1800
        self.assertEqual(self.flo.formatTime(when), '2001-02-03 04:35:06+0030')

        # If a strftime-format string is present on the logger, it should
        # use that instead.  Note we don't assert anything about day, hour
        # or minute because we cannot easily control what time.strftime()
        # thinks the local timezone is.
        self.flo.timeFormat = '%Y %m'
        self.assertEqual(self.flo.formatTime(when), '2001 02')


    def test_microsecondTimestampFormatting(self):
        """
        L{FileLogObserver.formatTime} supports a value of C{timeFormat} which
        includes C{"%f"}, a L{datetime}-only format specifier for microseconds.
        """
        self.flo.timeFormat = '%f'
        self.assertEqual("600000", self.flo.formatTime(12345.6))


    def test_loggingAnObjectWithBroken__str__(self):
        # HELLO, MCFLY
        self.lp.msg(EvilStr())
        self.assertEqual(len(self.out), 1)
        # Logging system shouldn't need to crap itself for this trivial case
        self.assertNotIn(self.ERROR_UNFORMATTABLE_OBJECT, self.out[0])


    def test_formattingAnObjectWithBroken__str__(self):
        self.lp.msg(format='%(blat)s', blat=EvilStr())
        self.assertEqual(len(self.out), 1)
        self.assertIn(self.ERROR_INVALID_FORMAT, self.out[0])


    def test_brokenSystem__str__(self):
        self.lp.msg('huh', system=EvilStr())
        self.assertEqual(len(self.out), 1)
        self.assertIn(self.ERROR_FORMAT, self.out[0])


    def test_formattingAnObjectWithBroken__repr__Indirect(self):
        self.lp.msg(format='%(blat)s', blat=[EvilRepr()])
        self.assertEqual(len(self.out), 1)
        self.assertIn(self.ERROR_UNFORMATTABLE_OBJECT, self.out[0])


    def test_systemWithBroker__repr__Indirect(self):
        self.lp.msg('huh', system=[EvilRepr()])
        self.assertEqual(len(self.out), 1)
        self.assertIn(self.ERROR_UNFORMATTABLE_OBJECT, self.out[0])


    def test_simpleBrokenFormat(self):
        self.lp.msg(format='hooj %s %s', blat=1)
        self.assertEqual(len(self.out), 1)
        self.assertIn(self.ERROR_INVALID_FORMAT, self.out[0])


    def test_ridiculousFormat(self):
        self.lp.msg(format=42, blat=1)
        self.assertEqual(len(self.out), 1)
        self.assertIn(self.ERROR_INVALID_FORMAT, self.out[0])


    def test_evilFormat__repr__And__str__(self):
        self.lp.msg(format=EvilReprStr(), blat=1)
        self.assertEqual(len(self.out), 1)
        self.assertIn(self.ERROR_PATHOLOGICAL, self.out[0])


    def test_strangeEventDict(self):
        """
        This kind of eventDict used to fail silently, so test it does.
        """
        self.lp.msg(message='', isError=False)
        self.assertEqual(len(self.out), 0)


    def _startLoggingCleanup(self):
        """
        Cleanup after a startLogging() call that mutates the hell out of some
        global state.
        """
        self.addCleanup(log.theLogPublisher._stopLogging)
        self.addCleanup(setattr, sys, 'stdout', sys.stdout)
        self.addCleanup(setattr, sys, 'stderr', sys.stderr)


    def test_printToStderrSetsIsError(self):
        """
        startLogging()'s overridden sys.stderr should consider everything
        written to it an error.
        """
        self._startLoggingCleanup()
        fakeFile = StringIO()
        log.startLogging(fakeFile)

        def observe(event):
            observed.append(event)
        observed = []
        log.addObserver(observe)

        print("Hello, world.", file=sys.stderr)
        self.assertEqual(observed[0]["isError"], 1)


    def test_startLogging(self):
        """
        startLogging() installs FileLogObserver and overrides sys.stdout and
        sys.stderr.
        """
        origStdout, origStderr = sys.stdout, sys.stderr
        self._startLoggingCleanup()
        # When done with test, reset stdout and stderr to current values:
        fakeFile = StringIO()
        observer = log.startLogging(fakeFile)
        self.addCleanup(observer.stop)
        log.msg("Hello!")
        self.assertIn("Hello!", fakeFile.getvalue())
        self.assertIsInstance(sys.stdout, LoggingFile)
        self.assertEqual(sys.stdout.level, NewLogLevel.info)
        encoding = getattr(origStdout, "encoding", None)
        if not encoding:
            encoding = sys.getdefaultencoding()
        self.assertEqual(sys.stdout.encoding.upper(), encoding.upper())
        self.assertIsInstance(sys.stderr, LoggingFile)
        self.assertEqual(sys.stderr.level, NewLogLevel.error)
        encoding = getattr(origStderr, "encoding", None)
        if not encoding:
            encoding = sys.getdefaultencoding()
        self.assertEqual(sys.stderr.encoding.upper(), encoding.upper())


    def test_startLoggingTwice(self):
        """
        There are some obscure error conditions that can occur when logging is
        started twice. See http://twistedmatrix.com/trac/ticket/3289 for more
        information.
        """
        self._startLoggingCleanup()
        # The bug is particular to the way that the t.p.log 'global' function
        # handle stdout. If we use our own stream, the error doesn't occur. If
        # we use our own LogPublisher, the error doesn't occur.
        sys.stdout = StringIO()

        def showError(eventDict):
            if eventDict['isError']:
                sys.__stdout__.write(eventDict['failure'].getTraceback())

        log.addObserver(showError)
        self.addCleanup(log.removeObserver, showError)
        observer = log.startLogging(sys.stdout)
        self.addCleanup(observer.stop)
        # At this point, we expect that sys.stdout is a StdioOnnaStick object.
        self.assertIsInstance(sys.stdout, LoggingFile)
        fakeStdout = sys.stdout
        observer = log.startLogging(sys.stdout)
        self.assertIs(sys.stdout, fakeStdout)


    def test_startLoggingOverridesWarning(self):
        """
        startLogging() overrides global C{warnings.showwarning} such that
        warnings go to Twisted log observers.
        """
        self._startLoggingCleanup()
        newPublisher = NewLogPublisher()

        class SysModule(object):
            stdout = object()
            stderr = object()

        tempLogPublisher = LogPublisher(
            newPublisher, newPublisher,
            logBeginner=LogBeginner(newPublisher, StringIO(), SysModule,
                                    warnings)
        )
        # Trial reports warnings in two ways.  First, it intercepts the global
        # 'showwarning' function *itself*, after starting logging (by way of
        # the '_collectWarnings' function which collects all warnings as a
        # around the test's 'run' method).  Second, it has a log observer which
        # immediately reports warnings when they're propagated into the log
        # system (which, in normal operation, happens only at the end of the
        # test case).  In order to avoid printing a spurious warning in this
        # test, we first replace the global log publisher's 'showwarning' in
        # the module with our own.
        self.patch(log, "theLogPublisher", tempLogPublisher)
        # And, one last thing, pretend we're starting from a fresh import, or
        # warnings.warn won't be patched at all.
        log._oldshowwarning = None
        # Global mutable state is bad, kids.  Stay in school.
        fakeFile = StringIO()
        # We didn't previously save log messages, so let's make sure we don't
        # save them any more.
        evt = {"pre-start": "event"}
        received = []

        def preStartObserver(x):
            if 'pre-start' in x.keys():
                received.append(x)

        newPublisher(evt)
        newPublisher.addObserver(preStartObserver)
        log.startLogging(fakeFile, setStdout=False)
        self.addCleanup(tempLogPublisher._stopLogging)
        self.assertEqual(received, [])
        warnings.warn("hello!")
        output = fakeFile.getvalue()
        self.assertIn("UserWarning: hello!", output)


    def test_emitPrefix(self):
        """
        FileLogObserver.emit() will add a timestamp and system prefix to its
        file output.
        """
        output = StringIO()
        flo = log.FileLogObserver(output)
        events = []

        def observer(event):
            # Capture the event for reference and pass it along to flo
            events.append(event)
            flo.emit(event)

        publisher = log.LogPublisher()
        publisher.addObserver(observer)

        publisher.msg("Hello!")
        self.assertEqual(len(events), 1)
        event = events[0]

        result = output.getvalue()
        prefix = "{time} [{system}] ".format(
            time=flo.formatTime(event["time"]), system=event["system"],
        )

        self.assertTrue(
            result.startswith(prefix),
            "{0!r} does not start with {1!r}".format(result, prefix)
        )


    def test_emitNewline(self):
        """
        FileLogObserver.emit() will append a newline to its file output.
        """
        output = StringIO()
        flo = log.FileLogObserver(output)

        publisher = log.LogPublisher()
        publisher.addObserver(flo.emit)

        publisher.msg("Hello!")

        result = output.getvalue()
        suffix = "Hello!\n"

        self.assertTrue(
            result.endswith(suffix),
            "{0!r} does not end with {1!r}".format(result, suffix)
        )



class PythonLoggingObserverTests(unittest.SynchronousTestCase):
    """
    Test the bridge with python logging module.
    """
    def setUp(self):
        rootLogger = logging.getLogger("")
        originalLevel = rootLogger.getEffectiveLevel()
        rootLogger.setLevel(logging.DEBUG)

        @self.addCleanup
        def restoreLevel():
            rootLogger.setLevel(originalLevel)
        self.hdlr, self.out = handlerAndBytesIO()
        rootLogger.addHandler(self.hdlr)

        @self.addCleanup
        def removeLogger():
            rootLogger.removeHandler(self.hdlr)
            self.hdlr.close()

        self.lp = log.LogPublisher()
        self.obs = log.PythonLoggingObserver()
        self.lp.addObserver(self.obs.emit)


    def test_singleString(self):
        """
        Test simple output, and default log level.
        """
        self.lp.msg("Hello, world.")
        self.assertIn(b"Hello, world.", self.out.getvalue())
        self.assertIn(b"INFO", self.out.getvalue())


    def test_errorString(self):
        """
        Test error output.
        """
        f = failure.Failure(ValueError("That is bad."))
        self.lp.msg(failure=f, isError=True)
        prefix = b"CRITICAL:"
        output = self.out.getvalue()
        self.assertTrue(
            output.startswith(prefix),
            "Does not start with {0!r}: {1!r}".format(prefix, output)
        )


    def test_formatString(self):
        """
        Test logging with a format.
        """
        self.lp.msg(format="%(bar)s oo %(foo)s", bar="Hello", foo="world")
        self.assertIn(b"Hello oo world", self.out.getvalue())


    def test_customLevel(self):
        """
        Test the logLevel keyword for customizing level used.
        """
        self.lp.msg("Spam egg.", logLevel=logging.ERROR)
        self.assertIn(b"Spam egg.", self.out.getvalue())
        self.assertIn(b"ERROR", self.out.getvalue())
        self.out.seek(0, 0)
        self.out.truncate()
        self.lp.msg("Foo bar.", logLevel=logging.WARNING)
        self.assertIn(b"Foo bar.", self.out.getvalue())
        self.assertIn(b"WARNING", self.out.getvalue())


    def test_strangeEventDict(self):
        """
        Verify that an event dictionary which is not an error and has an empty
        message isn't recorded.
        """
        self.lp.msg(message='', isError=False)
        self.assertEqual(self.out.getvalue(), b'')



class PythonLoggingIntegrationTests(unittest.SynchronousTestCase):
    """
    Test integration of python logging bridge.
    """

    def test_startStopObserver(self):
        """
        Test that start and stop methods of the observer actually register
        and unregister to the log system.
        """
        oldAddObserver = log.addObserver
        oldRemoveObserver = log.removeObserver
        l = []
        try:
            log.addObserver = l.append
            log.removeObserver = l.remove
            obs = log.PythonLoggingObserver()
            obs.start()
            self.assertEqual(l[0], obs.emit)
            obs.stop()
            self.assertEqual(len(l), 0)
        finally:
            log.addObserver = oldAddObserver
            log.removeObserver = oldRemoveObserver


    def test_inheritance(self):
        """
        Test that we can inherit L{log.PythonLoggingObserver} and use super:
        that's basically a validation that L{log.PythonLoggingObserver} is
        new-style class.
        """
        class MyObserver(log.PythonLoggingObserver):
            def emit(self, eventDict):
                super(MyObserver, self).emit(eventDict)
        obs = MyObserver()
        l = []
        oldEmit = log.PythonLoggingObserver.emit
        try:
            log.PythonLoggingObserver.emit = l.append
            obs.emit('foo')
            self.assertEqual(len(l), 1)
        finally:
            log.PythonLoggingObserver.emit = oldEmit



class DefaultObserverTests(unittest.SynchronousTestCase):
    """
    Test the default observer.
    """

    def test_failureLogger(self):
        """
        The reason argument passed to log.err() appears in the report
        generated by DefaultObserver.
        """
        self.catcher = []
        self.observer = self.catcher.append
        log.addObserver(self.observer)
        self.addCleanup(log.removeObserver, self.observer)

        obs = log.DefaultObserver()
        obs.stderr = StringIO()
        obs.start()
        self.addCleanup(obs.stop)

        reason = "The reason."
        log.err(Exception(), reason)
        errors = self.flushLoggedErrors()

        self.assertIn(reason, obs.stderr.getvalue())
        self.assertEqual(len(errors), 1)


    def test_emitEventWithBrokenRepr(self):
        """
        DefaultObserver.emit() does not raise when it observes an error event
        with a message that causes L{repr} to raise.
        """
        class Ouch(object):
            def __repr__(self):
                return str(1 / 0)

        message = ("foo", Ouch())
        event = dict(message=message, isError=1)

        observer = log.DefaultObserver()
        with StringIO() as output:
            observer.stderr = output
            observer.emit(event)
            self.assertTrue(output.getvalue().startswith("foo <Ouch instance"))



class StdioOnnaStickTests(unittest.SynchronousTestCase):
    """
    StdioOnnaStick should act like the normal sys.stdout object.
    """

    def setUp(self):
        self.resultLogs = []
        log.addObserver(self.resultLogs.append)


    def tearDown(self):
        log.removeObserver(self.resultLogs.append)


    def getLogMessages(self):
        return ["".join(d['message']) for d in self.resultLogs]


    def test_write(self):
        """
        Writing to a StdioOnnaStick instance results in Twisted log messages.

        Log messages are generated every time a '\\n' is encountered.
        """
        stdio = log.StdioOnnaStick()
        stdio.write("Hello there\nThis is a test")
        self.assertEqual(self.getLogMessages(), ["Hello there"])
        stdio.write("!\n")
        self.assertEqual(self.getLogMessages(),
                         ["Hello there", "This is a test!"])


    def test_metadata(self):
        """
        The log messages written by StdioOnnaStick have printed=1 keyword, and
        by default are not errors.
        """
        stdio = log.StdioOnnaStick()
        stdio.write("hello\n")
        self.assertFalse(self.resultLogs[0]['isError'])
        self.assertTrue(self.resultLogs[0]['printed'])


    def test_writeLines(self):
        """
        Writing lines to a StdioOnnaStick results in Twisted log messages.
        """
        stdio = log.StdioOnnaStick()
        stdio.writelines(["log 1", "log 2"])
        self.assertEqual(self.getLogMessages(), ["log 1", "log 2"])


    def test_print(self):
        """
        When StdioOnnaStick is set as sys.stdout, prints become log messages.
        """
        oldStdout = sys.stdout
        sys.stdout = log.StdioOnnaStick()
        self.addCleanup(setattr, sys, "stdout", oldStdout)
        print("This", end=" ")
        print("is a test")
        self.assertEqual(self.getLogMessages(), ["This is a test"])


    def test_error(self):
        """
        StdioOnnaStick created with isError=True log messages as errors.
        """
        stdio = log.StdioOnnaStick(isError=True)
        stdio.write("log 1\n")
        self.assertTrue(self.resultLogs[0]['isError'])


    def test_unicode(self):
        """
        StdioOnnaStick converts unicode prints to byte strings on Python 2, in
        order to be compatible with the normal stdout/stderr objects.

        On Python 3, the prints are left unmodified.
        """
        unicodeString = u"Hello, \N{VULGAR FRACTION ONE HALF} world."
        stdio = log.StdioOnnaStick(encoding="utf-8")
        self.assertEqual(stdio.encoding, "utf-8")
        stdio.write(unicodeString + u"\n")
        stdio.writelines([u"Also, " + unicodeString])
        oldStdout = sys.stdout
        sys.stdout = stdio
        self.addCleanup(setattr, sys, "stdout", oldStdout)
        # This should go to the log, utf-8 encoded too:
        print(unicodeString)
        if _PY3:
            self.assertEqual(self.getLogMessages(),
                             [unicodeString,
                              u"Also, " + unicodeString,
                              unicodeString])
        else:
            self.assertEqual(self.getLogMessages(),
                             [unicodeString.encode("utf-8"),
                              (u"Also, " + unicodeString).encode("utf-8"),
                              unicodeString.encode("utf-8")])
