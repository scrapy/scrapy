# -*- test-case-name: twisted._threads.test.test_memory -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation of an in-memory worker that defers execution.
"""


from zope.interface import implementer

from . import IWorker
from ._convenience import Quit

NoMoreWork = object()


@implementer(IWorker)
class MemoryWorker:
    """
    An L{IWorker} that queues work for later performance.

    @ivar _quit: a flag indicating
    @type _quit: L{Quit}
    """

    def __init__(self, pending=list):
        """
        Create a L{MemoryWorker}.
        """
        self._quit = Quit()
        self._pending = pending()

    def do(self, work):
        """
        Queue some work for to perform later; see L{createMemoryWorker}.

        @param work: The work to perform.
        """
        self._quit.check()
        self._pending.append(work)

    def quit(self):
        """
        Quit this worker.
        """
        self._quit.set()
        self._pending.append(NoMoreWork)


def createMemoryWorker():
    """
    Create an L{IWorker} that does nothing but defer work, to be performed
    later.

    @return: a worker that will enqueue work to perform later, and a callable
        that will perform one element of that work.
    @rtype: 2-L{tuple} of (L{IWorker}, L{callable})
    """

    def perform():
        if not worker._pending:
            return False
        if worker._pending[0] is NoMoreWork:
            return False
        worker._pending.pop(0)()
        return True

    worker = MemoryWorker()
    return (worker, perform)
