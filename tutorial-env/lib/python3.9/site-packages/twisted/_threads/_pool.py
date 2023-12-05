# -*- test-case-name: twisted._threads.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Top level thread pool interface, used to implement
L{twisted.python.threadpool}.
"""


from queue import Queue
from threading import Lock, Thread, local as LocalStorage

from twisted.python.log import err
from ._team import Team
from ._threadworker import LockWorker, ThreadWorker


def pool(currentLimit, threadFactory=Thread):
    """
    Construct a L{Team} that spawns threads as a thread pool, with the given
    limiting function.

    @note: Future maintainers: while the public API for the eventual move to
        twisted.threads should look I{something} like this, and while this
        function is necessary to implement the API described by
        L{twisted.python.threadpool}, I am starting to think the idea of a hard
        upper limit on threadpool size is just bad (turning memory performance
        issues into correctness issues well before we run into memory
        pressure), and instead we should build something with reactor
        integration for slowly releasing idle threads when they're not needed
        and I{rate} limiting the creation of new threads rather than just
        hard-capping it.

    @param currentLimit: a callable that returns the current limit on the
        number of workers that the returned L{Team} should create; if it
        already has more workers than that value, no new workers will be
        created.
    @type currentLimit: 0-argument callable returning L{int}

    @param threadFactory: Factory that, when given a C{target} keyword argument,
        returns a L{threading.Thread} that will run that target.
    @type threadFactory: callable returning a L{threading.Thread}

    @return: a new L{Team}.
    """

    def startThread(target):
        return threadFactory(target=target).start()

    def limitedWorkerCreator():
        stats = team.statistics()
        if stats.busyWorkerCount + stats.idleWorkerCount >= currentLimit():
            return None
        return ThreadWorker(startThread, Queue())

    team = Team(
        coordinator=LockWorker(Lock(), LocalStorage()),
        createWorker=limitedWorkerCreator,
        logException=err,
    )
    return team
