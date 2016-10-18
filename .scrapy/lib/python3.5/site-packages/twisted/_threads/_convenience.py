# -*- test-case-name: twisted._threads.test.test_convenience -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Common functionality used within the implementation of various workers.
"""

from __future__ import absolute_import, division, print_function

from ._ithreads import AlreadyQuit


class Quit(object):
    """
    A flag representing whether a worker has been quit.

    @ivar isSet: Whether this flag is set.
    @type isSet: L{bool}
    """

    def __init__(self):
        """
        Create a L{Quit} un-set.
        """
        self.isSet = False


    def set(self):
        """
        Set the flag if it has not been set.

        @raise AlreadyQuit: If it has been set.
        """
        self.check()
        self.isSet = True


    def check(self):
        """
        Check if the flag has been set.

        @raise AlreadyQuit: If it has been set.
        """
        if self.isSet:
            raise AlreadyQuit()
