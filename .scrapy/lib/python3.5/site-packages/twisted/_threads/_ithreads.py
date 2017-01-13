# -*- test-case-name: twisted._threads.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interfaces related to threads.
"""

from __future__ import absolute_import, division, print_function

from zope.interface import Interface


class AlreadyQuit(Exception):
    """
    This worker worker is dead and cannot execute more instructions.
    """



class IWorker(Interface):
    """
    A worker that can perform some work concurrently.

    All methods on this interface must be thread-safe.
    """

    def do(task):
        """
        Perform the given task.

        As an interface, this method makes no specific claims about concurrent
        execution.  An L{IWorker}'s C{do} implementation may defer execution
        for later on the same thread, immediately on a different thread, or
        some combination of the two.  It is valid for a C{do} method to
        schedule C{task} in such a way that it may never be executed.

        It is important for some implementations to provide specific properties
        with respect to where C{task} is executed, of course, and client code
        may rely on a more specific implementation of C{do} than L{IWorker}.

        @param task: a task to call in a thread or other concurrent context.
        @type task: 0-argument callable

        @raise AlreadyQuit: if C{quit} has been called.
        """

    def quit():
        """
        Free any resources associated with this L{IWorker} and cause it to
        reject all future work.

        @raise: L{AlreadyQuit} if this method has already been called.
        """


class IExclusiveWorker(IWorker):
    """
    Like L{IWorker}, but with the additional guarantee that the callables
    passed to C{do} will not be called exclusively with each other.
    """
