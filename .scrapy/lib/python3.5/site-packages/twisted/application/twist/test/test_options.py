# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.twist._options}.
"""

from sys import stdout, stderr

from twisted.copyright import version
from twisted.python.usage import UsageError
from twisted.logger import LogLevel, textFileLogObserver, jsonFileLogObserver
from twisted.test.proto_helpers import MemoryReactor
from ...reactors import NoSuchReactor
from ...service import ServiceMaker
from ...runner._exit import ExitStatus
from ...runner.test.test_runner import DummyExit
from ...twist import _options
from .._options import TwistOptions

import twisted.trial.unittest



class OptionsTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{TwistOptions}.
    """

    def patchExit(self):
        """
        Patch L{_twist.exit} so we can capture usage and prevent actual exits.
        """
        self.exit = DummyExit()
        self.patch(_options, "exit", self.exit)


    def patchOpen(self):
        """
        Patch L{_options.open} so we can capture usage and prevent actual opens.
        """
        self.opened = []

        def fakeOpen(name, mode=None):
            if name == "nocanopen":
                raise IOError(None, None, name)

            self.opened.append((name, mode))
            return NotImplemented

        self.patch(_options, "openFile", fakeOpen)


    def patchInstallReactor(self):
        """
        Patch C{_options.installReactor} so we can capture usage and prevent
        actual installs.
        """
        self.installedReactors = {}

        def installReactor(name):
            if name != "fusion":
                raise NoSuchReactor()

            reactor = MemoryReactor()
            self.installedReactors[name] = reactor
            return reactor

        self.patch(_options, "installReactor", installReactor)


    def test_synopsis(self):
        """
        L{TwistOptions.getSynopsis} appends arguments.
        """
        options = TwistOptions()

        self.assertTrue(
            options.getSynopsis().endswith(" plugin [plugin_options]")
        )


    def test_version(self):
        """
        L{TwistOptions.opt_version} exits with L{ExitStatus.EX_OK} and prints
        the version.
        """
        self.patchExit()

        options = TwistOptions()
        options.opt_version()

        self.assertEquals(self.exit.status, ExitStatus.EX_OK)
        self.assertEquals(self.exit.message, version)


    def test_reactor(self):
        """
        L{TwistOptions.opt_reactor} sets the reactor name.
        """
        options = TwistOptions()
        options.opt_reactor("fission")

        self.assertEquals(options["reactorName"], "fission")


    def test_installReactor(self):
        """
        L{TwistOptions.installReactor} installs the chosen reactor.
        """
        self.patchInstallReactor()

        options = TwistOptions()
        options.opt_reactor("fusion")
        options.installReactor()

        self.assertEqual(set(self.installedReactors), set(["fusion"]))


    def test_installReactorBogus(self):
        """
        L{TwistOptions.installReactor} raises UsageError if an unknown reactor
        is specified.
        """
        self.patchInstallReactor()

        options = TwistOptions()
        options.opt_reactor("coal")

        self.assertRaises(UsageError, options.installReactor)


    def test_logLevelValid(self):
        """
        L{TwistOptions.opt_log_level} sets the corresponding log level.
        """
        options = TwistOptions()
        options.opt_log_level("warn")

        self.assertIdentical(options["logLevel"], LogLevel.warn)


    def test_logLevelInvalid(self):
        """
        L{TwistOptions.opt_log_level} with an invalid log level name raises
        UsageError.
        """
        options = TwistOptions()

        self.assertRaises(UsageError, options.opt_log_level, "cheese")


    def _testLogFile(self, name, expectedStream):
        """
        Set log file name and check the selected output stream.

        @param name: The name of the file.
        @param expectedStream: The expected stream.
        """
        options = TwistOptions()
        options.opt_log_file(name)

        self.assertIdentical(options["logFile"], expectedStream)


    def test_logFileStdout(self):
        """
        L{TwistOptions.opt_log_file} given C{"-"} as a file name uses stdout.
        """
        self._testLogFile("-", stdout)


    def test_logFileStderr(self):
        """
        L{TwistOptions.opt_log_file} given C{"+"} as a file name uses stderr.
        """
        self._testLogFile("+", stderr)


    def test_logFileNamed(self):
        """
        L{TwistOptions.opt_log_file} opens the given file name in append mode.
        """
        self.patchOpen()

        options = TwistOptions()
        options.opt_log_file("mylog")

        self.assertEqual([("mylog", "a")], self.opened)


    def test_logFileCantOpen(self):
        """
        L{TwistOptions.opt_log_file} exits with L{ExitStatus.EX_IOERR} if
        unable to open the log file due to an L{EnvironmentError}.
        """
        self.patchExit()
        self.patchOpen()

        options = TwistOptions()
        options.opt_log_file("nocanopen")

        self.assertEquals(self.exit.status, ExitStatus.EX_IOERR)
        self.assertTrue(
            self.exit.message.startswith(
                "Unable to open log file 'nocanopen': "
            )
        )


    def _testLogFormat(self, format, expectedObserver):
        """
        Set log file format and check the selected observer.

        @param format: The format of the file.
        @param expectedObserver: The expected observer.
        """
        options = TwistOptions()
        options.opt_log_format(format)

        self.assertIdentical(
            options["fileLogObserverFactory"], expectedObserver
        )
        self.assertEqual(options["logFormat"], format)


    def test_logFormatText(self):
        """
        L{TwistOptions.opt_log_format} given C{"text"} uses a
        L{textFileLogObserver}.
        """
        self._testLogFormat("text", textFileLogObserver)


    def test_logFormatJSON(self):
        """
        L{TwistOptions.opt_log_format} given C{"text"} uses a
        L{textFileLogObserver}.
        """
        self._testLogFormat("json", jsonFileLogObserver)


    def test_logFormatInvalid(self):
        """
        L{TwistOptions.opt_log_format} given an invalid format name raises
        L{UsageError}.
        """
        options = TwistOptions()

        self.assertRaises(UsageError, options.opt_log_format, "frommage")


    def test_selectDefaultLogObserverNoOverride(self):
        """
        L{TwistOptions.selectDefaultLogObserver} will not override an already
        selected observer.
        """
        self.patchOpen()

        options = TwistOptions()
        options.opt_log_format("text")  # Ask for text
        options.opt_log_file("queso")   # File, not a tty
        options.selectDefaultLogObserver()

        # Because we didn't select a file that is a tty, the default is JSON,
        # but since we asked for text, we should get text.
        self.assertIdentical(
            options["fileLogObserverFactory"], textFileLogObserver
        )
        self.assertEqual(options["logFormat"], "text")


    def test_selectDefaultLogObserverDefaultWithTTY(self):
        """
        L{TwistOptions.selectDefaultLogObserver} will not override an already
        selected observer.
        """
        class TTYFile(object):
            def isatty(self):
                return True

        # stdout may not be a tty, so let's make sure it thinks it is
        self.patch(_options, "stdout", TTYFile())

        options = TwistOptions()
        options.opt_log_file("-")  # stdout, a tty
        options.selectDefaultLogObserver()

        self.assertIdentical(
            options["fileLogObserverFactory"], textFileLogObserver
        )
        self.assertEqual(options["logFormat"], "text")


    def test_selectDefaultLogObserverDefaultWithoutTTY(self):
        """
        L{TwistOptions.selectDefaultLogObserver} will not override an already
        selected observer.
        """
        self.patchOpen()

        options = TwistOptions()
        options.opt_log_file("queso")  # File, not a tty
        options.selectDefaultLogObserver()

        self.assertIdentical(
            options["fileLogObserverFactory"], jsonFileLogObserver
        )
        self.assertEqual(options["logFormat"], "json")


    def test_pluginsType(self):
        """
        L{TwistOptions.plugins} is a mapping of available plug-ins.
        """
        options = TwistOptions()
        plugins = options.plugins

        for name in plugins:
            self.assertIsInstance(name, str)
            self.assertIsInstance(plugins[name], ServiceMaker)


    def test_pluginsIncludeWeb(self):
        """
        L{TwistOptions.plugins} includes a C{"web"} plug-in.
        This is an attempt to verify that something we expect to be in the list
        is in there without enumerating all of the built-in plug-ins.
        """
        options = TwistOptions()

        self.assertIn("web", options.plugins)


    def test_subCommandsType(self):
        """
        L{TwistOptions.subCommands} is an iterable of tuples as expected by
        L{twisted.python.usage.Options}.
        """
        options = TwistOptions()

        for name, shortcut, parser, doc in options.subCommands:
            self.assertIsInstance(name, str)
            self.assertIdentical(shortcut, None)
            self.assertTrue(callable(parser))
            self.assertIsInstance(doc, str)


    def test_subCommandsIncludeWeb(self):
        """
        L{TwistOptions.subCommands} includes a sub-command for every plug-in.
        """
        options = TwistOptions()

        plugins = set(options.plugins)
        subCommands = set(
            name for name, shortcut, parser, doc in options.subCommands
        )

        self.assertEqual(subCommands, plugins)


    def test_postOptionsNoSubCommand(self):
        """
        L{TwistOptions.postOptions} raises L{UsageError} is it has no
        sub-command.
        """
        options = TwistOptions()

        self.assertRaises(UsageError, options.postOptions)
