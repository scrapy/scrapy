# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

"""Process utils."""

import errno
import os
import sys
import time
from binascii import hexlify


try:
    import multiprocessing
except ImportError:
    multiprocessing = None

from ._compat import long
from .log import logger


_task_id = None


def cpu_count():
    """Returns the number of processors on this machine."""
    if multiprocessing is None:
        return 1
    try:
        return multiprocessing.cpu_count()
    except NotImplementedError:
        pass
    try:
        return os.sysconf("SC_NPROCESSORS_CONF")
    except (AttributeError, ValueError):
        pass
    return 1


def _reseed_random():
    if 'random' not in sys.modules:
        return
    import random

    # If os.urandom is available, this method does the same thing as
    # random.seed.  If os.urandom is not available, we mix in the pid in
    # addition to a timestamp.
    try:
        seed = long(hexlify(os.urandom(16)), 16)
    except NotImplementedError:
        seed = int(time.time() * 1000) ^ os.getpid()
    random.seed(seed)


def fork_processes(number, max_restarts=100):
    """Starts multiple worker processes.

    If *number* is None or <= 0, we detect the number of cores available
    on this machine and fork that number of child processes.
    If *number* is given and > 0, we fork that specific number of
    sub-processes.

    Since we use processes and not threads, there is no shared memory
    between any server code.

    In each child process, *fork_processes* returns its *task id*, a
    number between 0 and *number*.  Processes that exit abnormally
    (due to a signal or non-zero exit status) are restarted with the
    same id (up to *max_restarts* times). In the parent process,
    *fork_processes* returns None if all child processes have exited
    normally, but will otherwise only exit by throwing an exception.
    """
    global _task_id
    assert _task_id is None
    if number is None or number <= 0:
        number = cpu_count()
    logger.info("starting %d pre-fork processes", number)
    children = {}

    def start_child(i):
        pid = os.fork()
        if pid == 0:
            # child process
            _reseed_random()
            global _task_id
            _task_id = i
            return i
        else:
            children[pid] = i
            return None

    for i in range(number):
        id = start_child(i)
        if id is not None:
            return id
    num_restarts = 0
    while children:
        try:
            pid, status = os.wait()
        except OSError as e:
            if e.errno == errno.EINTR:
                continue
            raise
        if pid not in children:
            continue
        id = children.pop(pid)
        if os.WIFSIGNALED(status):
            logger.warning("child %d (pid %d) killed by signal %d, restarting",
                           id, pid, os.WTERMSIG(status))
        elif os.WEXITSTATUS(status) != 0:
            logger.warning(
                "child %d (pid %d) exited with status %d, restarting",
                id, pid, os.WEXITSTATUS(status))
        else:
            logger.info("child %d (pid %d) exited normally", id, pid)
            continue
        num_restarts += 1
        if num_restarts > max_restarts:
            raise RuntimeError("Too many child restarts, giving up")
        new_id = start_child(id)
        if new_id is not None:
            return new_id
    # All child processes exited cleanly, so exit the master process
    # instead of just returning to right after the call to
    # fork_processes (which will probably just start up another IOLoop
    # unless the caller checks the return value).
    sys.exit(0)
