# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.trial._dist.disttrial}.
"""

import os
import sys
from functools import partial
from io import StringIO
from os.path import sep
from typing import Callable, List, Set
from unittest import TestCase as PyUnitTestCase

from zope.interface import implementer, verify

from attrs import Factory, assoc, define, field
from hamcrest import (
    assert_that,
    contains,
    ends_with,
    equal_to,
    has_length,
    none,
    starts_with,
)
from hamcrest.core.core.allof import AllOf
from hypothesis import given
from hypothesis.strategies import booleans, sampled_from

from twisted.internet import interfaces
from twisted.internet.base import ReactorBase
from twisted.internet.defer import Deferred, succeed
from twisted.internet.error import ProcessDone
from twisted.internet.protocol import ProcessProtocol, Protocol
from twisted.internet.test.modulehelpers import AlternateReactor
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.python.lockfile import FilesystemLock
from twisted.test.proto_helpers import MemoryReactorClock
from twisted.trial._dist import _WORKER_AMP_STDIN
from twisted.trial._dist.distreporter import DistReporter
from twisted.trial._dist.disttrial import DistTrialRunner, WorkerPool, WorkerPoolConfig
from twisted.trial._dist.functional import (
    countingCalls,
    discardResult,
    fromOptional,
    iterateWhile,
    sequence,
)
from twisted.trial._dist.worker import LocalWorker, RunResult, Worker, WorkerAction
from twisted.trial.reporter import (
    Reporter,
    TestResult,
    TreeReporter,
    UncleanWarningsReporterWrapper,
)
from twisted.trial.runner import ErrorHolder, TrialSuite
from twisted.trial.unittest import SynchronousTestCase, TestCase
from ...test import erroneous, sample
from .matchers import matches_result


@define
class FakeTransport:
    """
    A simple fake process transport.
    """

    _closed: Set[int] = field(default=Factory(set))

    def writeToChild(self, fd, data):
        """
        Ignore write calls.
        """

    def closeChildFD(self, fd):
        """
        Mark one of the child descriptors as closed.
        """
        self._closed.add(fd)


@implementer(interfaces.IReactorProcess)
class CountingReactor(MemoryReactorClock):
    """
    A fake reactor that counts the calls to L{IReactorCore.run},
    L{IReactorCore.stop}, and L{IReactorProcess.spawnProcess}.
    """

    spawnCount = 0
    stopCount = 0
    runCount = 0

    def __init__(self, workers):
        MemoryReactorClock.__init__(self)
        self._workers = workers

    def spawnProcess(
        self,
        workerProto,
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
        See L{IReactorProcess.spawnProcess}.

        @param workerProto: See L{IReactorProcess.spawnProcess}.
        @param args: See L{IReactorProcess.spawnProcess}.
        @param kwargs: See L{IReactorProcess.spawnProcess}.
        """
        self._workers.append(workerProto)
        workerProto.makeConnection(FakeTransport())
        self.spawnCount += 1

    def stop(self):
        """
        See L{IReactorCore.stop}.
        """
        MemoryReactorClock.stop(self)
        self.stopCount += 1

    def run(self):
        """
        See L{IReactorCore.run}.
        """
        self.runCount += 1

        # The same as IReactorCore.run, except no stop.
        self.running = True
        self.hasRun = True

        for f, args, kwargs in self.whenRunningHooks:
            f(*args, **kwargs)


class CountingReactorTests(SynchronousTestCase):
    """
    Tests for L{CountingReactor}.
    """

    def setUp(self):
        self.workers = []
        self.reactor = CountingReactor(self.workers)

    def test_providesIReactorProcess(self):
        """
        L{CountingReactor} instances provide L{IReactorProcess}.
        """
        verify.verifyObject(interfaces.IReactorProcess, self.reactor)

    def test_spawnProcess(self):
        """
        The process protocol for a spawned process is connected to a
        transport and appended onto the provided C{workers} list, and
        the reactor's C{spawnCount} increased.
        """
        self.assertFalse(self.reactor.spawnCount)

        proto = Protocol()
        for count in [1, 2]:
            self.reactor.spawnProcess(proto, sys.executable, args=[sys.executable])
            self.assertTrue(proto.transport)
            self.assertEqual(self.workers, [proto] * count)
            self.assertEqual(self.reactor.spawnCount, count)

    def test_stop(self):
        """
        Stopping the reactor increments its C{stopCount}
        """
        self.assertFalse(self.reactor.stopCount)
        for count in [1, 2]:
            self.reactor.stop()
            self.assertEqual(self.reactor.stopCount, count)

    def test_run(self):
        """
        Running the reactor increments its C{runCount}, does not imply
        C{stop}, and calls L{IReactorCore.callWhenRunning} hooks.
        """
        self.assertFalse(self.reactor.runCount)

        whenRunningCalls = []
        self.reactor.callWhenRunning(whenRunningCalls.append, None)

        for count in [1, 2]:
            self.reactor.run()
            self.assertEqual(self.reactor.runCount, count)
            self.assertEqual(self.reactor.stopCount, 0)
            self.assertEqual(len(whenRunningCalls), count)


class WorkerPoolTests(TestCase):
    """
    Tests for L{WorkerPool}.
    """

    def setUp(self):
        self.parent = FilePath(self.mktemp())
        self.workingDirectory = self.parent.child("_trial_temp")
        self.config = WorkerPoolConfig(
            numWorkers=4,
            workingDirectory=self.workingDirectory,
            workerArguments=[],
            logFile="out.log",
        )
        self.pool = WorkerPool(self.config)

    def test_createLocalWorkers(self):
        """
        C{_createLocalWorkers} iterates the list of protocols and create one
        L{LocalWorker} for each.
        """
        protocols = [object() for x in range(4)]
        workers = self.pool._createLocalWorkers(protocols, FilePath("path"), StringIO())
        for s in workers:
            self.assertIsInstance(s, LocalWorker)
        self.assertEqual(4, len(workers))

    def test_launchWorkerProcesses(self):
        """
        Given a C{spawnProcess} function, C{_launchWorkerProcess} launches a
        python process with an existing path as its argument.
        """
        protocols = [ProcessProtocol() for i in range(4)]
        arguments = []
        environment = {}

        def fakeSpawnProcess(
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
            arguments.append(executable)
            arguments.extend(args)
            environment.update(env)

        self.pool._launchWorkerProcesses(fakeSpawnProcess, protocols, ["foo"])
        self.assertEqual(arguments[0], arguments[1])
        self.assertTrue(os.path.exists(arguments[2]))
        self.assertEqual("foo", arguments[3])
        # The child process runs with PYTHONPATH set to exactly the parent's
        # import search path so that the child has a good chance of finding
        # the same source files the parent would have found.
        self.assertEqual(os.pathsep.join(sys.path), environment["PYTHONPATH"])

    def test_run(self):
        """
        C{run} dispatches the given action to each of its workers exactly once.
        """
        # Make sure the parent of the working directory exists so
        # manage a lock in it.
        self.parent.makedirs()

        workers = []
        starting = self.pool.start(CountingReactor([]))
        started = self.successResultOf(starting)
        running = started.run(lambda w: succeed(workers.append(w)))
        self.successResultOf(running)
        assert_that(workers, has_length(self.config.numWorkers))

    def test_runUsedDirectory(self):
        """
        L{WorkerPool.start} checks if the test directory is already locked, and if
        it is generates a name based on it.
        """
        # Make sure the parent of the working directory exists so we can
        # manage a lock in it.
        self.parent.makedirs()

        # Lock the directory the runner will expect to use.
        lock = FilesystemLock(self.workingDirectory.path + ".lock")
        self.assertTrue(lock.lock())
        self.addCleanup(lock.unlock)

        # Start up the pool
        fakeReactor = CountingReactor([])
        started = self.successResultOf(self.pool.start(fakeReactor))

        # Verify it took a nearby directory instead.
        self.assertEqual(
            started.workingDirectory,
            self.workingDirectory.sibling("_trial_temp-1"),
        )

    def test_join(self):
        """
        L{StartedWorkerPool.join} causes all of the workers to exit, closes the
        log file, and unlocks the test directory.
        """
        self.parent.makedirs()

        reactor = CountingReactor([])
        started = self.successResultOf(self.pool.start(reactor))
        joining = Deferred.fromCoroutine(started.join())
        self.assertNoResult(joining)
        for w in reactor._workers:
            assert_that(w.transport._closed, contains(_WORKER_AMP_STDIN))
            for fd in w.transport._closed:
                w.childConnectionLost(fd)
            for f in [w.processExited, w.processEnded]:
                f(Failure(ProcessDone(0)))
        assert_that(self.successResultOf(joining), none())
        assert_that(started.testLog.closed, equal_to(True))
        assert_that(started.testDirLock.locked, equal_to(False))

    @given(
        booleans(),
        sampled_from(
            [
                "out.log",
                f"subdir{sep}out.log",
            ]
        ),
    )
    def test_logFile(self, absolute: bool, logFile: str) -> None:
        """
        L{WorkerPool.start} creates a L{StartedWorkerPool} configured with a
        log file based on the L{WorkerPoolConfig.logFile}.
        """
        if absolute:
            logFile = self.parent.path + sep + logFile

        config = assoc(self.config, logFile=logFile)

        if absolute:
            matches = equal_to(logFile)
        else:
            matches = AllOf(
                # This might have a suffix if the configured workingDirectory
                # was found to be in-use already so we don't add a sep suffix.
                starts_with(config.workingDirectory.path),
                # This should be exactly the suffix so we add a sep prefix.
                ends_with(sep + logFile),
            )

        pool = WorkerPool(config)
        started = self.successResultOf(pool.start(CountingReactor([])))
        assert_that(started.testLog.name, matches)


class DistTrialRunnerTests(TestCase):
    """
    Tests for L{DistTrialRunner}.
    """

    suite = TrialSuite([sample.FooTest("test_foo")])

    def getRunner(self, **overrides):
        """
        Create a runner for testing.
        """
        args = dict(
            reporterFactory=TreeReporter,
            workingDirectory=self.mktemp(),
            stream=StringIO(),
            maxWorkers=4,
            workerArguments=[],
            workerPoolFactory=partial(LocalWorkerPool, autostop=True),
            reactor=CountingReactor([]),
        )
        args.update(overrides)
        return DistTrialRunner(**args)

    def test_writeResults(self):
        """
        L{DistTrialRunner.writeResults} writes to the stream specified in the
        init.
        """
        stringIO = StringIO()
        result = DistReporter(Reporter(stringIO))
        runner = self.getRunner()
        runner.writeResults(result)
        self.assertTrue(stringIO.tell() > 0)

    def test_minimalWorker(self):
        """
        L{DistTrialRunner.runAsync} doesn't try to start more workers than the
        number of tests.
        """
        pool = None

        def recordingFactory(*a, **kw):
            nonlocal pool
            pool = LocalWorkerPool(*a, autostop=True, **kw)
            return pool

        maxWorkers = 7
        numTests = 3

        runner = self.getRunner(
            maxWorkers=maxWorkers, workerPoolFactory=recordingFactory
        )
        suite = TrialSuite([TestCase() for n in range(numTests)])
        self.successResultOf(runner.runAsync(suite))
        assert_that(pool._started[0].workers, has_length(numTests))

    def test_runUncleanWarnings(self) -> None:
        """
        Running with the C{unclean-warnings} option makes L{DistTrialRunner} uses
        the L{UncleanWarningsReporterWrapper}.
        """
        runner = self.getRunner(uncleanWarnings=True)
        d = runner.runAsync(self.suite)
        result = self.successResultOf(d)
        self.assertIsInstance(result, DistReporter)
        self.assertIsInstance(result.original, UncleanWarningsReporterWrapper)

    def test_runWithoutTest(self):
        """
        L{DistTrialRunner} can run an empty test suite.
        """
        stream = StringIO()
        runner = self.getRunner(stream=stream)
        result = self.successResultOf(runner.runAsync(TrialSuite()))
        self.assertIsInstance(result, DistReporter)
        output = stream.getvalue()
        self.assertIn("Running 0 test", output)
        self.assertIn("PASSED", output)

    def test_runWithoutTestButWithAnError(self):
        """
        Even if there is no test, the suite can contain an error (most likely,
        an import error): this should make the run fail, and the error should
        be printed.
        """
        err = ErrorHolder("an error", Failure(RuntimeError("foo bar")))
        stream = StringIO()
        runner = self.getRunner(stream=stream)

        result = self.successResultOf(runner.runAsync(err))
        self.assertIsInstance(result, DistReporter)
        output = stream.getvalue()
        self.assertIn("Running 0 test", output)
        self.assertIn("foo bar", output)
        self.assertIn("an error", output)
        self.assertIn("errors=1", output)
        self.assertIn("FAILED", output)

    def test_runUnexpectedError(self) -> None:
        """
        If for some reasons we can't connect to the worker process, the error is
        recorded in the result object.
        """
        runner = self.getRunner(workerPoolFactory=BrokenWorkerPool)
        result = self.successResultOf(runner.runAsync(self.suite))
        errors = result.original.errors
        assert_that(errors, has_length(1))
        assert_that(errors[0][1].type, equal_to(WorkerPoolBroken))

    def test_runUnexpectedWorkerError(self) -> None:
        """
        If for some reason the worker process cannot run a test, the error is
        recorded in the result object.
        """
        runner = self.getRunner(
            workerPoolFactory=partial(
                LocalWorkerPool, workerFactory=_BrokenLocalWorker, autostop=True
            )
        )
        result = self.successResultOf(runner.runAsync(self.suite))
        errors = result.original.errors
        assert_that(errors, has_length(1))
        assert_that(errors[0][1].type, equal_to(WorkerBroken))

    def test_runWaitForProcessesDeferreds(self) -> None:
        """
        L{DistTrialRunner} waits for the worker pool to stop.
        """
        pool = None

        def recordingFactory(*a, **kw):
            nonlocal pool
            pool = LocalWorkerPool(*a, autostop=False, **kw)
            return pool

        runner = self.getRunner(
            workerPoolFactory=recordingFactory,
        )
        d = Deferred.fromCoroutine(runner.runAsync(self.suite))
        if pool is None:
            self.fail("worker pool was never created")

        assert pool is not None
        stopped = pool._started[0]._stopped
        self.assertNoResult(d)
        stopped.callback(None)
        result = self.successResultOf(d)
        self.assertIsInstance(result, DistReporter)

    def test_exitFirst(self):
        """
        L{DistTrialRunner} can run in C{exitFirst} mode where it will run until a
        test fails and then abandon the rest of the suite.
        """
        stream = StringIO()
        # Construct a suite with a failing test in the middle.
        suite = TrialSuite(
            [
                sample.FooTest("test_foo"),
                erroneous.TestRegularFail("test_fail"),
                sample.FooTest("test_bar"),
            ]
        )
        runner = self.getRunner(stream=stream, exitFirst=True, maxWorkers=2)
        d = runner.runAsync(suite)
        result = self.successResultOf(d)
        assert_that(
            result.original,
            matches_result(
                successes=1,
                failures=has_length(1),
            ),
        )

    def test_runUntilFailure(self):
        """
        L{DistTrialRunner} can run in C{untilFailure} mode where it will run
        the given tests until they fail.
        """
        stream = StringIO()
        case = erroneous.EventuallyFailingTestCase("test_it")
        runner = self.getRunner(stream=stream)
        d = runner.runAsync(case, untilFailure=True)
        result = self.successResultOf(d)
        # The case is hard-coded to fail on its 5th run.
        self.assertEqual(5, case.n)
        self.assertFalse(result.wasSuccessful())
        output = stream.getvalue()

        # It passes each time except the last.
        self.assertEqual(
            output.count("PASSED"),
            case.n - 1,
            "expected to see PASSED in output",
        )
        # It also fails at the end.
        self.assertIn("FAIL", output)

        # It also reports its progress.
        for i in range(1, 6):
            self.assertIn(f"Test Pass {i}", output)

        # It also reports the number of tests run as part of each iteration.
        self.assertEqual(
            output.count("Ran 1 tests in"),
            case.n,
            "expected to see per-iteration test count in output",
        )

    def test_run(self) -> None:
        """
        L{DistTrialRunner.run} returns a L{DistReporter} containing the result of
        the test suite run.
        """
        runner = self.getRunner()
        result = runner.run(self.suite)
        assert_that(result.wasSuccessful(), equal_to(True))
        assert_that(result.successes, equal_to(1))

    def test_installedReactor(self) -> None:
        """
        L{DistTrialRunner.run} uses the installed reactor L{DistTrialRunner} was
        constructed without a reactor.
        """
        reactor = CountingReactor([])
        with AlternateReactor(reactor):
            runner = self.getRunner(reactor=None)
        result = runner.run(self.suite)
        assert_that(result.errors, equal_to([]))
        assert_that(result.failures, equal_to([]))
        assert_that(result.wasSuccessful(), equal_to(True))
        assert_that(result.successes, equal_to(1))
        assert_that(reactor.runCount, equal_to(1))
        assert_that(reactor.stopCount, equal_to(1))

    def test_wrongInstalledReactor(self) -> None:
        """
        L{DistTrialRunner} raises L{TypeError} if the installed reactor provides
        neither L{IReactorCore} nor L{IReactorProcess} and no other reactor is
        given.
        """

        class Core(ReactorBase):
            def installWaker(self):
                pass

        @implementer(interfaces.IReactorProcess)
        class Process:
            def spawnProcess(
                self,
                processProtocol,
                executable,
                args,
                env,
                path,
                uid,
                gid,
                usePTY,
                childFDs,
            ):
                pass

        class Neither:
            pass

        # It provides neither
        with AlternateReactor(Neither()):
            with self.assertRaises(TypeError):
                self.getRunner(reactor=None)

        # It is missing IReactorProcess
        with AlternateReactor(Core()):
            with self.assertRaises(TypeError):
                self.getRunner(reactor=None)

        # It is missing IReactorCore
        with AlternateReactor(Process()):
            with self.assertRaises(TypeError):
                self.getRunner(reactor=None)

    def test_runFailure(self):
        """
        If there is an unexpected exception running the test suite then it is
        re-raised by L{DistTrialRunner.run}.
        """
        # Give it a broken worker pool factory.  There's no exception handling
        # for such an error in the implementation..
        class BrokenFactory(Exception):
            pass

        def brokenFactory(*args, **kwargs):
            raise BrokenFactory()

        runner = self.getRunner(workerPoolFactory=brokenFactory)
        with self.assertRaises(BrokenFactory):
            runner.run(self.suite)


class FunctionalTests(TestCase):
    """
    Tests for the functional helpers that need it.
    """

    def test_fromOptional(self) -> None:
        """
        ``fromOptional`` accepts a default value and an ``Optional`` value of the
        same type and returns the default value if the optional value is
        ``None`` or the optional value otherwise.
        """
        assert_that(fromOptional(1, None), equal_to(1))
        assert_that(fromOptional(2, 2), equal_to(2))

    def test_discardResult(self) -> None:
        """
        ``discardResult`` accepts an awaitable and returns a ``Deferred`` that
        fires with ``None`` after the awaitable completes.
        """
        a: Deferred[str] = Deferred()
        d = discardResult(a)
        self.assertNoResult(d)
        a.callback("result")
        assert_that(self.successResultOf(d), none())

    def test_sequence(self):
        """
        ``sequence`` accepts two awaitables and returns an awaitable that waits
        for the first one to complete and then completes with the result of
        the second one.
        """
        a: Deferred[str] = Deferred()
        b: Deferred[int] = Deferred()
        c = Deferred.fromCoroutine(sequence(a, b))
        b.callback(42)
        self.assertNoResult(c)
        a.callback("hello")
        assert_that(self.successResultOf(c), equal_to(42))

    def test_iterateWhile(self):
        """
        ``iterateWhile`` executes the actions from its factory until the predicate
        does not match an action result.
        """
        actions: List[Deferred[int]] = [Deferred(), Deferred(), Deferred()]

        def predicate(value):
            return value != 42

        d: Deferred[int] = Deferred.fromCoroutine(
            iterateWhile(predicate, list(actions).pop)
        )
        # Let the action it is waiting on complete
        actions.pop().callback(7)

        # It does not match the predicate so it is not done yet.
        self.assertNoResult(d)

        # Let the action it is waiting on now complete - with the result it
        # wants.
        actions.pop().callback(42)

        assert_that(self.successResultOf(d), equal_to(42))

    def test_countingCalls(self):
        """
        ``countingCalls`` decorates a function so that it is called with an
        increasing counter and passes the return value through.
        """

        @countingCalls
        def target(n: int) -> int:
            return n + 1

        for expected in range(1, 10):
            assert_that(target(), equal_to(expected))


class WorkerPoolBroken(Exception):
    """
    An exception for ``StartedWorkerPoolBroken`` to fail with to allow tests
    to exercise exception code paths.
    """


class StartedWorkerPoolBroken:
    """
    A broken, started worker pool.  Its workers cannot run actions.  They
    always raise an exception.
    """

    async def run(self, workerAction: WorkerAction) -> None:
        raise WorkerPoolBroken()

    async def join(self) -> None:
        return None


@define
class BrokenWorkerPool:
    """
    A worker pool that has workers with a broken ``run`` method.
    """

    _config: WorkerPoolConfig

    async def start(
        self, reactor: interfaces.IReactorProcess
    ) -> StartedWorkerPoolBroken:
        return StartedWorkerPoolBroken()


class _LocalWorker:
    """
    A L{Worker} that runs tests in this process in the usual way.

    This is a test double for L{LocalWorkerAMP} which allows testing worker
    pool logic without sending tests over an AMP connection to be run
    somewhere else..
    """

    async def run(self, case: PyUnitTestCase, result: TestResult) -> RunResult:
        """
        Directly run C{case} in the usual way.
        """
        TrialSuite([case]).run(result)
        return {"success": True}


class WorkerBroken(Exception):
    """
    A worker tried to run a test case but the worker is broken.
    """


class _BrokenLocalWorker:
    """
    A L{Worker} that always fails to run test cases.
    """

    async def run(self, case: PyUnitTestCase, result: TestResult) -> None:
        """
        Raise an exception instead of running C{case}.
        """
        raise WorkerBroken()


@define
class StartedLocalWorkerPool:
    """
    A started L{LocalWorkerPool}.
    """

    workingDirectory: FilePath
    workers: List[Worker]
    _stopped: Deferred

    async def run(self, workerAction: WorkerAction) -> None:
        """
        Run the action with each local worker.
        """
        for worker in self.workers:
            await workerAction(worker)

    async def join(self):
        await self._stopped


@define
class LocalWorkerPool:
    """
    Implement a worker pool that runs tests in-process instead of in child
    processes.
    """

    _config: WorkerPoolConfig
    _started: List[StartedLocalWorkerPool] = field(default=Factory(list))
    _autostop: bool = False
    _workerFactory: Callable[[], Worker] = _LocalWorker

    async def start(
        self, reactor: interfaces.IReactorProcess
    ) -> StartedLocalWorkerPool:
        workers = [self._workerFactory() for i in range(self._config.numWorkers)]
        started = StartedLocalWorkerPool(
            self._config.workingDirectory,
            workers,
            (succeed(None) if self._autostop else Deferred()),
        )
        self._started.append(started)
        return started
