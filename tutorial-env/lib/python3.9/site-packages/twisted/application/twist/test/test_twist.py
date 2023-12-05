# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.twist._twist}.
"""

from sys import stdout
from typing import Any, Dict, List

import twisted.trial.unittest
from twisted.internet.interfaces import IReactorCore
from twisted.logger import LogLevel, jsonFileLogObserver
from twisted.test.proto_helpers import MemoryReactor
from twisted.test.test_twistd import SignalCapturingMemoryReactor
from ...runner._exit import ExitStatus
from ...runner._runner import Runner
from ...runner.test.test_runner import DummyExit
from ...service import IService, MultiService
from ...twist import _twist
from .._options import TwistOptions
from .._twist import Twist


class TwistTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{Twist}.
    """

    def setUp(self) -> None:
        self.patchInstallReactor()

    def patchExit(self) -> None:
        """
        Patch L{_twist.exit} so we can capture usage and prevent actual exits.
        """
        self.exit = DummyExit()
        self.patch(_twist, "exit", self.exit)

    def patchInstallReactor(self) -> None:
        """
        Patch C{_options.installReactor} so we can capture usage and prevent
        actual installs.
        """
        self.installedReactors: Dict[str, IReactorCore] = {}

        def installReactor(_: TwistOptions, name: str) -> IReactorCore:
            reactor = MemoryReactor()
            self.installedReactors[name] = reactor
            return reactor

        self.patch(TwistOptions, "installReactor", installReactor)

    def patchStartService(self) -> None:
        """
        Patch L{MultiService.startService} so we can capture usage and prevent
        actual starts.
        """
        self.serviceStarts: List[IService] = []

        def startService(service: IService) -> None:
            self.serviceStarts.append(service)

        self.patch(MultiService, "startService", startService)

    def test_optionsValidArguments(self) -> None:
        """
        L{Twist.options} given valid arguments returns options.
        """
        options = Twist.options(["twist", "web"])

        self.assertIsInstance(options, TwistOptions)

    def test_optionsInvalidArguments(self) -> None:
        """
        L{Twist.options} given invalid arguments exits with
        L{ExitStatus.EX_USAGE} and an error/usage message.
        """
        self.patchExit()

        Twist.options(["twist", "--bogus-bagels"])

        self.assertIdentical(self.exit.status, ExitStatus.EX_USAGE)
        self.assertIsNotNone(self.exit.message)
        self.assertTrue(
            self.exit.message.startswith("Error: ")  # type: ignore[union-attr]
        )
        self.assertTrue(
            self.exit.message.endswith(  # type: ignore[union-attr]
                f"\n\n{TwistOptions()}"
            )
        )

    def test_service(self) -> None:
        """
        L{Twist.service} returns an L{IService}.
        """
        options = Twist.options(["twist", "web"])  # web should exist
        service = Twist.service(options.plugins["web"], options.subOptions)
        self.assertTrue(IService.providedBy(service))

    def test_startService(self) -> None:
        """
        L{Twist.startService} starts the service and registers a trigger to
        stop the service when the reactor shuts down.
        """
        options = Twist.options(["twist", "web"])

        reactor = options["reactor"]
        subCommand = options.subCommand
        assert subCommand is not None
        service = Twist.service(
            plugin=options.plugins[subCommand],
            options=options.subOptions,
        )

        self.patchStartService()

        Twist.startService(reactor, service)

        self.assertEqual(self.serviceStarts, [service])
        self.assertEqual(
            reactor.triggers["before"]["shutdown"], [(service.stopService, (), {})]
        )

    def test_run(self) -> None:
        """
        L{Twist.run} runs the runner with arguments corresponding to the given
        options.
        """
        argsSeen = []

        self.patch(Runner, "__init__", lambda self, **args: argsSeen.append(args))
        self.patch(Runner, "run", lambda self: None)

        twistOptions = Twist.options(
            ["twist", "--reactor=default", "--log-format=json", "web"]
        )
        Twist.run(twistOptions)

        self.assertEqual(len(argsSeen), 1)
        self.assertEqual(
            argsSeen[0],
            dict(
                reactor=self.installedReactors["default"],
                defaultLogLevel=LogLevel.info,
                logFile=stdout,
                fileLogObserverFactory=jsonFileLogObserver,
            ),
        )

    def test_main(self) -> None:
        """
        L{Twist.main} runs the runner with arguments corresponding to the given
        command line arguments.
        """
        self.patchStartService()

        runners = []

        class Runner:
            def __init__(self, **kwargs: Any) -> None:
                self.args = kwargs
                self.runs = 0
                runners.append(self)

            def run(self) -> None:
                self.runs += 1

        self.patch(_twist, "Runner", Runner)

        Twist.main(["twist", "--reactor=default", "--log-format=json", "web"])

        self.assertEqual(len(self.serviceStarts), 1)
        self.assertEqual(len(runners), 1)
        self.assertEqual(
            runners[0].args,
            dict(
                reactor=self.installedReactors["default"],
                defaultLogLevel=LogLevel.info,
                logFile=stdout,
                fileLogObserverFactory=jsonFileLogObserver,
            ),
        )
        self.assertEqual(runners[0].runs, 1)


class TwistExitTests(twisted.trial.unittest.TestCase):
    """
    Tests to verify that the Twist script takes the expected actions related
    to signals and the reactor.
    """

    def setUp(self) -> None:
        self.exitWithSignalCalled = False

        def fakeExitWithSignal(sig: int) -> None:
            """
            Fake to capture whether L{twisted.application._exitWithSignal
            was called.

            @param sig: Signal value
            @type sig: C{int}
            """
            self.exitWithSignalCalled = True

        self.patch(_twist, "_exitWithSignal", fakeExitWithSignal)

        def startLogging(_: Runner) -> None:
            """
            Prevent Runner from adding new log observers or other
            tests outside this module will fail.

            @param _: Unused self param
            """

        self.patch(Runner, "startLogging", startLogging)

    def test_twistReactorDoesntExitWithSignal(self) -> None:
        """
        _exitWithSignal is not called if the reactor's _exitSignal attribute
        is zero.
        """
        reactor = SignalCapturingMemoryReactor()
        reactor._exitSignal = None
        options = TwistOptions()
        options["reactor"] = reactor
        options["fileLogObserverFactory"] = jsonFileLogObserver

        Twist.run(options)
        self.assertFalse(self.exitWithSignalCalled)

    def test_twistReactorHasNoExitSignalAttr(self) -> None:
        """
        _exitWithSignal is not called if the runner's reactor does not
        implement L{twisted.internet.interfaces._ISupportsExitSignalCapturing}
        """
        reactor = MemoryReactor()
        options = TwistOptions()
        options["reactor"] = reactor
        options["fileLogObserverFactory"] = jsonFileLogObserver
        Twist.run(options)
        self.assertFalse(self.exitWithSignalCalled)

    def test_twistReactorExitsWithSignal(self) -> None:
        """
        _exitWithSignal is called if the runner's reactor exits due
        to a signal.
        """
        reactor = SignalCapturingMemoryReactor()
        reactor._exitSignal = 2
        options = TwistOptions()
        options["reactor"] = reactor
        options["fileLogObserverFactory"] = jsonFileLogObserver
        Twist.run(options)
        self.assertTrue(self.exitWithSignalCalled)
