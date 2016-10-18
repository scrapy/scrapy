# -*- coding: utf-8 -*-
"""
    sphinx.util.parallel
    ~~~~~~~~~~~~~~~~~~~~

    Parallel building utilities.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import os
import time
import traceback
from math import sqrt

try:
    import multiprocessing
except ImportError:
    multiprocessing = None

from six import iteritems

from sphinx.errors import SphinxParallelError

# our parallel functionality only works for the forking Process
parallel_available = multiprocessing and (os.name == 'posix')


class SerialTasks(object):
    """Has the same interface as ParallelTasks, but executes tasks directly."""

    def __init__(self, nproc=1):
        pass

    def add_task(self, task_func, arg=None, result_func=None):
        if arg is not None:
            res = task_func(arg)
        else:
            res = task_func()
        if result_func:
            result_func(res)

    def join(self):
        pass


class ParallelTasks(object):
    """Executes *nproc* tasks in parallel after forking."""

    def __init__(self, nproc):
        self.nproc = nproc
        # (optional) function performed by each task on the result of main task
        self._result_funcs = {}
        # task arguments
        self._args = {}
        # list of subprocesses (both started and waiting)
        self._procs = {}
        # list of receiving pipe connections of running subprocesses
        self._precvs = {}
        # list of receiving pipe connections of waiting subprocesses
        self._precvsWaiting = {}
        # number of working subprocesses
        self._pworking = 0
        # task number of each subprocess
        self._taskid = 0

    def _process(self, pipe, func, arg):
        try:
            if arg is None:
                ret = func()
            else:
                ret = func(arg)
            pipe.send((False, ret))
        except BaseException as err:
            pipe.send((True, (err, traceback.format_exc())))

    def add_task(self, task_func, arg=None, result_func=None):
        tid = self._taskid
        self._taskid += 1
        self._result_funcs[tid] = result_func or (lambda arg: None)
        self._args[tid] = arg
        precv, psend = multiprocessing.Pipe(False)
        proc = multiprocessing.Process(target=self._process,
                                       args=(psend, task_func, arg))
        self._procs[tid] = proc
        self._precvsWaiting[tid] = precv
        self._join_one()

    def join(self):
        while self._pworking:
            self._join_one()

    def _join_one(self):
        for tid, pipe in iteritems(self._precvs):
            if pipe.poll():
                exc, result = pipe.recv()
                if exc:
                    raise SphinxParallelError(*result)
                self._result_funcs.pop(tid)(self._args.pop(tid), result)
                self._procs[tid].join()
                self._pworking -= 1
                break
        else:
            time.sleep(0.02)
        while self._precvsWaiting and self._pworking < self.nproc:
            newtid, newprecv = self._precvsWaiting.popitem()
            self._precvs[newtid] = newprecv
            self._procs[newtid].start()
            self._pworking += 1


def make_chunks(arguments, nproc, maxbatch=10):
    # determine how many documents to read in one go
    nargs = len(arguments)
    chunksize = nargs // nproc
    if chunksize >= maxbatch:
        # try to improve batch size vs. number of batches
        chunksize = int(sqrt(nargs/nproc * maxbatch))
    if chunksize == 0:
        chunksize = 1
    nchunks, rest = divmod(nargs, chunksize)
    if rest:
        nchunks += 1
    # partition documents in "chunks" that will be written by one Process
    return [arguments[i*chunksize:(i+1)*chunksize] for i in range(nchunks)]
