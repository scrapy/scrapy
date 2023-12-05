# -*- test-case-name: twisted.runner.test.test_procmon -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Support for starting, monitoring, and restarting child process.
"""
from typing import Dict, List, Optional

import attr
import incremental

from twisted.application import service
from twisted.internet import error, protocol, reactor as _reactor
from twisted.logger import Logger
from twisted.protocols import basic
from twisted.python import deprecate


@attr.s(frozen=True, auto_attribs=True)
class _Process:
    """
    The parameters of a process to be restarted.

    @ivar args: command-line arguments (including name of command as first one)
    @type args: C{list}

    @ivar uid: user-id to run process as, or None (which means inherit uid)
    @type uid: C{int}

    @ivar gid: group-id to run process as, or None (which means inherit gid)
    @type gid: C{int}

    @ivar env: environment for process
    @type env: C{dict}

    @ivar cwd: initial working directory for process or None
               (which means inherit cwd)
    @type cwd: C{str}
    """

    args: List[str]
    uid: Optional[int] = None
    gid: Optional[int] = None
    env: Dict[str, str] = attr.ib(default=attr.Factory(dict))
    cwd: Optional[str] = None

    @deprecate.deprecated(incremental.Version("Twisted", 18, 7, 0))
    def toTuple(self):
        """
        Convert process to tuple.

        Convert process to tuple that looks like the legacy structure
        of processes, for potential users who inspected processes
        directly.

        This was only an accidental feature, and will be removed. If
        you need to remember what processes were added to a process monitor,
        keep track of that when they are added. The process list
        inside the process monitor is no longer a public API.

        This allows changing the internal structure of the process list,
        when warranted by bug fixes or additional features.

        @return: tuple representation of process
        """
        return (self.args, self.uid, self.gid, self.env)


class DummyTransport:

    disconnecting = 0


transport = DummyTransport()


class LineLogger(basic.LineReceiver):

    tag = None
    stream = None
    delimiter = b"\n"
    service = None

    def lineReceived(self, line):
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError:
            line = repr(line)

        self.service.log.info(
            "[{tag}] {line}", tag=self.tag, line=line, stream=self.stream
        )


class LoggingProtocol(protocol.ProcessProtocol):

    service = None
    name = None

    def connectionMade(self):
        self._output = LineLogger()
        self._output.tag = self.name
        self._output.stream = "stdout"
        self._output.service = self.service
        self._outputEmpty = True

        self._error = LineLogger()
        self._error.tag = self.name
        self._error.stream = "stderr"
        self._error.service = self.service
        self._errorEmpty = True

        self._output.makeConnection(transport)
        self._error.makeConnection(transport)

    def outReceived(self, data):
        self._output.dataReceived(data)
        self._outputEmpty = data[-1] == b"\n"

    def errReceived(self, data):
        self._error.dataReceived(data)
        self._errorEmpty = data[-1] == b"\n"

    def processEnded(self, reason):
        if not self._outputEmpty:
            self._output.dataReceived(b"\n")
        if not self._errorEmpty:
            self._error.dataReceived(b"\n")
        self.service.connectionLost(self.name)

    @property
    def output(self):
        return self._output

    @property
    def empty(self):
        return self._outputEmpty


class ProcessMonitor(service.Service):
    """
    ProcessMonitor runs processes, monitors their progress, and restarts
    them when they die.

    The ProcessMonitor will not attempt to restart a process that appears to
    die instantly -- with each "instant" death (less than 1 second, by
    default), it will delay approximately twice as long before restarting
    it.  A successful run will reset the counter.

    The primary interface is L{addProcess} and L{removeProcess}. When the
    service is running (that is, when the application it is attached to is
    running), adding a process automatically starts it.

    Each process has a name. This name string must uniquely identify the
    process.  In particular, attempting to add two processes with the same
    name will result in a C{KeyError}.

    @type threshold: C{float}
    @ivar threshold: How long a process has to live before the death is
        considered instant, in seconds.  The default value is 1 second.

    @type killTime: C{float}
    @ivar killTime: How long a process being killed has to get its affairs
        in order before it gets killed with an unmaskable signal.  The
        default value is 5 seconds.

    @type minRestartDelay: C{float}
    @ivar minRestartDelay: The minimum time (in seconds) to wait before
        attempting to restart a process.  Default 1s.

    @type maxRestartDelay: C{float}
    @ivar maxRestartDelay: The maximum time (in seconds) to wait before
        attempting to restart a process.  Default 3600s (1h).

    @type _reactor: L{IReactorProcess} provider
    @ivar _reactor: A provider of L{IReactorProcess} and L{IReactorTime}
        which will be used to spawn processes and register delayed calls.

    @type log: L{Logger}
    @ivar log: The logger used to propagate log messages from spawned
        processes.

    """

    threshold = 1
    killTime = 5
    minRestartDelay = 1
    maxRestartDelay = 3600
    log = Logger()

    def __init__(self, reactor=_reactor):
        self._reactor = reactor

        self._processes = {}
        self.protocols = {}
        self.delay = {}
        self.timeStarted = {}
        self.murder = {}
        self.restart = {}

    @deprecate.deprecatedProperty(incremental.Version("Twisted", 18, 7, 0))
    def processes(self):
        """
        Processes as dict of tuples

        @return: Dict of process name to monitored processes as tuples
        """
        return {name: process.toTuple() for name, process in self._processes.items()}

    @deprecate.deprecated(incremental.Version("Twisted", 18, 7, 0))
    def __getstate__(self):
        dct = service.Service.__getstate__(self)
        del dct["_reactor"]
        dct["protocols"] = {}
        dct["delay"] = {}
        dct["timeStarted"] = {}
        dct["murder"] = {}
        dct["restart"] = {}
        del dct["_processes"]
        dct["processes"] = self.processes
        return dct

    def addProcess(self, name, args, uid=None, gid=None, env={}, cwd=None):
        """
        Add a new monitored process and start it immediately if the
        L{ProcessMonitor} service is running.

        Note that args are passed to the system call, not to the shell. If
        running the shell is desired, the common idiom is to use
        C{ProcessMonitor.addProcess("name", ['/bin/sh', '-c', shell_script])}

        @param name: A name for this process.  This value must be
            unique across all processes added to this monitor.
        @type name: C{str}
        @param args: The argv sequence for the process to launch.
        @param uid: The user ID to use to run the process.  If L{None},
            the current UID is used.
        @type uid: C{int}
        @param gid: The group ID to use to run the process.  If L{None},
            the current GID is used.
        @type uid: C{int}
        @param env: The environment to give to the launched process. See
            L{IReactorProcess.spawnProcess}'s C{env} parameter.
        @type env: C{dict}
        @param cwd: The initial working directory of the launched process.
            The default of C{None} means inheriting the laucnhing process's
            working directory.
        @type env: C{dict}
        @raise KeyError: If a process with the given name already exists.
        """
        if name in self._processes:
            raise KeyError(f"remove {name} first")
        self._processes[name] = _Process(args, uid, gid, env, cwd)
        self.delay[name] = self.minRestartDelay
        if self.running:
            self.startProcess(name)

    def removeProcess(self, name):
        """
        Stop the named process and remove it from the list of monitored
        processes.

        @type name: C{str}
        @param name: A string that uniquely identifies the process.
        """
        self.stopProcess(name)
        del self._processes[name]

    def startService(self):
        """
        Start all monitored processes.
        """
        service.Service.startService(self)
        for name in list(self._processes):
            self.startProcess(name)

    def stopService(self):
        """
        Stop all monitored processes and cancel all scheduled process restarts.
        """
        service.Service.stopService(self)

        # Cancel any outstanding restarts
        for name, delayedCall in list(self.restart.items()):
            if delayedCall.active():
                delayedCall.cancel()

        for name in list(self._processes):
            self.stopProcess(name)

    def connectionLost(self, name):
        """
        Called when a monitored processes exits. If
        L{service.IService.running} is L{True} (ie the service is started), the
        process will be restarted.
        If the process had been running for more than
        L{ProcessMonitor.threshold} seconds it will be restarted immediately.
        If the process had been running for less than
        L{ProcessMonitor.threshold} seconds, the restart will be delayed and
        each time the process dies before the configured threshold, the restart
        delay will be doubled - up to a maximum delay of maxRestartDelay sec.

        @type name: C{str}
        @param name: A string that uniquely identifies the process
            which exited.
        """
        # Cancel the scheduled _forceStopProcess function if the process
        # dies naturally
        if name in self.murder:
            if self.murder[name].active():
                self.murder[name].cancel()
            del self.murder[name]

        del self.protocols[name]

        if self._reactor.seconds() - self.timeStarted[name] < self.threshold:
            # The process died too fast - backoff
            nextDelay = self.delay[name]
            self.delay[name] = min(self.delay[name] * 2, self.maxRestartDelay)

        else:
            # Process had been running for a significant amount of time
            # restart immediately
            nextDelay = 0
            self.delay[name] = self.minRestartDelay

        # Schedule a process restart if the service is running
        if self.running and name in self._processes:
            self.restart[name] = self._reactor.callLater(
                nextDelay, self.startProcess, name
            )

    def startProcess(self, name):
        """
        @param name: The name of the process to be started
        """
        # If a protocol instance already exists, it means the process is
        # already running
        if name in self.protocols:
            return

        process = self._processes[name]

        proto = LoggingProtocol()
        proto.service = self
        proto.name = name
        self.protocols[name] = proto
        self.timeStarted[name] = self._reactor.seconds()
        self._reactor.spawnProcess(
            proto,
            process.args[0],
            process.args,
            uid=process.uid,
            gid=process.gid,
            env=process.env,
            path=process.cwd,
        )

    def _forceStopProcess(self, proc):
        """
        @param proc: An L{IProcessTransport} provider
        """
        try:
            proc.signalProcess("KILL")
        except error.ProcessExitedAlready:
            pass

    def stopProcess(self, name):
        """
        @param name: The name of the process to be stopped
        """
        if name not in self._processes:
            raise KeyError(f"Unrecognized process name: {name}")

        proto = self.protocols.get(name, None)
        if proto is not None:
            proc = proto.transport
            try:
                proc.signalProcess("TERM")
            except error.ProcessExitedAlready:
                pass
            else:
                self.murder[name] = self._reactor.callLater(
                    self.killTime, self._forceStopProcess, proc
                )

    def restartAll(self):
        """
        Restart all processes. This is useful for third party management
        services to allow a user to restart servers because of an outside change
        in circumstances -- for example, a new version of a library is
        installed.
        """
        for name in self._processes:
            self.stopProcess(name)

    def __repr__(self) -> str:
        lst = []
        for name, proc in self._processes.items():
            uidgid = ""
            if proc.uid is not None:
                uidgid = str(proc.uid)
            if proc.gid is not None:
                uidgid += ":" + str(proc.gid)

            if uidgid:
                uidgid = "(" + uidgid + ")"
            lst.append(f"{name!r}{uidgid}: {proc.args!r}")
        return "<" + self.__class__.__name__ + " " + " ".join(lst) + ">"
