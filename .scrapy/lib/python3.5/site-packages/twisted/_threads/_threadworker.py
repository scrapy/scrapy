# -*- test-case-name: twisted._threads.test.test_threadworker -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation of an L{IWorker} based on native threads and queues.
"""

from __future__ import absolute_import, division, print_function

from zope.interface import implementer
from ._ithreads import IExclusiveWorker
from ._convenience import Quit


_stop = object()

@implementer(IExclusiveWorker)
class ThreadWorker(object):
    """
    An L{IExclusiveWorker} implemented based on a single thread and a queue.

    This worker ensures exclusivity (i.e. it is an L{IExclusiveWorker} and not
    an L{IWorker}) by performing all of the work passed to C{do} on the I{same}
    thread.
    """

    def __init__(self, startThread, queue):
        """
        Create a L{ThreadWorker} with a function to start a thread and a queue
        to use to communicate with that thread.

        @param startThread: a callable that takes a callable to run in another
            thread.
        @type startThread: callable taking a 0-argument callable and returning
            nothing.

        @param queue: A L{Queue} to use to give tasks to the thread created by
            C{startThread}.
        @param queue: L{Queue}
        """
        self._q = queue
        self._hasQuit = Quit()
        def work():
            for task in iter(queue.get, _stop):
                task()
        startThread(work)


    def do(self, task):
        """
        Perform the given task on the thread owned by this L{ThreadWorker}.

        @param task: the function to call on a thread.
        """
        self._hasQuit.check()
        self._q.put(task)


    def quit(self):
        """
        Reject all future work and stop the thread started by C{__init__}.
        """
        # Reject all future work.  Set this _before_ enqueueing _stop, so
        # that no work is ever enqueued _after_ _stop.
        self._hasQuit.set()
        self._q.put(_stop)



@implementer(IExclusiveWorker)
class LockWorker(object):
    """
    An L{IWorker} implemented based on a mutual-exclusion lock.
    """

    def __init__(self, lock, local):
        """
        @param lock: A mutual-exclusion lock, with C{acquire} and C{release}
            methods.
        @type lock: L{threading.Lock}

        @param local: Local storage.
        @type local: L{threading.local}
        """
        self._quit = Quit()
        self._lock = lock
        self._local = local


    def do(self, work):
        """
        Do the given work on this thread, with the mutex acquired.  If this is
        called re-entrantly, return and wait for the outer invocation to do the
        work.

        @param work: the work to do with the lock held.
        """
        lock = self._lock
        local = self._local
        self._quit.check()
        working = getattr(local, "working", None)
        if working is None:
            working = local.working = []
            working.append(work)
            lock.acquire()
            try:
                while working:
                    working.pop(0)()
            finally:
                lock.release()
                local.working = None
        else:
            working.append(work)


    def quit(self):
        """
        Quit this L{LockWorker}.
        """
        self._quit.set()
        self._lock = None

