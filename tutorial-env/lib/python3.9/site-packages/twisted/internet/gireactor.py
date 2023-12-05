# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module provides support for Twisted to interact with the glib
mainloop via GObject Introspection.

In order to use this support, simply do the following::

    from twisted.internet import gireactor
    gireactor.install()

If you wish to use a GApplication, register it with the reactor::

    from twisted.internet import reactor
    reactor.registerGApplication(app)

Then use twisted.internet APIs as usual.

On Python 3, pygobject v3.4 or later is required.
"""


import gi.pygtkcompat  # type: ignore[import]
from gi.repository import GLib  # type: ignore[import]

from twisted.internet import _glibbase
from twisted.internet.error import ReactorAlreadyRunning
from twisted.python import runtime

# We require a sufficiently new version of pygobject, so always exists:
_pygtkcompatPresent = True

# Newer version of gi, so we can try to initialize compatibility layer; if
# real pygtk was already imported we'll get ImportError at this point
# rather than segfault, so unconditional import is fine.
gi.pygtkcompat.enable()
# At this point importing gobject will get you gi version, and importing
# e.g. gtk will either fail in non-segfaulty way or use gi version if user
# does gi.pygtkcompat.enable_gtk(). So, no need to prevent imports of
# old school pygtk modules.
if getattr(GLib, "threads_init", None) is not None:
    GLib.threads_init()


class GIReactor(_glibbase.GlibReactorBase):
    """
    GObject-introspection event loop reactor.

    @ivar _gapplication: A C{Gio.Application} instance that was registered
        with C{registerGApplication}.
    """

    _POLL_DISCONNECTED = (
        GLib.IOCondition.HUP | GLib.IOCondition.ERR | GLib.IOCondition.NVAL
    )
    _POLL_IN = GLib.IOCondition.IN
    _POLL_OUT = GLib.IOCondition.OUT

    # glib's iochannel sources won't tell us about any events that we haven't
    # asked for, even if those events aren't sensible inputs to the poll()
    # call.
    INFLAGS = _POLL_IN | _POLL_DISCONNECTED
    OUTFLAGS = _POLL_OUT | _POLL_DISCONNECTED

    # By default no Application is registered:
    _gapplication = None

    def __init__(self, useGtk=False):
        _gtk = None
        if useGtk is True:
            from gi.repository import Gtk as _gtk

        _glibbase.GlibReactorBase.__init__(self, GLib, _gtk, useGtk=useGtk)

    def registerGApplication(self, app):
        """
        Register a C{Gio.Application} or C{Gtk.Application}, whose main loop
        will be used instead of the default one.

        We will C{hold} the application so it doesn't exit on its own. In
        versions of C{python-gi} 3.2 and later, we exit the event loop using
        the C{app.quit} method which overrides any holds. Older versions are
        not supported.
        """
        if self._gapplication is not None:
            raise RuntimeError("Can't register more than one application instance.")
        if self._started:
            raise ReactorAlreadyRunning(
                "Can't register application after reactor was started."
            )
        if not hasattr(app, "quit"):
            raise RuntimeError(
                "Application registration is not supported in"
                " versions of PyGObject prior to 3.2."
            )
        self._gapplication = app

        def run():
            app.hold()
            app.run(None)

        self._run = run

        self._crash = app.quit


class PortableGIReactor(_glibbase.PortableGlibReactorBase):
    """
    Portable GObject Introspection event loop reactor.
    """

    def __init__(self, useGtk=False):
        _gtk = None
        if useGtk is True:
            from gi.repository import Gtk as _gtk

        _glibbase.PortableGlibReactorBase.__init__(self, GLib, _gtk, useGtk=useGtk)

    def registerGApplication(self, app):
        """
        Register a C{Gio.Application} or C{Gtk.Application}, whose main loop
        will be used instead of the default one.
        """
        raise NotImplementedError("GApplication is not currently supported on Windows.")


def install(useGtk=False):
    """
    Configure the twisted mainloop to be run inside the glib mainloop.

    @param useGtk: should GTK+ rather than glib event loop be
        used (this will be slightly slower but does support GUI).
    """
    if runtime.platform.getType() == "posix":
        reactor = GIReactor(useGtk=useGtk)
    else:
        reactor = PortableGIReactor(useGtk=useGtk)

    from twisted.internet.main import installReactor

    installReactor(reactor)
    return reactor


__all__ = ["install"]
