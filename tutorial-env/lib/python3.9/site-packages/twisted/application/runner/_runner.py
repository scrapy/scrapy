# -*- test-case-name: twisted.application.runner.test.test_runner -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted application runner.
"""

from os import kill
from signal import SIGTERM
from sys import stderr
from typing import Any, Callable, Mapping, TextIO

from attr import Factory, attrib, attrs
from constantly import NamedConstant  # type: ignore[import]

from twisted.internet.interfaces import IReactorCore
from twisted.logger import (
    FileLogObserver,
    FilteringLogObserver,
    Logger,
    LogLevel,
    LogLevelFilterPredicate,
    globalLogBeginner,
    textFileLogObserver,
)
from ._exit import ExitStatus, exit
from ._pidfile import AlreadyRunningError, InvalidPIDFileError, IPIDFile, nonePIDFile


@attrs(frozen=True)
class Runner:
    """
    Twisted application runner.

    @cvar _log: The logger attached to this class.

    @ivar _reactor: The reactor to start and run the application in.
    @ivar _pidFile: The file to store the running process ID in.
    @ivar _kill: Whether this runner should kill an existing running
        instance of the application.
    @ivar _defaultLogLevel: The default log level to start the logging
        system with.
    @ivar _logFile: A file stream to write logging output to.
    @ivar _fileLogObserverFactory: A factory for the file log observer to
        use when starting the logging system.
    @ivar _whenRunning: Hook to call after the reactor is running;
        this is where the application code that relies on the reactor gets
        called.
    @ivar _whenRunningArguments: Keyword arguments to pass to
        C{whenRunning} when it is called.
    @ivar _reactorExited: Hook to call after the reactor exits.
    @ivar _reactorExitedArguments: Keyword arguments to pass to
        C{reactorExited} when it is called.
    """

    _log = Logger()

    _reactor = attrib(type=IReactorCore)
    _pidFile = attrib(type=IPIDFile, default=nonePIDFile)
    _kill = attrib(type=bool, default=False)
    _defaultLogLevel = attrib(type=NamedConstant, default=LogLevel.info)
    _logFile = attrib(type=TextIO, default=stderr)
    _fileLogObserverFactory = attrib(
        type=Callable[[TextIO], FileLogObserver], default=textFileLogObserver
    )
    _whenRunning = attrib(type=Callable[..., None], default=lambda **_: None)
    _whenRunningArguments = attrib(type=Mapping[str, Any], default=Factory(dict))
    _reactorExited = attrib(type=Callable[..., None], default=lambda **_: None)
    _reactorExitedArguments = attrib(type=Mapping[str, Any], default=Factory(dict))

    def run(self) -> None:
        """
        Run this command.
        """
        pidFile = self._pidFile

        self.killIfRequested()

        try:
            with pidFile:
                self.startLogging()
                self.startReactor()
                self.reactorExited()

        except AlreadyRunningError:
            exit(ExitStatus.EX_CONFIG, "Already running.")
            # When testing, patched exit doesn't exit
            return  # type: ignore[unreachable]

    def killIfRequested(self) -> None:
        """
        If C{self._kill} is true, attempt to kill a running instance of the
        application.
        """
        pidFile = self._pidFile

        if self._kill:
            if pidFile is nonePIDFile:
                exit(ExitStatus.EX_USAGE, "No PID file specified.")
                # When testing, patched exit doesn't exit
                return  # type: ignore[unreachable]

            try:
                pid = pidFile.read()
            except OSError:
                exit(ExitStatus.EX_IOERR, "Unable to read PID file.")
                # When testing, patched exit doesn't exit
                return  # type: ignore[unreachable]
            except InvalidPIDFileError:
                exit(ExitStatus.EX_DATAERR, "Invalid PID file.")
                # When testing, patched exit doesn't exit
                return  # type: ignore[unreachable]

            self.startLogging()
            self._log.info("Terminating process: {pid}", pid=pid)

            kill(pid, SIGTERM)

            exit(ExitStatus.EX_OK)
            # When testing, patched exit doesn't exit
            return  # type: ignore[unreachable]

    def startLogging(self) -> None:
        """
        Start the L{twisted.logger} logging system.
        """
        logFile = self._logFile

        fileLogObserverFactory = self._fileLogObserverFactory

        fileLogObserver = fileLogObserverFactory(logFile)

        logLevelPredicate = LogLevelFilterPredicate(
            defaultLogLevel=self._defaultLogLevel
        )

        filteringObserver = FilteringLogObserver(fileLogObserver, [logLevelPredicate])

        globalLogBeginner.beginLoggingTo([filteringObserver])

    def startReactor(self) -> None:
        """
        Register C{self._whenRunning} with the reactor so that it is called
        once the reactor is running, then start the reactor.
        """
        self._reactor.callWhenRunning(self.whenRunning)

        self._log.info("Starting reactor...")
        self._reactor.run()

    def whenRunning(self) -> None:
        """
        Call C{self._whenRunning} with C{self._whenRunningArguments}.

        @note: This method is called after the reactor starts running.
        """
        self._whenRunning(**self._whenRunningArguments)

    def reactorExited(self) -> None:
        """
        Call C{self._reactorExited} with C{self._reactorExitedArguments}.

        @note: This method is called after the reactor exits.
        """
        self._reactorExited(**self._reactorExitedArguments)
