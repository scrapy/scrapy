# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.threadpool}
"""


import gc
import pickle
import threading
import time
import weakref

from twisted._threads import Team, createMemoryWorker
from twisted.python import context, failure, threadable, threadpool
from twisted.trial import unittest


class Synchronization:
    failures = 0

    def __init__(self, N, waiting):
        self.N = N
        self.waiting = waiting
        self.lock = threading.Lock()
        self.runs = []

    def run(self):
        # This is the testy part: this is supposed to be invoked
        # serially from multiple threads.  If that is actually the
        # case, we will never fail to acquire this lock.  If it is
        # *not* the case, we might get here while someone else is
        # holding the lock.
        if self.lock.acquire(False):
            if not len(self.runs) % 5:
                # Constant selected based on empirical data to maximize the
                # chance of a quick failure if this code is broken.
                time.sleep(0.0002)
            self.lock.release()
        else:
            self.failures += 1

        # This is just the only way I can think of to wake up the test
        # method.  It doesn't actually have anything to do with the
        # test.
        self.lock.acquire()
        self.runs.append(None)
        if len(self.runs) == self.N:
            self.waiting.release()
        self.lock.release()

    synchronized = ["run"]


threadable.synchronize(Synchronization)


class ThreadPoolTests(unittest.SynchronousTestCase):
    """
    Test threadpools.
    """

    def getTimeout(self):
        """
        Return number of seconds to wait before giving up.
        """
        return 5  # Really should be order of magnitude less

    def _waitForLock(self, lock):
        items = range(1000000)
        for i in items:
            if lock.acquire(False):
                break
            time.sleep(1e-5)
        else:
            self.fail("A long time passed without succeeding")

    def test_attributes(self):
        """
        L{ThreadPool.min} and L{ThreadPool.max} are set to the values passed to
        L{ThreadPool.__init__}.
        """
        pool = threadpool.ThreadPool(12, 22)
        self.assertEqual(pool.min, 12)
        self.assertEqual(pool.max, 22)

    def test_start(self):
        """
        L{ThreadPool.start} creates the minimum number of threads specified.
        """
        pool = threadpool.ThreadPool(0, 5)
        pool.start()
        self.addCleanup(pool.stop)
        self.assertEqual(len(pool.threads), 0)

        pool = threadpool.ThreadPool(3, 10)
        self.assertEqual(len(pool.threads), 0)
        pool.start()
        self.addCleanup(pool.stop)
        self.assertEqual(len(pool.threads), 3)

    def test_adjustingWhenPoolStopped(self):
        """
        L{ThreadPool.adjustPoolsize} only modifies the pool size and does not
        start new workers while the pool is not running.
        """
        pool = threadpool.ThreadPool(0, 5)
        pool.start()
        pool.stop()
        pool.adjustPoolsize(2)
        self.assertEqual(len(pool.threads), 0)

    def test_threadCreationArguments(self):
        """
        Test that creating threads in the threadpool with application-level
        objects as arguments doesn't results in those objects never being
        freed, with the thread maintaining a reference to them as long as it
        exists.
        """
        tp = threadpool.ThreadPool(0, 1)
        tp.start()
        self.addCleanup(tp.stop)

        # Sanity check - no threads should have been started yet.
        self.assertEqual(tp.threads, [])

        # Here's our function
        def worker(arg):
            pass

        # weakref needs an object subclass
        class Dumb:
            pass

        # And here's the unique object
        unique = Dumb()

        workerRef = weakref.ref(worker)
        uniqueRef = weakref.ref(unique)

        # Put some work in
        tp.callInThread(worker, unique)

        # Add an event to wait completion
        event = threading.Event()
        tp.callInThread(event.set)
        event.wait(self.getTimeout())

        del worker
        del unique
        gc.collect()
        self.assertIsNone(uniqueRef())
        self.assertIsNone(workerRef())

    def test_threadCreationArgumentsCallInThreadWithCallback(self):
        """
        As C{test_threadCreationArguments} above, but for
        callInThreadWithCallback.
        """

        tp = threadpool.ThreadPool(0, 1)
        tp.start()
        self.addCleanup(tp.stop)

        # Sanity check - no threads should have been started yet.
        self.assertEqual(tp.threads, [])

        # this holds references obtained in onResult
        refdict = {}  # name -> ref value

        onResultWait = threading.Event()
        onResultDone = threading.Event()

        resultRef = []

        # result callback
        def onResult(success, result):
            # Spin the GC, which should now delete worker and unique if it's
            # not held on to by callInThreadWithCallback after it is complete
            gc.collect()
            onResultWait.wait(self.getTimeout())
            refdict["workerRef"] = workerRef()
            refdict["uniqueRef"] = uniqueRef()
            onResultDone.set()
            resultRef.append(weakref.ref(result))

        # Here's our function
        def worker(arg, test):
            return Dumb()

        # weakref needs an object subclass
        class Dumb:
            pass

        # And here's the unique object
        unique = Dumb()

        onResultRef = weakref.ref(onResult)
        workerRef = weakref.ref(worker)
        uniqueRef = weakref.ref(unique)

        # Put some work in
        tp.callInThreadWithCallback(onResult, worker, unique, test=unique)

        del worker
        del unique

        # let onResult collect the refs
        onResultWait.set()
        # wait for onResult
        onResultDone.wait(self.getTimeout())
        gc.collect()

        self.assertIsNone(uniqueRef())
        self.assertIsNone(workerRef())

        # XXX There's a race right here - has onResult in the worker thread
        # returned and the locals in _worker holding it and the result been
        # deleted yet?

        del onResult
        gc.collect()
        self.assertIsNone(onResultRef())
        self.assertIsNone(resultRef[0]())

        # The callback shouldn't have been able to resolve the references.
        self.assertEqual(list(refdict.values()), [None, None])

    def test_persistence(self):
        """
        Threadpools can be pickled and unpickled, which should preserve the
        number of threads and other parameters.
        """
        pool = threadpool.ThreadPool(7, 20)

        self.assertEqual(pool.min, 7)
        self.assertEqual(pool.max, 20)

        # check that unpickled threadpool has same number of threads
        copy = pickle.loads(pickle.dumps(pool))

        self.assertEqual(copy.min, 7)
        self.assertEqual(copy.max, 20)

    def _threadpoolTest(self, method):
        """
        Test synchronization of calls made with C{method}, which should be
        one of the mechanisms of the threadpool to execute work in threads.
        """
        # This is a schizophrenic test: it seems to be trying to test
        # both the callInThread()/dispatch() behavior of the ThreadPool as well
        # as the serialization behavior of threadable.synchronize().  It
        # would probably make more sense as two much simpler tests.
        N = 10

        tp = threadpool.ThreadPool()
        tp.start()
        self.addCleanup(tp.stop)

        waiting = threading.Lock()
        waiting.acquire()
        actor = Synchronization(N, waiting)

        for i in range(N):
            method(tp, actor)

        self._waitForLock(waiting)

        self.assertFalse(actor.failures, f"run() re-entered {actor.failures} times")

    def test_callInThread(self):
        """
        Call C{_threadpoolTest} with C{callInThread}.
        """
        return self._threadpoolTest(lambda tp, actor: tp.callInThread(actor.run))

    def test_callInThreadException(self):
        """
        L{ThreadPool.callInThread} logs exceptions raised by the callable it
        is passed.
        """

        class NewError(Exception):
            pass

        def raiseError():
            raise NewError()

        tp = threadpool.ThreadPool(0, 1)
        tp.callInThread(raiseError)
        tp.start()
        tp.stop()

        errors = self.flushLoggedErrors(NewError)
        self.assertEqual(len(errors), 1)

    def test_callInThreadWithCallback(self):
        """
        L{ThreadPool.callInThreadWithCallback} calls C{onResult} with a
        two-tuple of C{(True, result)} where C{result} is the value returned
        by the callable supplied.
        """
        waiter = threading.Lock()
        waiter.acquire()

        results = []

        def onResult(success, result):
            waiter.release()
            results.append(success)
            results.append(result)

        tp = threadpool.ThreadPool(0, 1)
        tp.callInThreadWithCallback(onResult, lambda: "test")
        tp.start()

        try:
            self._waitForLock(waiter)
        finally:
            tp.stop()

        self.assertTrue(results[0])
        self.assertEqual(results[1], "test")

    def test_callInThreadWithCallbackExceptionInCallback(self):
        """
        L{ThreadPool.callInThreadWithCallback} calls C{onResult} with a
        two-tuple of C{(False, failure)} where C{failure} represents the
        exception raised by the callable supplied.
        """

        class NewError(Exception):
            pass

        def raiseError():
            raise NewError()

        waiter = threading.Lock()
        waiter.acquire()

        results = []

        def onResult(success, result):
            waiter.release()
            results.append(success)
            results.append(result)

        tp = threadpool.ThreadPool(0, 1)
        tp.callInThreadWithCallback(onResult, raiseError)
        tp.start()

        try:
            self._waitForLock(waiter)
        finally:
            tp.stop()

        self.assertFalse(results[0])
        self.assertIsInstance(results[1], failure.Failure)
        self.assertTrue(issubclass(results[1].type, NewError))

    def test_callInThreadWithCallbackExceptionInOnResult(self):
        """
        L{ThreadPool.callInThreadWithCallback} logs the exception raised by
        C{onResult}.
        """

        class NewError(Exception):
            pass

        waiter = threading.Lock()
        waiter.acquire()

        results = []

        def onResult(success, result):
            results.append(success)
            results.append(result)
            raise NewError()

        tp = threadpool.ThreadPool(0, 1)
        tp.callInThreadWithCallback(onResult, lambda: None)
        tp.callInThread(waiter.release)
        tp.start()

        try:
            self._waitForLock(waiter)
        finally:
            tp.stop()

        errors = self.flushLoggedErrors(NewError)
        self.assertEqual(len(errors), 1)

        self.assertTrue(results[0])
        self.assertIsNone(results[1])

    def test_callbackThread(self):
        """
        L{ThreadPool.callInThreadWithCallback} calls the function it is
        given and the C{onResult} callback in the same thread.
        """
        threadIds = []

        event = threading.Event()

        def onResult(success, result):
            threadIds.append(threading.current_thread().ident)
            event.set()

        def func():
            threadIds.append(threading.current_thread().ident)

        tp = threadpool.ThreadPool(0, 1)
        tp.callInThreadWithCallback(onResult, func)
        tp.start()
        self.addCleanup(tp.stop)

        event.wait(self.getTimeout())
        self.assertEqual(len(threadIds), 2)
        self.assertEqual(threadIds[0], threadIds[1])

    def test_callbackContext(self):
        """
        The context L{ThreadPool.callInThreadWithCallback} is invoked in is
        shared by the context the callable and C{onResult} callback are
        invoked in.
        """
        myctx = context.theContextTracker.currentContext().contexts[-1]
        myctx["testing"] = "this must be present"

        contexts = []

        event = threading.Event()

        def onResult(success, result):
            ctx = context.theContextTracker.currentContext().contexts[-1]
            contexts.append(ctx)
            event.set()

        def func():
            ctx = context.theContextTracker.currentContext().contexts[-1]
            contexts.append(ctx)

        tp = threadpool.ThreadPool(0, 1)
        tp.callInThreadWithCallback(onResult, func)
        tp.start()
        self.addCleanup(tp.stop)

        event.wait(self.getTimeout())

        self.assertEqual(len(contexts), 2)
        self.assertEqual(myctx, contexts[0])
        self.assertEqual(myctx, contexts[1])

    def test_existingWork(self):
        """
        Work added to the threadpool before its start should be executed once
        the threadpool is started: this is ensured by trying to release a lock
        previously acquired.
        """
        waiter = threading.Lock()
        waiter.acquire()

        tp = threadpool.ThreadPool(0, 1)
        tp.callInThread(waiter.release)  # Before start()
        tp.start()

        try:
            self._waitForLock(waiter)
        finally:
            tp.stop()

    def test_workerStateTransition(self):
        """
        As the worker receives and completes work, it transitions between
        the working and waiting states.
        """
        pool = threadpool.ThreadPool(0, 1)
        pool.start()
        self.addCleanup(pool.stop)

        # Sanity check
        self.assertEqual(pool.workers, 0)
        self.assertEqual(len(pool.waiters), 0)
        self.assertEqual(len(pool.working), 0)

        # Fire up a worker and give it some 'work'
        threadWorking = threading.Event()
        threadFinish = threading.Event()

        def _thread():
            threadWorking.set()
            threadFinish.wait(10)

        pool.callInThread(_thread)
        threadWorking.wait(10)
        self.assertEqual(pool.workers, 1)
        self.assertEqual(len(pool.waiters), 0)
        self.assertEqual(len(pool.working), 1)

        # Finish work, and spin until state changes
        threadFinish.set()
        while not len(pool.waiters):
            time.sleep(0.0005)

        # Make sure state changed correctly
        self.assertEqual(len(pool.waiters), 1)
        self.assertEqual(len(pool.working), 0)


class RaceConditionTests(unittest.SynchronousTestCase):
    def setUp(self):
        self.threadpool = threadpool.ThreadPool(0, 10)
        self.event = threading.Event()
        self.threadpool.start()

        def done():
            self.threadpool.stop()
            del self.threadpool

        self.addCleanup(done)

    def getTimeout(self):
        """
        A reasonable number of seconds to time out.
        """
        return 5

    def test_synchronization(self):
        """
        If multiple threads are waiting on an event (via blocking on something
        in a callable passed to L{threadpool.ThreadPool.callInThread}), and
        there is spare capacity in the threadpool, sending another callable
        which will cause those to un-block to
        L{threadpool.ThreadPool.callInThread} will reliably run that callable
        and un-block the blocked threads promptly.

        @note: This is not really a unit test, it is a stress-test.  You may
            need to run it with C{trial -u} to fail reliably if there is a
            problem.  It is very hard to regression-test for this particular
            bug - one where the thread pool may consider itself as having
            "enough capacity" when it really needs to spin up a new thread if
            it possibly can - in a deterministic way, since the bug can only be
            provoked by subtle race conditions.
        """
        timeout = self.getTimeout()
        self.threadpool.callInThread(self.event.set)
        self.event.wait(timeout)
        self.event.clear()
        for i in range(3):
            self.threadpool.callInThread(self.event.wait)
        self.threadpool.callInThread(self.event.set)
        self.event.wait(timeout)
        if not self.event.isSet():
            self.event.set()
            self.fail("'set' did not run in thread; timed out waiting on 'wait'.")


class MemoryPool(threadpool.ThreadPool):
    """
    A deterministic threadpool that uses in-memory data structures to queue
    work rather than threads to execute work.
    """

    def __init__(self, coordinator, failTest, newWorker, *args, **kwargs):
        """
        Initialize this L{MemoryPool} with a test case.

        @param coordinator: a worker used to coordinate work in the L{Team}
            underlying this threadpool.
        @type coordinator: L{twisted._threads.IExclusiveWorker}

        @param failTest: A 1-argument callable taking an exception and raising
            a test-failure exception.
        @type failTest: 1-argument callable taking (L{Failure}) and raising
            L{unittest.FailTest}.

        @param newWorker: a 0-argument callable that produces a new
            L{twisted._threads.IWorker} provider on each invocation.
        @type newWorker: 0-argument callable returning
            L{twisted._threads.IWorker}.
        """
        self._coordinator = coordinator
        self._failTest = failTest
        self._newWorker = newWorker
        threadpool.ThreadPool.__init__(self, *args, **kwargs)

    def _pool(self, currentLimit, threadFactory):
        """
        Override testing hook to create a deterministic threadpool.

        @param currentLimit: A 1-argument callable which returns the current
            threadpool size limit.

        @param threadFactory: ignored in this invocation; a 0-argument callable
            that would produce a thread.

        @return: a L{Team} backed by the coordinator and worker passed to
            L{MemoryPool.__init__}.
        """

        def respectLimit():
            # The expression in this method copied and pasted from
            # twisted.threads._pool, which is unfortunately bound up
            # with lots of actual-threading stuff.
            stats = team.statistics()
            if (stats.busyWorkerCount + stats.idleWorkerCount) >= currentLimit():
                return None
            return self._newWorker()

        team = Team(
            coordinator=self._coordinator,
            createWorker=respectLimit,
            logException=self._failTest,
        )
        return team


class PoolHelper:
    """
    A L{PoolHelper} constructs a L{threadpool.ThreadPool} that doesn't actually
    use threads, by using the internal interfaces in L{twisted._threads}.

    @ivar performCoordination: a 0-argument callable that will perform one unit
        of "coordination" - work involved in delegating work to other threads -
        and return L{True} if it did any work, L{False} otherwise.

    @ivar workers: the workers which represent the threads within the pool -
        the workers other than the coordinator.
    @type workers: L{list} of 2-tuple of (L{IWorker}, C{workPerformer}) where
        C{workPerformer} is a 0-argument callable like C{performCoordination}.

    @ivar threadpool: a modified L{threadpool.ThreadPool} to test.
    @type threadpool: L{MemoryPool}
    """

    def __init__(self, testCase, *args, **kwargs):
        """
        Create a L{PoolHelper}.

        @param testCase: a test case attached to this helper.

        @type args: The arguments passed to a L{threadpool.ThreadPool}.

        @type kwargs: The arguments passed to a L{threadpool.ThreadPool}
        """
        coordinator, self.performCoordination = createMemoryWorker()
        self.workers = []

        def newWorker():
            self.workers.append(createMemoryWorker())
            return self.workers[-1][0]

        self.threadpool = MemoryPool(
            coordinator, testCase.fail, newWorker, *args, **kwargs
        )

    def performAllCoordination(self):
        """
        Perform all currently scheduled "coordination", which is the work
        involved in delegating work to other threads.
        """
        while self.performCoordination():
            pass


class MemoryBackedTests(unittest.SynchronousTestCase):
    """
    Tests using L{PoolHelper} to deterministically test properties of the
    threadpool implementation.
    """

    def test_workBeforeStarting(self):
        """
        If a threadpool is told to do work before starting, then upon starting
        up, it will start enough workers to handle all of the enqueued work
        that it's been given.
        """
        helper = PoolHelper(self, 0, 10)
        n = 5
        for x in range(n):
            helper.threadpool.callInThread(lambda: None)
        helper.performAllCoordination()
        self.assertEqual(helper.workers, [])
        helper.threadpool.start()
        helper.performAllCoordination()
        self.assertEqual(len(helper.workers), n)

    def test_tooMuchWorkBeforeStarting(self):
        """
        If the amount of work before starting exceeds the maximum number of
        threads allowed to the threadpool, only the maximum count will be
        started.
        """
        helper = PoolHelper(self, 0, 10)
        n = 50
        for x in range(n):
            helper.threadpool.callInThread(lambda: None)
        helper.performAllCoordination()
        self.assertEqual(helper.workers, [])
        helper.threadpool.start()
        helper.performAllCoordination()
        self.assertEqual(len(helper.workers), helper.threadpool.max)
