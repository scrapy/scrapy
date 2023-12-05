# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase

try:
    import syslog as _stdsyslog
except ImportError:
    stdsyslog = None
else:
    stdsyslog = _stdsyslog
    from twisted.python import syslog


class SyslogObserverTests(TestCase):
    """
    Tests for L{SyslogObserver} which sends Twisted log events to the syslog.
    """

    events = None

    if stdsyslog is None:
        skip = "syslog is not supported on this platform"

    def setUp(self):
        self.patch(syslog.SyslogObserver, "openlog", self.openlog)
        self.patch(syslog.SyslogObserver, "syslog", self.syslog)
        self.observer = syslog.SyslogObserver("SyslogObserverTests")

    def openlog(self, prefix, options, facility):
        self.logOpened = (prefix, options, facility)
        self.events = []

    def syslog(self, options, message):
        self.events.append((options, message))

    def test_emitWithoutMessage(self):
        """
        L{SyslogObserver.emit} ignores events with an empty value for the
        C{'message'} key.
        """
        self.observer.emit({"message": (), "isError": False, "system": "-"})
        self.assertEqual(self.events, [])

    def test_emitCustomPriority(self):
        """
        L{SyslogObserver.emit} uses the value of the C{'syslogPriority'} as the
        syslog priority, if that key is present in the event dictionary.
        """
        self.observer.emit(
            {
                "message": ("hello, world",),
                "isError": False,
                "system": "-",
                "syslogPriority": stdsyslog.LOG_DEBUG,
            }
        )
        self.assertEqual(self.events, [(stdsyslog.LOG_DEBUG, "[-] hello, world")])

    def test_emitErrorPriority(self):
        """
        L{SyslogObserver.emit} uses C{LOG_ALERT} if the event represents an
        error.
        """
        self.observer.emit(
            {
                "message": ("hello, world",),
                "isError": True,
                "system": "-",
                "failure": Failure(Exception("foo")),
            }
        )
        self.assertEqual(self.events, [(stdsyslog.LOG_ALERT, "[-] hello, world")])

    def test_emitCustomPriorityOverridesError(self):
        """
        L{SyslogObserver.emit} uses the value of the C{'syslogPriority'} key if
        it is specified even if the event dictionary represents an error.
        """
        self.observer.emit(
            {
                "message": ("hello, world",),
                "isError": True,
                "system": "-",
                "syslogPriority": stdsyslog.LOG_NOTICE,
                "failure": Failure(Exception("bar")),
            }
        )
        self.assertEqual(self.events, [(stdsyslog.LOG_NOTICE, "[-] hello, world")])

    def test_emitCustomFacility(self):
        """
        L{SyslogObserver.emit} uses the value of the C{'syslogPriority'} as the
        syslog priority, if that key is present in the event dictionary.
        """
        self.observer.emit(
            {
                "message": ("hello, world",),
                "isError": False,
                "system": "-",
                "syslogFacility": stdsyslog.LOG_CRON,
            }
        )
        self.assertEqual(
            self.events, [(stdsyslog.LOG_INFO | stdsyslog.LOG_CRON, "[-] hello, world")]
        )

    def test_emitCustomSystem(self):
        """
        L{SyslogObserver.emit} uses the value of the C{'system'} key to prefix
        the logged message.
        """
        self.observer.emit(
            {
                "message": ("hello, world",),
                "isError": False,
                "system": "nonDefaultSystem",
            }
        )
        self.assertEqual(
            self.events, [(stdsyslog.LOG_INFO, "[nonDefaultSystem] hello, world")]
        )

    def test_emitMessage(self):
        """
        L{SyslogObserver.emit} logs the value of the C{'message'} key of the
        event dictionary it is passed to the syslog.
        """
        self.observer.emit(
            {"message": ("hello, world",), "isError": False, "system": "-"}
        )
        self.assertEqual(self.events, [(stdsyslog.LOG_INFO, "[-] hello, world")])

    def test_emitMultilineMessage(self):
        """
        Each line of a multiline message is emitted separately to the syslog.
        """
        self.observer.emit(
            {"message": ("hello,\nworld",), "isError": False, "system": "-"}
        )
        self.assertEqual(
            self.events,
            [(stdsyslog.LOG_INFO, "[-] hello,"), (stdsyslog.LOG_INFO, "[-] \tworld")],
        )

    def test_emitStripsTrailingEmptyLines(self):
        """
        Trailing empty lines of a multiline message are omitted from the
        messages sent to the syslog.
        """
        self.observer.emit(
            {"message": ("hello,\nworld\n\n",), "isError": False, "system": "-"}
        )
        self.assertEqual(
            self.events,
            [(stdsyslog.LOG_INFO, "[-] hello,"), (stdsyslog.LOG_INFO, "[-] \tworld")],
        )
