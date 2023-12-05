# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted._threads._threadworker}.
"""


import gc
import weakref
from threading import ThreadError, local

from twisted.trial.unittest import SynchronousTestCase
from .. import AlreadyQuit, LockWorker, ThreadWorker


class FakeQueueEmpty(Exception):
    """
    L{FakeQueue}'s C{get} has exhausted the queue.
    """


class WouldDeadlock(Exception):
    """
    If this were a real lock, you'd be deadlocked because the lock would be
    double-acquired.
    """


class FakeThread:
    """
    A fake L{threading.Thread}.

    @ivar target: A target function to run.
    @type target: L{callable}

    @ivar started: Has this thread been started?
    @type started: L{bool}
    """

    def __init__(self, target):
        """
        Create a L{FakeThread} with a target.
        """
        self.target = target
        self.started = False

    def start(self):
        """
        Set the "started" flag.
        """
        self.started = True


class FakeQueue:
    """
    A fake L{Queue} implementing C{put} and C{get}.

    @ivar items: A lit of items placed by C{put} but not yet retrieved by
        C{get}.
    @type items: L{list}
    """

    def __init__(self):
        """
        Create a L{FakeQueue}.
        """
        self.items = []

    def put(self, item):
        """
        Put an item into the queue for later retrieval by L{FakeQueue.get}.

        @param item: any object
        """
        self.items.append(item)

    def get(self):
        """
        Get an item.

        @return: an item previously put by C{put}.
        """
        if not self.items:
            raise FakeQueueEmpty()
        return self.items.pop(0)


class FakeLock:
    """
    A stand-in for L{threading.Lock}.

    @ivar acquired: Whether this lock is presently acquired.
    """

    def __init__(self):
        """
        Create a lock in the un-acquired state.
        """
        self.acquired = False

    def acquire(self):
        """
        Acquire the lock.  Raise an exception if the lock is already acquired.
        """
        if self.acquired:
            raise WouldDeadlock()
        self.acquired = True

    def release(self):
        """
        Release the lock.  Raise an exception if the lock is not presently
        acquired.
        """
        if not self.acquired:
            raise ThreadError()
        self.acquired = False


class ThreadWorkerTests(SynchronousTestCase):
    """
    Tests for L{ThreadWorker}.
    """

    def setUp(self):
        """
        Create a worker with fake threads.
        """
        self.fakeThreads = []
        self.fakeQueue = FakeQueue()

        def startThread(target):
            newThread = FakeThread(target=target)
            newThread.start()
            self.fakeThreads.append(newThread)
            return newThread

        self.worker = ThreadWorker(startThread, self.fakeQueue)

    def test_startsThreadAndPerformsWork(self):
        """
        L{ThreadWorker} calls its C{createThread} callable to create a thread,
        its C{createQueue} callable to create a queue, and then the thread's
        target pulls work from that queue.
        """
        self.assertEqual(len(self.fakeThreads), 1)
        self.assertEqual(self.fakeThreads[0].started, True)

        def doIt():
            doIt.done = True

        doIt.done = False
        self.worker.do(doIt)
        self.assertEqual(doIt.done, False)
        self.assertRaises(FakeQueueEmpty, self.fakeThreads[0].target)
        self.assertEqual(doIt.done, True)

    def test_quitPreventsFutureCalls(self):
        """
        L{ThreadWorker.quit} causes future calls to L{ThreadWorker.do} and
        L{ThreadWorker.quit} to raise L{AlreadyQuit}.
        """
        self.worker.quit()
        self.assertRaises(AlreadyQuit, self.worker.quit)
        self.assertRaises(AlreadyQuit, self.worker.do, list)


class LockWorkerTests(SynchronousTestCase):
    """
    Tests for L{LockWorker}.
    """

    def test_fakeDeadlock(self):
        """
        The L{FakeLock} test fixture will alert us if there's a potential
        deadlock.
        """
        lock = FakeLock()
        lock.acquire()
        self.assertRaises(WouldDeadlock, lock.acquire)

    def test_fakeDoubleRelease(self):
        """
        The L{FakeLock} test fixture will alert us if there's a potential
        double-release.
        """
        lock = FakeLock()
        self.assertRaises(ThreadError, lock.release)
        lock.acquire()
        self.assertEqual(None, lock.release())
        self.assertRaises(ThreadError, lock.release)

    def test_doExecutesImmediatelyWithLock(self):
        """
        L{LockWorker.do} immediately performs the work it's given, while the
        lock is acquired.
        """
        storage = local()
        lock = FakeLock()
        worker = LockWorker(lock, storage)

        def work():
            work.done = True
            work.acquired = lock.acquired

        work.done = False
        worker.do(work)
        self.assertEqual(work.done, True)
        self.assertEqual(work.acquired, True)
        self.assertEqual(lock.acquired, False)

    def test_doUnwindsReentrancy(self):
        """
        If L{LockWorker.do} is called recursively, it postpones the inner call
        until the outer one is complete.
        """
        lock = FakeLock()
        worker = LockWorker(lock, local())
        levels = []
        acquired = []

        def work():
            work.level += 1
            levels.append(work.level)
            acquired.append(lock.acquired)
            if len(levels) < 2:
                worker.do(work)
            work.level -= 1

        work.level = 0
        worker.do(work)
        self.assertEqual(levels, [1, 1])
        self.assertEqual(acquired, [True, True])

    def test_quit(self):
        """
        L{LockWorker.quit} frees the resources associated with its lock and
        causes further calls to C{do} and C{quit} to fail.
        """
        lock = FakeLock()
        ref = weakref.ref(lock)
        worker = LockWorker(lock, local())
        lock = None
        self.assertIsNot(ref(), None)
        worker.quit()
        gc.collect()
        self.assertIs(ref(), None)
        self.assertRaises(AlreadyQuit, worker.quit)
        self.assertRaises(AlreadyQuit, worker.do, list)

    def test_quitWhileWorking(self):
        """
        If L{LockWorker.quit} is invoked during a call to L{LockWorker.do}, all
        recursive work scheduled with L{LockWorker.do} will be completed and
        the lock will be released.
        """
        lock = FakeLock()
        ref = weakref.ref(lock)
        worker = LockWorker(lock, local())

        def phase1():
            worker.do(phase2)
            worker.quit()
            self.assertRaises(AlreadyQuit, worker.do, list)
            phase1.complete = True

        phase1.complete = False

        def phase2():
            phase2.complete = True
            phase2.acquired = lock.acquired

        phase2.complete = False
        worker.do(phase1)
        self.assertEqual(phase1.complete, True)
        self.assertEqual(phase2.complete, True)
        self.assertEqual(lock.acquired, False)
        lock = None
        gc.collect()
        self.assertIs(ref(), None)

    def test_quitWhileGettingLock(self):
        """
        If L{LockWorker.do} is called concurrently with L{LockWorker.quit}, and
        C{quit} wins the race before C{do} gets the lock attribute, then
        L{AlreadyQuit} will be raised.
        """

        class RacyLockWorker(LockWorker):
            @property
            def _lock(self):
                self.quit()
                return self.__dict__["_lock"]

            @_lock.setter
            def _lock(self, value):
                self.__dict__["_lock"] = value

        worker = RacyLockWorker(FakeLock(), local())
        self.assertRaises(AlreadyQuit, worker.do, list)
