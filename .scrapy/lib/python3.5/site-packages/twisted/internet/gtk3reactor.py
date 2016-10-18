# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module provides support for Twisted to interact with the gtk3 mainloop
via Gobject introspection. This is like gi, but slightly slower and requires a
working $DISPLAY.

In order to use this support, simply do the following::

    from twisted.internet import gtk3reactor
    gtk3reactor.install()

If you wish to use a GApplication, register it with the reactor::

    from twisted.internet import reactor
    reactor.registerGApplication(app)

Then use twisted.internet APIs as usual.
"""

from __future__ import division, absolute_import

import os

from twisted.internet import gireactor
from twisted.python import runtime

# Newer versions of gtk3/pygoject raise a RuntimeError, or just break in a
# confusing manner, if the program is not running under X11.  We therefore try
# to fail in a more reasonable manner, and check for $DISPLAY as a reasonable
# approximation of availability of X11. This is somewhat over-aggressive,
# since some older versions of gtk3/pygobject do work with missing $DISPLAY,
# but it's too hard to figure out which, so we always require it.
if (runtime.platform.getType() == 'posix' and
    not runtime.platform.isMacOSX() and not os.environ.get("DISPLAY")):
    raise ImportError(
        "Gtk3 requires X11, and no DISPLAY environment variable is set")


class Gtk3Reactor(gireactor.GIReactor):
    """
    A reactor using the gtk3+ event loop.
    """

    def __init__(self):
        """
        Override init to set the C{useGtk} flag.
        """
        gireactor.GIReactor.__init__(self, useGtk=True)



class PortableGtk3Reactor(gireactor.PortableGIReactor):
    """
    Portable GTK+ 3.x reactor.
    """
    def __init__(self):
        """
        Override init to set the C{useGtk} flag.
        """
        gireactor.PortableGIReactor.__init__(self, useGtk=True)



def install():
    """
    Configure the Twisted mainloop to be run inside the gtk3+ mainloop.
    """
    if runtime.platform.getType() == 'posix':
        reactor = Gtk3Reactor()
    else:
        reactor = PortableGtk3Reactor()

    from twisted.internet.main import installReactor
    installReactor(reactor)
    return reactor


__all__ = ['install']
