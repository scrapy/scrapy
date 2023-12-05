# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.runner.procmon}.
"""
import pickle

from twisted.internet.error import ProcessDone, ProcessExitedAlready, ProcessTerminated
from twisted.internet.task import Clock
from twisted.logger import globalLogPublisher
from twisted.python.failure import Failure
from twisted.runner.procmon import LoggingProtocol, ProcessMonitor
from twisted.test.proto_helpers import MemoryReactor
from twisted.trial import unittest


class DummyProcess:
    """
    An incomplete and fake L{IProcessTransport} implementation for testing how
    L{ProcessMonitor} behaves when its monitored processes exit.

    @ivar _terminationDelay: the delay in seconds after which the DummyProcess
        will appear to exit when it receives a TERM signal
    """

    pid = 1
    proto = None

    _terminationDelay = 1

    def __init__(
        self,
        reactor,
        executable,
        args,
        environment,
        path,
        proto,
        uid=None,
        gid=None,
        usePTY=0,
        childFDs=None,
    ):

        self.proto = proto

        self._reactor = reactor
        self._executable = executable
        self._args = args
        self._environment = environment
        self._path = path
        self._uid = uid
        self._gid = gid
        self._usePTY = usePTY
        self._childFDs = childFDs

    def signalProcess(self, signalID):
        """
        A partial implementation of signalProcess which can only handle TERM and
        KILL signals.
         - When a TERM signal is given, the dummy process will appear to exit
           after L{DummyProcess._terminationDelay} seconds with exit code 0
         - When a KILL signal is given, the dummy process will appear to exit
           immediately with exit code 1.

        @param signalID: The signal name or number to be issued to the process.
        @type signalID: C{str}
        """
        params = {"TERM": (self._terminationDelay, 0), "KILL": (0, 1)}

        if self.pid is None:
            raise ProcessExitedAlready()

        if signalID in params:
            delay, status = params[signalID]
            self._signalHandler = self._reactor.callLater(
                delay, self.processEnded, status
            )

    def processEnded(self, status):
        """
        Deliver the process ended event to C{self.proto}.
        """
        self.pid = None
        statusMap = {
            0: ProcessDone,
            1: ProcessTerminated,
        }
        self.proto.processEnded(Failure(statusMap[status](status)))


class DummyProcessReactor(MemoryReactor, Clock):
    """
    @ivar spawnedProcesses: a list that keeps track of the fake process
        instances built by C{spawnProcess}.
    @type spawnedProcesses: C{list}
    """

    def __init__(self):
        MemoryReactor.__init__(self)
        Clock.__init__(self)

        self.spawnedProcesses = []

    def spawnProcess(
        self,
        processProtocol,
        executable,
        args=(),
        env={},
        path=None,
        uid=None,
        gid=None,
        usePTY=0,
        childFDs=None,
    ):
        """
        Fake L{reactor.spawnProcess}, that logs all the process
        arguments and returns a L{DummyProcess}.
        """

        proc = DummyProcess(
            self,
            executable,
            args,
            env,
            path,
            processProtocol,
            uid,
            gid,
            usePTY,
            childFDs,
        )
        processProtocol.makeConnection(proc)
        self.spawnedProcesses.append(proc)
        return proc


class ProcmonTests(unittest.TestCase):
    """
    Tests for L{ProcessMonitor}.
    """

    def setUp(self):
        """
        Create an L{ProcessMonitor} wrapped around a fake reactor.
        """
        self.reactor = DummyProcessReactor()
        self.pm = ProcessMonitor(reactor=self.reactor)
        self.pm.minRestartDelay = 2
        self.pm.maxRestartDelay = 10
        self.pm.threshold = 10

    def test_reprLooksGood(self):
        """
        Repr includes all details
        """
        self.pm.addProcess("foo", ["arg1", "arg2"], uid=1, gid=2, env={})
        representation = repr(self.pm)
        self.assertIn("foo", representation)
        self.assertIn("1", representation)
        self.assertIn("2", representation)

    def test_simpleReprLooksGood(self):
        """
        Repr does not include unneeded details.

        Values of attributes that just mean "inherit from launching
        process" do not appear in the repr of a process.
        """
        self.pm.addProcess("foo", ["arg1", "arg2"], env={})
        representation = repr(self.pm)
        self.assertNotIn("(", representation)
        self.assertNotIn(")", representation)

    def test_getStateIncludesProcesses(self):
        """
        The list of monitored processes must be included in the pickle state.
        """
        self.pm.addProcess("foo", ["arg1", "arg2"], uid=1, gid=2, env={})
        self.assertEqual(
            self.pm.__getstate__()["processes"], {"foo": (["arg1", "arg2"], 1, 2, {})}
        )

    def test_getStateExcludesReactor(self):
        """
        The private L{ProcessMonitor._reactor} instance variable should not be
        included in the pickle state.
        """
        self.assertNotIn("_reactor", self.pm.__getstate__())

    def test_addProcess(self):
        """
        L{ProcessMonitor.addProcess} only starts the named program if
        L{ProcessMonitor.startService} has been called.
        """
        self.pm.addProcess("foo", ["arg1", "arg2"], uid=1, gid=2, env={})
        self.assertEqual(self.pm.protocols, {})
        self.assertEqual(self.pm.processes, {"foo": (["arg1", "arg2"], 1, 2, {})})
        self.pm.startService()
        self.reactor.advance(0)
        self.assertEqual(list(self.pm.protocols.keys()), ["foo"])

    def test_addProcessDuplicateKeyError(self):
        """
        L{ProcessMonitor.addProcess} raises a C{KeyError} if a process with the
        given name already exists.
        """
        self.pm.addProcess("foo", ["arg1", "arg2"], uid=1, gid=2, env={})
        self.assertRaises(
            KeyError, self.pm.addProcess, "foo", ["arg1", "arg2"], uid=1, gid=2, env={}
        )

    def test_addProcessEnv(self):
        """
        L{ProcessMonitor.addProcess} takes an C{env} parameter that is passed to
        L{IReactorProcess.spawnProcess}.
        """
        fakeEnv = {"KEY": "value"}
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"], uid=1, gid=2, env=fakeEnv)
        self.reactor.advance(0)
        self.assertEqual(self.reactor.spawnedProcesses[0]._environment, fakeEnv)

    def test_addProcessCwd(self):
        """
        L{ProcessMonitor.addProcess} takes an C{cwd} parameter that is passed
        to L{IReactorProcess.spawnProcess}.
        """
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"], cwd="/mnt/lala")
        self.reactor.advance(0)
        self.assertEqual(self.reactor.spawnedProcesses[0]._path, "/mnt/lala")

    def test_removeProcess(self):
        """
        L{ProcessMonitor.removeProcess} removes the process from the public
        processes list.
        """
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"])
        self.assertEqual(len(self.pm.processes), 1)
        self.pm.removeProcess("foo")
        self.assertEqual(len(self.pm.processes), 0)

    def test_removeProcessUnknownKeyError(self):
        """
        L{ProcessMonitor.removeProcess} raises a C{KeyError} if the given
        process name isn't recognised.
        """
        self.pm.startService()
        self.assertRaises(KeyError, self.pm.removeProcess, "foo")

    def test_startProcess(self):
        """
        When a process has been started, an instance of L{LoggingProtocol} will
        be added to the L{ProcessMonitor.protocols} dict and the start time of
        the process will be recorded in the L{ProcessMonitor.timeStarted}
        dictionary.
        """
        self.pm.addProcess("foo", ["foo"])
        self.pm.startProcess("foo")
        self.assertIsInstance(self.pm.protocols["foo"], LoggingProtocol)
        self.assertIn("foo", self.pm.timeStarted.keys())

    def test_startProcessAlreadyStarted(self):
        """
        L{ProcessMonitor.startProcess} silently returns if the named process is
        already started.
        """
        self.pm.addProcess("foo", ["foo"])
        self.pm.startProcess("foo")
        self.assertIsNone(self.pm.startProcess("foo"))

    def test_startProcessUnknownKeyError(self):
        """
        L{ProcessMonitor.startProcess} raises a C{KeyError} if the given
        process name isn't recognised.
        """
        self.assertRaises(KeyError, self.pm.startProcess, "foo")

    def test_stopProcessNaturalTermination(self):
        """
        L{ProcessMonitor.stopProcess} immediately sends a TERM signal to the
        named process.
        """
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"])
        self.assertIn("foo", self.pm.protocols)

        # Configure fake process to die 1 second after receiving term signal
        timeToDie = self.pm.protocols["foo"].transport._terminationDelay = 1

        # Advance the reactor to just before the short lived process threshold
        # and leave enough time for the process to die
        self.reactor.advance(self.pm.threshold)
        # Then signal the process to stop
        self.pm.stopProcess("foo")

        # Advance the reactor just enough to give the process time to die and
        # verify that the process restarts
        self.reactor.advance(timeToDie)

        # No further time is required to pass here but the reactor must
        # iterate due to implementation details.  See the comment in
        # test_stopProcessForcedKill.
        self.reactor.advance(0)

        # We expect it to be restarted immediately
        self.assertEqual(self.reactor.seconds(), self.pm.timeStarted["foo"])

    def test_stopProcessForcedKill(self):
        """
        L{ProcessMonitor.stopProcess} kills a process which fails to terminate
        naturally within L{ProcessMonitor.killTime} seconds.
        """
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"])
        self.assertIn("foo", self.pm.protocols)
        self.reactor.advance(self.pm.threshold)
        proc = self.pm.protocols["foo"].transport
        # Arrange for the fake process to live longer than the killTime
        proc._terminationDelay = self.pm.killTime + 1
        self.pm.stopProcess("foo")
        # If process doesn't die before the killTime, procmon should
        # terminate it
        self.reactor.advance(self.pm.killTime - 1)
        self.assertEqual(0.0, self.pm.timeStarted["foo"])

        self.reactor.advance(1)

        # We expect it to be immediately restarted.  While no actual time
        # should need to pass for this to happen, the reactor will need to
        # iterate a couple times because the implementation uses `callLater`
        # (twice!) to schedule the restart and no delayed call can run sooner
        # than the reactor iteration after it is scheduled.
        self.reactor.pump([0, 0])

        self.assertEqual(self.reactor.seconds(), self.pm.timeStarted["foo"])

    def test_stopProcessUnknownKeyError(self):
        """
        L{ProcessMonitor.stopProcess} raises a C{KeyError} if the given process
        name isn't recognised.
        """
        self.assertRaises(KeyError, self.pm.stopProcess, "foo")

    def test_stopProcessAlreadyStopped(self):
        """
        L{ProcessMonitor.stopProcess} silently returns if the named process
        is already stopped. eg Process has crashed and a restart has been
        rescheduled, but in the meantime, the service is stopped.
        """
        self.pm.addProcess("foo", ["foo"])
        self.assertIsNone(self.pm.stopProcess("foo"))

    def test_outputReceivedCompleteLine(self):
        """
        Getting a complete output line on stdout generates a log message.
        """
        events = []
        self.addCleanup(globalLogPublisher.removeObserver, events.append)
        globalLogPublisher.addObserver(events.append)
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # Advance the reactor to start the process
        self.reactor.advance(0)
        self.assertIn("foo", self.pm.protocols)
        # Long time passes
        self.reactor.advance(self.pm.threshold)
        # Process greets
        self.pm.protocols["foo"].outReceived(b"hello world!\n")
        self.assertEquals(len(events), 1)
        namespace = events[0]["log_namespace"]
        stream = events[0]["stream"]
        tag = events[0]["tag"]
        line = events[0]["line"]
        self.assertEquals(namespace, "twisted.runner.procmon.ProcessMonitor")
        self.assertEquals(stream, "stdout")
        self.assertEquals(tag, "foo")
        self.assertEquals(line, "hello world!")

    def test_ouputReceivedCompleteErrLine(self):
        """
        Getting a complete output line on stderr generates a log message.
        """
        events = []
        self.addCleanup(globalLogPublisher.removeObserver, events.append)
        globalLogPublisher.addObserver(events.append)
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # Advance the reactor to start the process
        self.reactor.advance(0)
        self.assertIn("foo", self.pm.protocols)
        # Long time passes
        self.reactor.advance(self.pm.threshold)
        # Process greets
        self.pm.protocols["foo"].errReceived(b"hello world!\n")
        self.assertEquals(len(events), 1)
        namespace = events[0]["log_namespace"]
        stream = events[0]["stream"]
        tag = events[0]["tag"]
        line = events[0]["line"]
        self.assertEquals(namespace, "twisted.runner.procmon.ProcessMonitor")
        self.assertEquals(stream, "stderr")
        self.assertEquals(tag, "foo")
        self.assertEquals(line, "hello world!")

    def test_outputReceivedCompleteLineInvalidUTF8(self):
        """
        Getting invalid UTF-8 results in the repr of the raw message
        """
        events = []
        self.addCleanup(globalLogPublisher.removeObserver, events.append)
        globalLogPublisher.addObserver(events.append)
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # Advance the reactor to start the process
        self.reactor.advance(0)
        self.assertIn("foo", self.pm.protocols)
        # Long time passes
        self.reactor.advance(self.pm.threshold)
        # Process greets
        self.pm.protocols["foo"].outReceived(b"\xffhello world!\n")
        self.assertEquals(len(events), 1)
        message = events[0]
        namespace = message["log_namespace"]
        stream = message["stream"]
        tag = message["tag"]
        output = message["line"]
        self.assertEquals(namespace, "twisted.runner.procmon.ProcessMonitor")
        self.assertEquals(stream, "stdout")
        self.assertEquals(tag, "foo")
        self.assertEquals(output, repr(b"\xffhello world!"))

    def test_outputReceivedPartialLine(self):
        """
        Getting partial line results in no events until process end
        """
        events = []
        self.addCleanup(globalLogPublisher.removeObserver, events.append)
        globalLogPublisher.addObserver(events.append)
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # Advance the reactor to start the process
        self.reactor.advance(0)
        self.assertIn("foo", self.pm.protocols)
        # Long time passes
        self.reactor.advance(self.pm.threshold)
        # Process greets
        self.pm.protocols["foo"].outReceived(b"hello world!")
        self.assertEquals(len(events), 0)
        self.pm.protocols["foo"].processEnded(Failure(ProcessDone(0)))
        self.assertEquals(len(events), 1)
        namespace = events[0]["log_namespace"]
        stream = events[0]["stream"]
        tag = events[0]["tag"]
        line = events[0]["line"]
        self.assertEquals(namespace, "twisted.runner.procmon.ProcessMonitor")
        self.assertEquals(stream, "stdout")
        self.assertEquals(tag, "foo")
        self.assertEquals(line, "hello world!")

    def test_connectionLostLongLivedProcess(self):
        """
        L{ProcessMonitor.connectionLost} should immediately restart a process
        if it has been running longer than L{ProcessMonitor.threshold} seconds.
        """
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # advance the reactor to start the process
        self.reactor.advance(0)
        self.assertIn("foo", self.pm.protocols)
        # Long time passes
        self.reactor.advance(self.pm.threshold)
        # Process dies after threshold
        self.pm.protocols["foo"].processEnded(Failure(ProcessDone(0)))
        self.assertNotIn("foo", self.pm.protocols)
        # Process should be restarted immediately
        self.reactor.advance(0)
        self.assertIn("foo", self.pm.protocols)

    def test_connectionLostMurderCancel(self):
        """
        L{ProcessMonitor.connectionLost} cancels a scheduled process killer and
        deletes the DelayedCall from the L{ProcessMonitor.murder} list.
        """
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # Advance 1s to start the process then ask ProcMon to stop it
        self.reactor.advance(1)
        self.pm.stopProcess("foo")
        # A process killer has been scheduled, delayedCall is active
        self.assertIn("foo", self.pm.murder)
        delayedCall = self.pm.murder["foo"]
        self.assertTrue(delayedCall.active())
        # Advance to the point at which the dummy process exits
        self.reactor.advance(self.pm.protocols["foo"].transport._terminationDelay)
        # Now the delayedCall has been cancelled and deleted
        self.assertFalse(delayedCall.active())
        self.assertNotIn("foo", self.pm.murder)

    def test_connectionLostProtocolDeletion(self):
        """
        L{ProcessMonitor.connectionLost} removes the corresponding
        ProcessProtocol instance from the L{ProcessMonitor.protocols} list.
        """
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"])
        self.assertIn("foo", self.pm.protocols)
        self.pm.protocols["foo"].transport.signalProcess("KILL")
        self.reactor.advance(self.pm.protocols["foo"].transport._terminationDelay)
        self.assertNotIn("foo", self.pm.protocols)

    def test_connectionLostMinMaxRestartDelay(self):
        """
        L{ProcessMonitor.connectionLost} will wait at least minRestartDelay s
        and at most maxRestartDelay s
        """
        self.pm.minRestartDelay = 2
        self.pm.maxRestartDelay = 3

        self.pm.startService()
        self.pm.addProcess("foo", ["foo"])

        self.assertEqual(self.pm.delay["foo"], self.pm.minRestartDelay)
        self.reactor.advance(self.pm.threshold - 1)
        self.pm.protocols["foo"].processEnded(Failure(ProcessDone(0)))
        self.assertEqual(self.pm.delay["foo"], self.pm.maxRestartDelay)

    def test_connectionLostBackoffDelayDoubles(self):
        """
        L{ProcessMonitor.connectionLost} doubles the restart delay each time
        the process dies too quickly.
        """
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"])
        self.reactor.advance(self.pm.threshold - 1)  # 9s
        self.assertIn("foo", self.pm.protocols)
        self.assertEqual(self.pm.delay["foo"], self.pm.minRestartDelay)
        # process dies within the threshold and should not restart immediately
        self.pm.protocols["foo"].processEnded(Failure(ProcessDone(0)))
        self.assertEqual(self.pm.delay["foo"], self.pm.minRestartDelay * 2)

    def test_startService(self):
        """
        L{ProcessMonitor.startService} starts all monitored processes.
        """
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # advance the reactor to start the process
        self.reactor.advance(0)
        self.assertIn("foo", self.pm.protocols)

    def test_stopService(self):
        """
        L{ProcessMonitor.stopService} should stop all monitored processes.
        """
        self.pm.addProcess("foo", ["foo"])
        self.pm.addProcess("bar", ["bar"])
        # Schedule the process to start
        self.pm.startService()
        # advance the reactor to start the processes
        self.reactor.advance(self.pm.threshold)
        self.assertIn("foo", self.pm.protocols)
        self.assertIn("bar", self.pm.protocols)

        self.reactor.advance(1)

        self.pm.stopService()
        # Advance to beyond the killTime - all monitored processes
        # should have exited
        self.reactor.advance(self.pm.killTime + 1)
        # The processes shouldn't be restarted
        self.assertEqual({}, self.pm.protocols)

    def test_restartAllRestartsOneProcess(self):
        """
        L{ProcessMonitor.restartAll} succeeds when there is one process.
        """
        self.pm.addProcess("foo", ["foo"])
        self.pm.startService()
        self.reactor.advance(1)
        self.pm.restartAll()
        # Just enough time for the process to die,
        # not enough time to start a new one.
        self.reactor.advance(1)
        processes = list(self.reactor.spawnedProcesses)
        myProcess = processes.pop()
        self.assertEquals(processes, [])
        self.assertIsNone(myProcess.pid)

    def test_stopServiceCancelRestarts(self):
        """
        L{ProcessMonitor.stopService} should cancel any scheduled process
        restarts.
        """
        self.pm.addProcess("foo", ["foo"])
        # Schedule the process to start
        self.pm.startService()
        # advance the reactor to start the processes
        self.reactor.advance(self.pm.threshold)
        self.assertIn("foo", self.pm.protocols)

        self.reactor.advance(1)
        # Kill the process early
        self.pm.protocols["foo"].processEnded(Failure(ProcessDone(0)))
        self.assertTrue(self.pm.restart["foo"].active())
        self.pm.stopService()
        # Scheduled restart should have been cancelled
        self.assertFalse(self.pm.restart["foo"].active())

    def test_stopServiceCleanupScheduledRestarts(self):
        """
        L{ProcessMonitor.stopService} should cancel all scheduled process
        restarts.
        """
        self.pm.threshold = 5
        self.pm.minRestartDelay = 5
        # Start service and add a process (started immediately)
        self.pm.startService()
        self.pm.addProcess("foo", ["foo"])
        # Stop the process after 1s
        self.reactor.advance(1)
        self.pm.stopProcess("foo")
        # Wait 1s for it to exit it will be scheduled to restart 5s later
        self.reactor.advance(1)
        # Meanwhile stop the service
        self.pm.stopService()
        # Advance to beyond the process restart time
        self.reactor.advance(6)
        # The process shouldn't have restarted because stopService has cancelled
        # all pending process restarts.
        self.assertEqual(self.pm.protocols, {})


class DeprecationTests(unittest.SynchronousTestCase):

    """
    Tests that check functionality that should be deprecated is deprecated.
    """

    def setUp(self):
        """
        Create reactor and process monitor.
        """
        self.reactor = DummyProcessReactor()
        self.pm = ProcessMonitor(reactor=self.reactor)

    def test_toTuple(self):
        """
        _Process.toTuple is deprecated.

        When getting the deprecated processes property, the actual
        data (kept in the class _Process) is converted to a tuple --
        which produces a DeprecationWarning per process so converted.
        """
        self.pm.addProcess("foo", ["foo"])
        myprocesses = self.pm.processes
        self.assertEquals(len(myprocesses), 1)
        warnings = self.flushWarnings()
        foundToTuple = False
        for warning in warnings:
            self.assertIs(warning["category"], DeprecationWarning)
            if "toTuple" in warning["message"]:
                foundToTuple = True
        self.assertTrue(foundToTuple, f"no tuple deprecation found:{repr(warnings)}")

    def test_processes(self):
        """
        Accessing L{ProcessMonitor.processes} results in deprecation warning

        Even when there are no processes, and thus no process is converted
        to a tuple, accessing the L{ProcessMonitor.processes} property
        should generate its own DeprecationWarning.
        """
        myProcesses = self.pm.processes
        self.assertEquals(myProcesses, {})
        warnings = self.flushWarnings()
        first = warnings.pop(0)
        self.assertIs(first["category"], DeprecationWarning)
        self.assertEquals(warnings, [])

    def test_getstate(self):
        """
        Pickling an L{ProcessMonitor} results in deprecation warnings
        """
        pickle.dumps(self.pm)
        warnings = self.flushWarnings()
        for warning in warnings:
            self.assertIs(warning["category"], DeprecationWarning)
