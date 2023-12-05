# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.runner._runner}.
"""

import errno
from io import StringIO
from signal import SIGTERM
from types import TracebackType
from typing import Any, Iterable, List, Optional, TextIO, Tuple, Type, Union, cast

from attr import Factory, attrib, attrs

import twisted.trial.unittest
from twisted.internet.testing import MemoryReactor
from twisted.logger import (
    FileLogObserver,
    FilteringLogObserver,
    ILogObserver,
    LogBeginner,
    LogLevel,
    LogLevelFilterPredicate,
    LogPublisher,
)
from twisted.python.filepath import FilePath
from ...runner import _runner
from .._exit import ExitStatus
from .._pidfile import NonePIDFile, PIDFile
from .._runner import Runner


class RunnerTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{Runner}.
    """

    def filePath(self, content: Optional[bytes] = None) -> FilePath:
        filePath = FilePath(self.mktemp())
        if content is not None:
            filePath.setContent(content)
        return filePath

    def setUp(self) -> None:
        # Patch exit and kill so we can capture usage and prevent actual exits
        # and kills.

        self.exit = DummyExit()
        self.kill = DummyKill()

        self.patch(_runner, "exit", self.exit)
        self.patch(_runner, "kill", self.kill)

        # Patch getpid so we get a known result

        self.pid = 1337
        self.pidFileContent = f"{self.pid}\n".encode()

        # Patch globalLogBeginner so that we aren't trying to install multiple
        # global log observers.

        self.stdout = StringIO()
        self.stderr = StringIO()
        self.stdio = DummyStandardIO(self.stdout, self.stderr)
        self.warnings = DummyWarningsModule()

        self.globalLogPublisher = LogPublisher()
        self.globalLogBeginner = LogBeginner(
            self.globalLogPublisher,
            self.stdio.stderr,
            self.stdio,
            self.warnings,
        )

        self.patch(_runner, "stderr", self.stderr)
        self.patch(_runner, "globalLogBeginner", self.globalLogBeginner)

    def test_runInOrder(self) -> None:
        """
        L{Runner.run} calls the expected methods in order.
        """
        runner = DummyRunner(reactor=MemoryReactor())
        runner.run()

        self.assertEqual(
            runner.calledMethods,
            [
                "killIfRequested",
                "startLogging",
                "startReactor",
                "reactorExited",
            ],
        )

    def test_runUsesPIDFile(self) -> None:
        """
        L{Runner.run} uses the provided PID file.
        """
        pidFile = DummyPIDFile()

        runner = Runner(reactor=MemoryReactor(), pidFile=pidFile)

        self.assertFalse(pidFile.entered)
        self.assertFalse(pidFile.exited)

        runner.run()

        self.assertTrue(pidFile.entered)
        self.assertTrue(pidFile.exited)

    def test_runAlreadyRunning(self) -> None:
        """
        L{Runner.run} exits with L{ExitStatus.EX_USAGE} and the expected
        message if a process is already running that corresponds to the given
        PID file.
        """
        pidFile = PIDFile(self.filePath(self.pidFileContent))
        pidFile.isRunning = lambda: True  # type: ignore[assignment]

        runner = Runner(reactor=MemoryReactor(), pidFile=pidFile)
        runner.run()

        self.assertEqual(self.exit.status, ExitStatus.EX_CONFIG)
        self.assertEqual(self.exit.message, "Already running.")

    def test_killNotRequested(self) -> None:
        """
        L{Runner.killIfRequested} when C{kill} is false doesn't exit and
        doesn't indiscriminately murder anyone.
        """
        runner = Runner(reactor=MemoryReactor())
        runner.killIfRequested()

        self.assertEqual(self.kill.calls, [])
        self.assertFalse(self.exit.exited)

    def test_killRequestedWithoutPIDFile(self) -> None:
        """
        L{Runner.killIfRequested} when C{kill} is true but C{pidFile} is
        L{nonePIDFile} exits with L{ExitStatus.EX_USAGE} and the expected
        message; and also doesn't indiscriminately murder anyone.
        """
        runner = Runner(reactor=MemoryReactor(), kill=True)
        runner.killIfRequested()

        self.assertEqual(self.kill.calls, [])
        self.assertEqual(self.exit.status, ExitStatus.EX_USAGE)
        self.assertEqual(self.exit.message, "No PID file specified.")

    def test_killRequestedWithPIDFile(self) -> None:
        """
        L{Runner.killIfRequested} when C{kill} is true and given a C{pidFile}
        performs a targeted killing of the appropriate process.
        """
        pidFile = PIDFile(self.filePath(self.pidFileContent))
        runner = Runner(reactor=MemoryReactor(), kill=True, pidFile=pidFile)
        runner.killIfRequested()

        self.assertEqual(self.kill.calls, [(self.pid, SIGTERM)])
        self.assertEqual(self.exit.status, ExitStatus.EX_OK)
        self.assertIdentical(self.exit.message, None)

    def test_killRequestedWithPIDFileCantRead(self) -> None:
        """
        L{Runner.killIfRequested} when C{kill} is true and given a C{pidFile}
        that it can't read exits with L{ExitStatus.EX_IOERR}.
        """
        pidFile = PIDFile(self.filePath(None))

        def read() -> int:
            raise OSError(errno.EACCES, "Permission denied")

        pidFile.read = read  # type: ignore[assignment]

        runner = Runner(reactor=MemoryReactor(), kill=True, pidFile=pidFile)
        runner.killIfRequested()

        self.assertEqual(self.exit.status, ExitStatus.EX_IOERR)
        self.assertEqual(self.exit.message, "Unable to read PID file.")

    def test_killRequestedWithPIDFileEmpty(self) -> None:
        """
        L{Runner.killIfRequested} when C{kill} is true and given a C{pidFile}
        containing no value exits with L{ExitStatus.EX_DATAERR}.
        """
        pidFile = PIDFile(self.filePath(b""))
        runner = Runner(reactor=MemoryReactor(), kill=True, pidFile=pidFile)
        runner.killIfRequested()

        self.assertEqual(self.exit.status, ExitStatus.EX_DATAERR)
        self.assertEqual(self.exit.message, "Invalid PID file.")

    def test_killRequestedWithPIDFileNotAnInt(self) -> None:
        """
        L{Runner.killIfRequested} when C{kill} is true and given a C{pidFile}
        containing a non-integer value exits with L{ExitStatus.EX_DATAERR}.
        """
        pidFile = PIDFile(self.filePath(b"** totally not a number, dude **"))
        runner = Runner(reactor=MemoryReactor(), kill=True, pidFile=pidFile)
        runner.killIfRequested()

        self.assertEqual(self.exit.status, ExitStatus.EX_DATAERR)
        self.assertEqual(self.exit.message, "Invalid PID file.")

    def test_startLogging(self) -> None:
        """
        L{Runner.startLogging} sets up a filtering observer with a log level
        predicate set to the given log level that contains a file observer of
        the given type which writes to the given file.
        """
        logFile = StringIO()

        # Patch the log beginner so that we don't try to start the already
        # running (started by trial) logging system.

        class LogBeginner:
            observers: List[ILogObserver] = []

            def beginLoggingTo(self, observers: Iterable[ILogObserver]) -> None:
                LogBeginner.observers = list(observers)

        self.patch(_runner, "globalLogBeginner", LogBeginner())

        # Patch FilteringLogObserver so we can capture its arguments

        class MockFilteringLogObserver(FilteringLogObserver):
            observer: Optional[ILogObserver] = None
            predicates: List[LogLevelFilterPredicate] = []

            def __init__(
                self,
                observer: ILogObserver,
                predicates: Iterable[LogLevelFilterPredicate],
                negativeObserver: ILogObserver = cast(ILogObserver, lambda event: None),
            ):
                MockFilteringLogObserver.observer = observer
                MockFilteringLogObserver.predicates = list(predicates)
                FilteringLogObserver.__init__(
                    self, observer, predicates, negativeObserver
                )

        self.patch(_runner, "FilteringLogObserver", MockFilteringLogObserver)

        # Patch FileLogObserver so we can capture its arguments

        class MockFileLogObserver(FileLogObserver):
            outFile: Optional[TextIO] = None

            def __init__(self, outFile: TextIO) -> None:
                MockFileLogObserver.outFile = outFile
                FileLogObserver.__init__(self, outFile, str)

        # Start logging
        runner = Runner(
            reactor=MemoryReactor(),
            defaultLogLevel=LogLevel.critical,
            logFile=logFile,
            fileLogObserverFactory=MockFileLogObserver,
        )
        runner.startLogging()

        # Check for a filtering observer
        self.assertEqual(len(LogBeginner.observers), 1)
        self.assertIsInstance(LogBeginner.observers[0], FilteringLogObserver)

        # Check log level predicate with the correct default log level
        self.assertEqual(len(MockFilteringLogObserver.predicates), 1)
        self.assertIsInstance(
            MockFilteringLogObserver.predicates[0], LogLevelFilterPredicate
        )
        self.assertIdentical(
            MockFilteringLogObserver.predicates[0].defaultLogLevel, LogLevel.critical
        )

        # Check for a file observer attached to the filtering observer
        observer = cast(MockFileLogObserver, MockFilteringLogObserver.observer)
        self.assertIsInstance(observer, MockFileLogObserver)

        # Check for the file we gave it
        self.assertIdentical(observer.outFile, logFile)

    def test_startReactorWithReactor(self) -> None:
        """
        L{Runner.startReactor} with the C{reactor} argument runs the given
        reactor.
        """
        reactor = MemoryReactor()
        runner = Runner(reactor=reactor)
        runner.startReactor()

        self.assertTrue(reactor.hasRun)

    def test_startReactorWhenRunning(self) -> None:
        """
        L{Runner.startReactor} ensures that C{whenRunning} is called with
        C{whenRunningArguments} when the reactor is running.
        """
        self._testHook("whenRunning", "startReactor")

    def test_whenRunningWithArguments(self) -> None:
        """
        L{Runner.whenRunning} calls C{whenRunning} with
        C{whenRunningArguments}.
        """
        self._testHook("whenRunning")

    def test_reactorExitedWithArguments(self) -> None:
        """
        L{Runner.whenRunning} calls C{reactorExited} with
        C{reactorExitedArguments}.
        """
        self._testHook("reactorExited")

    def _testHook(self, methodName: str, callerName: Optional[str] = None) -> None:
        """
        Verify that the named hook is run with the expected arguments as
        specified by the arguments used to create the L{Runner}, when the
        specified caller is invoked.

        @param methodName: The name of the hook to verify.

        @param callerName: The name of the method that is expected to cause the
            hook to be called.
            If C{None}, use the L{Runner} method with the same name as the
            hook.
        """
        if callerName is None:
            callerName = methodName

        arguments = dict(a=object(), b=object(), c=object())
        argumentsSeen = []

        def hook(**arguments: object) -> None:
            argumentsSeen.append(arguments)

        runnerArguments = {
            methodName: hook,
            f"{methodName}Arguments": arguments.copy(),
        }
        runner = Runner(
            reactor=MemoryReactor(), **runnerArguments  # type: ignore[arg-type]
        )

        hookCaller = getattr(runner, callerName)
        hookCaller()

        self.assertEqual(len(argumentsSeen), 1)
        self.assertEqual(argumentsSeen[0], arguments)


@attrs(frozen=True)
class DummyRunner(Runner):
    """
    Stub for L{Runner}.

    Keep track of calls to some methods without actually doing anything.
    """

    calledMethods = attrib(type=List[str], default=Factory(list))

    def killIfRequested(self) -> None:
        self.calledMethods.append("killIfRequested")

    def startLogging(self) -> None:
        self.calledMethods.append("startLogging")

    def startReactor(self) -> None:
        self.calledMethods.append("startReactor")

    def reactorExited(self) -> None:
        self.calledMethods.append("reactorExited")


class DummyPIDFile(NonePIDFile):
    """
    Stub for L{PIDFile}.

    Tracks context manager entry/exit without doing anything.
    """

    def __init__(self) -> None:
        NonePIDFile.__init__(self)

        self.entered = False
        self.exited = False

    def __enter__(self) -> "DummyPIDFile":
        self.entered = True
        return self

    def __exit__(
        self,
        excType: Optional[Type[BaseException]],
        excValue: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.exited = True


class DummyExit:
    """
    Stub for L{_exit.exit} that remembers whether it's been called and, if it has,
    what arguments it was given.
    """

    def __init__(self) -> None:
        self.exited = False

    def __call__(
        self, status: Union[int, ExitStatus], message: Optional[str] = None
    ) -> None:
        assert not self.exited

        self.status = status
        self.message = message
        self.exited = True


class DummyKill:
    """
    Stub for L{os.kill} that remembers whether it's been called and, if it has,
    what arguments it was given.
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[int, int]] = []

    def __call__(self, pid: int, sig: int) -> None:
        self.calls.append((pid, sig))


class DummyStandardIO:
    """
    Stub for L{sys} which provides L{StringIO} streams as stdout and stderr.
    """

    def __init__(self, stdout: TextIO, stderr: TextIO) -> None:
        self.stdout = stdout
        self.stderr = stderr


class DummyWarningsModule:
    """
    Stub for L{warnings} which provides a C{showwarning} method that is a no-op.
    """

    def showwarning(*args: Any, **kwargs: Any) -> None:
        """
        Do nothing.

        @param args: ignored.
        @param kwargs: ignored.
        """
