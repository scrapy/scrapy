# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted._threads._team}.
"""

from __future__ import absolute_import, division, print_function

from twisted.trial.unittest import SynchronousTestCase

from twisted.python.context import call, get
from twisted.python.components import proxyForInterface

from twisted.python.failure import Failure
from .. import IWorker, Team, createMemoryWorker, AlreadyQuit

class ContextualWorker(proxyForInterface(IWorker, "_realWorker")):
    """
    A worker implementation that supplies a context.
    """

    def __init__(self, realWorker, **ctx):
        """
        Create with a real worker and a context.
        """
        self._realWorker = realWorker
        self._context = ctx


    def do(self, work):
        """
        Perform the given work with the context given to __init__.

        @param work: the work to pass on to the real worker.
        """
        super(ContextualWorker, self).do(lambda: call(self._context, work))



class TeamTests(SynchronousTestCase):
    """
    Tests for L{Team}
    """

    def setUp(self):
        """
        Set up a L{Team} with inspectable, synchronous workers that can be
        single-stepped.
        """
        coordinator, self.coordinateOnce = createMemoryWorker()
        self.coordinator = ContextualWorker(coordinator, worker="coordinator")
        self.workerPerformers = []
        self.allWorkersEver = []
        self.allUnquitWorkers = []
        self.activePerformers = []
        self.noMoreWorkers = lambda: False

        def createWorker():
            if self.noMoreWorkers():
                return None
            worker, performer = createMemoryWorker()
            self.workerPerformers.append(performer)
            self.activePerformers.append(performer)
            cw = ContextualWorker(worker, worker=len(self.workerPerformers))
            self.allWorkersEver.append(cw)
            self.allUnquitWorkers.append(cw)
            realQuit = cw.quit
            def quitAndRemove():
                realQuit()
                self.allUnquitWorkers.remove(cw)
                self.activePerformers.remove(performer)
            cw.quit = quitAndRemove
            return cw

        self.failures = []
        def logException():
            self.failures.append(Failure())
        self.team = Team(coordinator, createWorker, logException)


    def coordinate(self):
        """
        Perform all work currently scheduled in the coordinator.

        @return: whether any coordination work was performed; if the
            coordinator was idle when this was called, return L{False}
            (otherwise L{True}).
        @rtype: L{bool}
        """
        did = False
        while self.coordinateOnce():
            did = True
        return did


    def performAllOutstandingWork(self):
        """
        Perform all work on the coordinator and worker performers that needs to
        be done.
        """
        continuing = True
        while continuing:
            continuing = self.coordinate()
            for performer in self.workerPerformers:
                if performer in self.activePerformers:
                    performer()
            continuing = continuing or self.coordinate()


    def test_doDoesWorkInWorker(self):
        """
        L{Team.do} does the work in a worker created by the createWorker
        callable.
        """
        def something():
            something.who = get("worker")
        self.team.do(something)
        self.coordinate()
        self.assertEqual(self.team.statistics().busyWorkerCount, 1)
        self.performAllOutstandingWork()
        self.assertEqual(something.who, 1)
        self.assertEqual(self.team.statistics().busyWorkerCount, 0)


    def test_initialStatistics(self):
        """
        L{Team.statistics} returns an object with idleWorkerCount,
        busyWorkerCount, and backloggedWorkCount integer attributes.
        """
        stats = self.team.statistics()
        self.assertEqual(stats.idleWorkerCount, 0)
        self.assertEqual(stats.busyWorkerCount, 0)
        self.assertEqual(stats.backloggedWorkCount, 0)


    def test_growCreatesIdleWorkers(self):
        """
        L{Team.grow} increases the number of available idle workers.
        """
        self.team.grow(5)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.workerPerformers), 5)


    def test_growCreateLimit(self):
        """
        L{Team.grow} increases the number of available idle workers until the
        C{createWorker} callable starts returning None.
        """
        self.noMoreWorkers = lambda: len(self.allWorkersEver) >= 3
        self.team.grow(5)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.allWorkersEver), 3)
        self.assertEqual(self.team.statistics().idleWorkerCount, 3)


    def test_shrinkQuitsWorkers(self):
        """
        L{Team.shrink} will quit the given number of workers.
        """
        self.team.grow(5)
        self.performAllOutstandingWork()
        self.team.shrink(3)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.allUnquitWorkers), 2)


    def test_shrinkToZero(self):
        """
        L{Team.shrink} with no arguments will stop all outstanding workers.
        """
        self.team.grow(10)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.allUnquitWorkers), 10)
        self.team.shrink()
        self.assertEqual(len(self.allUnquitWorkers), 10)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.allUnquitWorkers), 0)


    def test_moreWorkWhenNoWorkersAvailable(self):
        """
        When no additional workers are available, the given work is backlogged,
        and then performed later when the work was.
        """
        self.team.grow(3)
        self.coordinate()
        def something():
            something.times += 1
        something.times = 0
        self.assertEqual(self.team.statistics().idleWorkerCount, 3)
        for i in range(3):
            self.team.do(something)
        # Make progress on the coordinator but do _not_ actually complete the
        # work, yet.
        self.coordinate()
        self.assertEqual(self.team.statistics().idleWorkerCount, 0)
        self.noMoreWorkers = lambda: True
        self.team.do(something)
        self.coordinate()
        self.assertEqual(self.team.statistics().idleWorkerCount, 0)
        self.assertEqual(self.team.statistics().backloggedWorkCount, 1)
        self.performAllOutstandingWork()
        self.assertEqual(self.team.statistics().backloggedWorkCount, 0)
        self.assertEqual(something.times, 4)


    def test_exceptionInTask(self):
        """
        When an exception is raised in a task passed to L{Team.do}, the
        C{logException} given to the L{Team} at construction is invoked in the
        exception context.
        """
        self.team.do(lambda: 1/0)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.failures), 1)
        self.assertEqual(self.failures[0].type, ZeroDivisionError)


    def test_quit(self):
        """
        L{Team.quit} causes future invocations of L{Team.do} and L{Team.quit}
        to raise L{AlreadyQuit}.
        """
        self.team.quit()
        self.assertRaises(AlreadyQuit, self.team.quit)
        self.assertRaises(AlreadyQuit, self.team.do, list)


    def test_quitQuits(self):
        """
        L{Team.quit} causes all idle workers, as well as the coordinator
        worker, to quit.
        """
        for x in range(10):
            self.team.do(list)
        self.performAllOutstandingWork()
        self.team.quit()
        self.performAllOutstandingWork()
        self.assertEqual(len(self.allUnquitWorkers), 0)
        self.assertRaises(AlreadyQuit, self.coordinator.quit)


    def test_quitQuitsLaterWhenBusy(self):
        """
        L{Team.quit} causes all busy workers to be quit once they've finished
        the work they've been given.
        """
        self.team.grow(10)
        for x in range(5):
            self.team.do(list)
        self.coordinate()
        self.team.quit()
        self.coordinate()
        self.assertEqual(len(self.allUnquitWorkers), 5)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.allUnquitWorkers), 0)
        self.assertRaises(AlreadyQuit, self.coordinator.quit)


    def test_quitConcurrentWithWorkHappening(self):
        """
        If work happens after L{Team.quit} sets its C{Quit} flag, but before
        any other work takes place, the L{Team} should still exit gracefully.
        """
        self.team.do(list)
        originalSet = self.team._quit.set
        def performWorkConcurrently():
            originalSet()
            self.performAllOutstandingWork()
        self.team._quit.set = performWorkConcurrently
        self.team.quit()
        self.assertRaises(AlreadyQuit, self.team.quit)
        self.assertRaises(AlreadyQuit, self.team.do, list)


    def test_shrinkWhenBusy(self):
        """
        L{Team.shrink} will wait for busy workers to finish being busy and then
        quit them.
        """
        for x in range(10):
            self.team.do(list)
        self.coordinate()
        self.assertEqual(len(self.allUnquitWorkers), 10)
        # There should be 10 busy workers at this point.
        self.team.shrink(7)
        self.performAllOutstandingWork()
        self.assertEqual(len(self.allUnquitWorkers), 3)
