# -*- test-case-name: twisted.application.runner.test.test_runner -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted application runner.
"""

__all__ = [
    "Runner",
    "RunnerOptions",
]

from sys import stderr
from signal import SIGTERM
from os import getpid, kill

from twisted.python.constants import Names, NamedConstant
from twisted.logger import (
    globalLogBeginner, textFileLogObserver,
    FilteringLogObserver, LogLevelFilterPredicate,
    LogLevel, Logger,
)
from twisted.internet import default as defaultReactor
from ._exit import exit, ExitStatus



class Runner(object):
    """
    Twisted application runner.
    """

    log = Logger()


    def __init__(self, options):
        """
        @param options: Configuration options for this runner.
        @type options: mapping of L{RunnerOptions} to values
        """
        self.options = options


    def run(self):
        """
        Run this command.
        Equivalent to::

            self.killIfRequested()
            self.writePIDFile()
            self.startLogging()
            self.startReactor()
            self.reactorExited()
            self.removePIDFile()

        Additional steps may be added over time, but the order won't change.
        """
        self.killIfRequested()
        self.writePIDFile()
        self.startLogging()
        self.startReactor()
        self.reactorExited()
        self.removePIDFile()


    def killIfRequested(self):
        """
        Kill a running instance of this application if L{RunnerOptions.kill} is
        specified and L{True} in C{self.options}.
        This requires that L{RunnerOptions.pidFilePath} also be specified;
        exit with L{ExitStatus.EX_USAGE} if kill is requested with no PID file.
        """
        pidFilePath = self.options.get(RunnerOptions.pidFilePath)

        if self.options.get(RunnerOptions.kill, False):
            if pidFilePath is None:
                exit(ExitStatus.EX_USAGE, "No PID file specified")
                return  # When testing, patched exit doesn't exit
            else:
                pid = ""
                try:
                    for pid in pidFilePath.open():
                        break
                except EnvironmentError:
                    exit(ExitStatus.EX_IOERR, "Unable to read PID file.")
                    return  # When testing, patched exit doesn't exit
                try:
                    pid = int(pid)
                except ValueError:
                    exit(ExitStatus.EX_DATAERR, "Invalid PID file.")
                    return  # When testing, patched exit doesn't exit

            self.startLogging()
            self.log.info("Terminating process: {pid}", pid=pid)

            kill(pid, SIGTERM)

            exit(ExitStatus.EX_OK)
            return  # When testing, patched exit doesn't exit


    def writePIDFile(self):
        """
        Write a PID file for this application if L{RunnerOptions.pidFilePath}
        is specified in C{self.options}.
        """
        pidFilePath = self.options.get(RunnerOptions.pidFilePath)
        if pidFilePath is not None:
            pid = getpid()
            pidFilePath.setContent(u"{}\n".format(pid).encode("utf-8"))


    def removePIDFile(self):
        """
        Remove the PID file for this application if L{RunnerOptions.pidFilePath}
        is specified in C{self.options}.
        """
        pidFilePath = self.options.get(RunnerOptions.pidFilePath)
        if pidFilePath is not None:
            pidFilePath.remove()


    def startLogging(self):
        """
        Start the L{twisted.logger} logging system.
        """
        logFile = self.options.get(RunnerOptions.logFile, stderr)

        fileLogObserverFactory = self.options.get(
            RunnerOptions.fileLogObserverFactory, textFileLogObserver
        )

        fileLogObserver = fileLogObserverFactory(logFile)

        logLevelPredicate = LogLevelFilterPredicate(
            defaultLogLevel=self.options.get(
                RunnerOptions.defaultLogLevel, LogLevel.info
            )
        )

        filteringObserver = FilteringLogObserver(
            fileLogObserver, [logLevelPredicate]
        )

        globalLogBeginner.beginLoggingTo([filteringObserver])


    def startReactor(self):
        """
        Register C{self.whenRunning} with the reactor so that it is called once
        the reactor is running and start the reactor.
        If L{RunnerOptions.reactor} is specified in C{self.options}, use that
        reactor; otherwise use the default reactor.
        """
        reactor = self.options.get(RunnerOptions.reactor)
        if reactor is None:
            reactor = defaultReactor
            reactor.install()
            self.options[RunnerOptions.reactor] = reactor

        reactor.callWhenRunning(self.whenRunning)

        self.log.info("Starting reactor...")
        reactor.run()


    def whenRunning(self):
        """
        If L{RunnerOptions.whenRunning} is specified in C{self.options}, call
        it.

        @note: This method is called when the reactor is running.
        """
        whenRunning = self.options.get(RunnerOptions.whenRunning)
        if whenRunning is not None:
            whenRunning(self.options)


    def reactorExited(self):
        """
        If L{RunnerOptions.reactorExited} is specified in C{self.options}, call
        it.

        @note: This method is called after the reactor has exited.
        """
        reactorExited = self.options.get(RunnerOptions.reactorExited)
        if reactorExited is not None:
            reactorExited(self.options)



class RunnerOptions(Names):
    """
    Names for options recognized by L{Runner}.
    These are meant to be used as keys in the options given to L{Runner}, with
    corresponding values as noted below.

    @cvar reactor: The reactor to start.
        Corresponding value: L{IReactorCore}.
    @type reactor: L{NamedConstant}

    @cvar pidFilePath: The path to the PID file.
        Corresponding value: L{IFilePath}.
    @type pidFilePath: L{NamedConstant}

    @cvar kill: Whether this runner should kill an existing running instance.
        Corresponding value: L{bool}.
    @type kill: L{NamedConstant}

    @cvar defaultLogLevel: The default log level to start the logging system
        with.
        Corresponding value: L{NamedConstant} from L{LogLevel}.
    @type defaultLogLevel: L{NamedConstant}

    @cvar logFile: A file stream to write logging output to.
        Corresponding value: writable file like object.
    @type logFile: L{NamedConstant}

    @cvar fileLogObserverFactory: What file log observer to use when starting
        the logging system.
        Corresponding value: callable that returns a
        L{twisted.logger.FileLogObserver}
    @type fileLogObserverFactory: L{NamedConstant}

    @cvar whenRunning: Hook to call when the reactor is running.
        This can be considered the Twisted equivalent to C{main()}.
        Corresponding value: callable that takes the options mapping given to
        the runner as an argument.
    @type whenRunning: L{NamedConstant}

    @cvar reactorExited: Hook to call when the reactor has exited.
        Corresponding value: callable that takes an empty arguments list
    @type reactorExited: L{NamedConstant}
    """

    reactor                = NamedConstant()
    pidFilePath            = NamedConstant()
    kill                   = NamedConstant()
    defaultLogLevel        = NamedConstant()
    logFile                = NamedConstant()
    fileLogObserverFactory = NamedConstant()
    whenRunning            = NamedConstant()
    reactorExited          = NamedConstant()
