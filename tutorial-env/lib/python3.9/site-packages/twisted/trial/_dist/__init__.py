# -*- test-case-name: twisted.trial._dist.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This package implements the distributed Trial test runner:

  - The L{twisted.trial._dist.disttrial} module implements a test runner which
    runs in a manager process and can launch additional worker processes in
    which to run tests and gather up results from all of them.

  - The L{twisted.trial._dist.options} module defines command line options used
    to configure the distributed test runner.

  - The L{twisted.trial._dist.managercommands} module defines AMP commands
    which are sent from worker processes back to the manager process to report
    the results of tests.

  - The L{twisted.trial._dist.workercommands} module defines AMP commands which
    are sent from the manager process to the worker processes to control the
    execution of tests there.

  - The L{twisted.trial._dist.distreporter} module defines a proxy for
    L{twisted.trial.itrial.IReporter} which enforces the typical requirement
    that results be passed to a reporter for only one test at a time, allowing
    any reporter to be used with despite disttrial's simultaneously running
    tests.

  - The L{twisted.trial._dist.workerreporter} module implements a
    L{twisted.trial.itrial.IReporter} which is used by worker processes and
    reports results back to the manager process using AMP commands.

  - The L{twisted.trial._dist.workertrial} module is a runnable script which is
    the main point for worker processes.

  - The L{twisted.trial._dist.worker} process defines the manager's AMP
    protocol for accepting results from worker processes and a process protocol
    for use running workers as local child processes (as opposed to
    distributing them to another host).

@since: 12.3
"""

# File descriptors numbers used to set up pipes with the worker.
_WORKER_AMP_STDIN = 3

_WORKER_AMP_STDOUT = 4
