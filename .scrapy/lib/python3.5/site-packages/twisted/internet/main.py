# -*- test-case-name: twisted.internet.test.test_main -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Backwards compatibility, and utility functions.

In general, this module should not be used, other than by reactor authors
who need to use the 'installReactor' method.
"""

from __future__ import division, absolute_import

from twisted.internet import error

CONNECTION_DONE = error.ConnectionDone('Connection done')
CONNECTION_LOST = error.ConnectionLost('Connection lost')



def installReactor(reactor):
    """
    Install reactor C{reactor}.

    @param reactor: An object that provides one or more IReactor* interfaces.
    """
    # this stuff should be common to all reactors.
    import twisted.internet
    import sys
    if 'twisted.internet.reactor' in sys.modules:
        raise error.ReactorAlreadyInstalledError("reactor already installed")
    twisted.internet.reactor = reactor
    sys.modules['twisted.internet.reactor'] = reactor


__all__ = ["CONNECTION_LOST", "CONNECTION_DONE", "installReactor"]
