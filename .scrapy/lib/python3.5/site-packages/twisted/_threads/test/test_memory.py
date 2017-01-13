# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted._threads._memory}.
"""
from __future__ import absolute_import, division, print_function

from zope.interface.verify import verifyObject

from twisted.trial.unittest import SynchronousTestCase
from .. import AlreadyQuit, IWorker, createMemoryWorker


class MemoryWorkerTests(SynchronousTestCase):
    """
    Tests for L{MemoryWorker}.
    """

    def test_createWorkerAndPerform(self):
        """
        L{createMemoryWorker} creates an L{IWorker} and a callable that can
        perform work on it.  The performer returns C{True} if it accomplished
        useful work.
        """
        worker, performer = createMemoryWorker()
        verifyObject(IWorker, worker)
        done = []
        worker.do(lambda: done.append(3))
        worker.do(lambda: done.append(4))
        self.assertEqual(done, [])
        self.assertEqual(performer(), True)
        self.assertEqual(done, [3])
        self.assertEqual(performer(), True)
        self.assertEqual(done, [3, 4])


    def test_quitQuits(self):
        """
        Calling C{quit} on the worker returned by L{createMemoryWorker} causes
        its C{do} and C{quit} methods to raise L{AlreadyQuit}; its C{perform}
        callable will start raising L{AlreadyQuit} when the work already
        provided to C{do} has been exhausted.
        """
        worker, performer = createMemoryWorker()
        done = []
        def moreWork():
            done.append(7)
        worker.do(moreWork)
        worker.quit()
        self.assertRaises(AlreadyQuit, worker.do, moreWork)
        self.assertRaises(AlreadyQuit, worker.quit)
        performer()
        self.assertEqual(done, [7])
        self.assertEqual(performer(), False)


    def test_performWhenNothingToDoYet(self):
        """
        The C{perform} callable returned by L{createMemoryWorker} will return
        no result when there's no work to do yet.  Since there is no work to
        do, the performer returns C{False}.
        """
        worker, performer = createMemoryWorker()
        self.assertEqual(performer(), False)
