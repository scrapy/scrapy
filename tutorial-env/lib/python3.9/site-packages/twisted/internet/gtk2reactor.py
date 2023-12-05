# -*- test-case-name: twisted.internet.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
This module provides support for Twisted to interact with the glib/gtk2
mainloop.

In order to use this support, simply do the following::

    from twisted.internet import gtk2reactor
    gtk2reactor.install()

Then use twisted.internet APIs as usual.  The other methods here are not
intended to be called directly.
"""

# System Imports
import sys

# Twisted Imports
from twisted.internet import _glibbase
from twisted.python import runtime

# Certain old versions of pygtk and gi crash if imported at the same
# time. This is a problem when running Twisted's unit tests, since they will
# attempt to run both gtk2 and gtk3/gi tests. However, gireactor makes sure
# that if we are in such an old version, and gireactor was imported,
# gtk2reactor will not be importable. So we don't *need* to enforce that here
# as well; whichever is imported first will still win. Moreover, additional
# enforcement in this module is unnecessary in modern versions, and downright
# problematic in certain versions where for some reason importing gtk also
# imports some subset of gi. So we do nothing here, relying on gireactor to
# prevent the crash.

try:
    if not hasattr(sys, "frozen"):
        # Don't want to check this for py2exe
        import pygtk  # type: ignore[import]

        pygtk.require("2.0")
except (ImportError, AttributeError):
    pass  # maybe we're using pygtk before this hack existed.

import gobject  # type: ignore[import]

if hasattr(gobject, "threads_init"):
    # recent versions of python-gtk expose this. python-gtk=2.4.1
    # (wrapping glib-2.4.7) does. python-gtk=2.0.0 (wrapping
    # glib-2.2.3) does not.
    gobject.threads_init()


class Gtk2Reactor(_glibbase.GlibReactorBase):
    """
    PyGTK+ 2 event loop reactor.
    """

    _POLL_DISCONNECTED = gobject.IO_HUP | gobject.IO_ERR | gobject.IO_NVAL
    _POLL_IN = gobject.IO_IN
    _POLL_OUT = gobject.IO_OUT

    # glib's iochannel sources won't tell us about any events that we haven't
    # asked for, even if those events aren't sensible inputs to the poll()
    # call.
    INFLAGS = _POLL_IN | _POLL_DISCONNECTED
    OUTFLAGS = _POLL_OUT | _POLL_DISCONNECTED

    def __init__(self, useGtk=True):
        _gtk = None
        if useGtk is True:
            import gtk as _gtk  # type: ignore[import]

        _glibbase.GlibReactorBase.__init__(self, gobject, _gtk, useGtk=useGtk)


class PortableGtkReactor(_glibbase.PortableGlibReactorBase):
    """
    Reactor that works on Windows.

    Sockets aren't supported by GTK+'s input_add on Win32.
    """

    def __init__(self, useGtk=True):
        _gtk = None
        if useGtk is True:
            import gtk as _gtk

        _glibbase.PortableGlibReactorBase.__init__(self, gobject, _gtk, useGtk=useGtk)


def install(useGtk=True):
    """
    Configure the twisted mainloop to be run inside the gtk mainloop.

    @param useGtk: should glib rather than GTK+ event loop be
        used (this will be slightly faster but does not support GUI).
    """
    reactor = Gtk2Reactor(useGtk)
    from twisted.internet.main import installReactor

    installReactor(reactor)
    return reactor


def portableInstall(useGtk=True):
    """
    Configure the twisted mainloop to be run inside the gtk mainloop.
    """
    reactor = PortableGtkReactor()
    from twisted.internet.main import installReactor

    installReactor(reactor)
    return reactor


if runtime.platform.getType() == "posix":
    install = install
else:
    install = portableInstall


__all__ = ["install"]
