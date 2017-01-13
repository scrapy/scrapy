# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.twist._twist}.
"""

from sys import stdout

from twisted.logger import LogLevel, jsonFileLogObserver
from twisted.test.proto_helpers import MemoryReactor
from ...service import IService, MultiService
from ...runner._exit import ExitStatus
from ...runner._runner import Runner, RunnerOptions
from ...runner.test.test_runner import DummyExit
from ...twist import _options, _twist
from .._options import TwistOptions
from .._twist import Twist

import twisted.trial.unittest



class TwistTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{Twist}.
    """

    def setUp(self):
        self.patchInstallReactor()


    def patchExit(self):
        """
        Patch L{_twist.exit} so we can capture usage and prevent actual exits.
        """
        self.exit = DummyExit()
        self.patch(_twist, "exit", self.exit)


    def patchInstallReactor(self):
        """
        Patch C{_options.installReactor} so we can capture usage and prevent
        actual installs.
        """
        self.installedReactors = {}

        def installReactor(name):
            reactor = MemoryReactor()
            self.installedReactors[name] = reactor
            return reactor

        self.patch(_options, "installReactor", installReactor)


    def patchStartService(self):
        """
        Patch L{MultiService.startService} so we can capture usage and prevent
        actual starts.
        """
        self.serviceStarts = []

        def startService(service):
            self.serviceStarts.append(service)

        self.patch(MultiService, "startService", startService)


    def test_optionsValidArguments(self):
        """
        L{Twist.options} given valid arguments returns options.
        """
        options = Twist.options(["twist", "web"])

        self.assertIsInstance(options, TwistOptions)


    def test_optionsInvalidArguments(self):
        """
        L{Twist.options} given invalid arguments exits with
        L{ExitStatus.EX_USAGE} and an error/usage message.
        """
        self.patchExit()

        Twist.options(["twist", "--bogus-bagels"])

        self.assertIdentical(self.exit.status, ExitStatus.EX_USAGE)
        self.assertTrue(self.exit.message.startswith("Error: "))
        self.assertTrue(self.exit.message.endswith(
            "\n\n{}".format(TwistOptions())
        ))


    def test_service(self):
        """
        L{Twist.service} returns an L{IService}.
        """
        options = Twist.options(["twist", "web"])  # web should exist
        service = Twist.service(options.plugins["web"], options.subOptions)
        self.assertTrue(IService.providedBy(service))


    def test_startService(self):
        """
        L{Twist.startService} starts the service and registers a trigger to
        stop the service when the reactor shuts down.
        """
        options = Twist.options(["twist", "web"])

        reactor = options["reactor"]
        service = Twist.service(
            plugin=options.plugins[options.subCommand],
            options=options.subOptions,
        )

        self.patchStartService()

        Twist.startService(reactor, service)

        self.assertEqual(self.serviceStarts, [service])
        self.assertEqual(
            reactor.triggers["before"]["shutdown"],
            [(service.stopService, (), {})]
        )


    def test_runnerOptions(self):
        """
        L{Twist.runnerOptions} translates L{TwistOptions} to a L{RunnerOptions}
        map.
        """
        options = Twist.options([
            "twist", "--reactor=default", "--log-format=json", "web"
        ])

        self.assertEqual(
            Twist.runnerOptions(options),
            {
                RunnerOptions.reactor: self.installedReactors["default"],
                RunnerOptions.defaultLogLevel: LogLevel.info,
                RunnerOptions.logFile: stdout,
                RunnerOptions.fileLogObserverFactory: jsonFileLogObserver,
            }
        )


    def test_run(self):
        """
        L{Twist.run} runs the runner with the given options.
        """
        options = TwistOptions()
        runner = Runner(options)

        optionsSeen = []

        self.patch(
            Runner, "run", lambda self: optionsSeen.append(self.options)
        )

        runner.run()

        self.assertEqual(len(optionsSeen), 1)
        self.assertIdentical(optionsSeen[0], options)


    def test_main(self):
        """
        L{Twist.run} runs the runner with options corresponding to the given
        arguments.
        """
        self.patchStartService()

        runners = []

        class Runner(object):
            def __init__(self, options):
                self.options = options
                self.runs = 0
                runners.append(self)

            def run(self):
                self.runs += 1

        self.patch(_twist, "Runner", Runner)

        Twist.main([
            "twist", "--reactor=default", "--log-format=json", "web"
        ])

        self.assertEqual(len(self.serviceStarts), 1)
        self.assertEqual(len(runners), 1)
        self.assertEqual(
            runners[0].options,
            {
                RunnerOptions.reactor: self.installedReactors["default"],
                RunnerOptions.defaultLogLevel: LogLevel.info,
                RunnerOptions.logFile: stdout,
                RunnerOptions.fileLogObserverFactory: jsonFileLogObserver,
            }
        )
        self.assertEqual(runners[0].runs, 1)
