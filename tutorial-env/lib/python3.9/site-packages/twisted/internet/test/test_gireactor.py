# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
GI/GTK3 reactor tests.
"""


import sys
from unittest import skipIf

try:
    from gi.repository import Gio  # type: ignore[import]

    from twisted.internet import gireactor as _gireactor
except ImportError:
    gireactor = None
    gtk3reactor = None
else:
    gireactor = _gireactor
    # gtk3reactor may be unavailable even if gireactor is available; in
    # particular in pygobject 3.4/gtk 3.6, when no X11 DISPLAY is found.
    try:
        from twisted.internet import gtk3reactor as _gtk3reactor
    except ImportError:
        gtk3reactor = None
    else:
        gtk3reactor = _gtk3reactor
        from gi.repository import Gtk

from twisted.internet.error import ReactorAlreadyRunning
from twisted.internet.test.reactormixins import ReactorBuilder
from twisted.trial.unittest import SkipTest, TestCase

# Skip all tests if gi is unavailable:
if gireactor is None:
    skip = "gtk3/gi not importable"


class GApplicationRegistrationTests(ReactorBuilder, TestCase):
    """
    GtkApplication and GApplication are supported by
    L{twisted.internet.gtk3reactor} and L{twisted.internet.gireactor}.

    We inherit from L{ReactorBuilder} in order to use some of its
    reactor-running infrastructure, but don't need its test-creation
    functionality.
    """

    def runReactor(self, app, reactor):
        """
        Register the app, run the reactor, make sure app was activated, and
        that reactor was running, and that reactor can be stopped.
        """
        if not hasattr(app, "quit"):
            raise SkipTest("Version of PyGObject is too old.")

        result = []

        def stop():
            result.append("stopped")
            reactor.stop()

        def activate(widget):
            result.append("activated")
            reactor.callLater(0, stop)

        app.connect("activate", activate)

        # We want reactor.stop() to *always* stop the event loop, even if
        # someone has called hold() on the application and never done the
        # corresponding release() -- for more details see
        # http://developer.gnome.org/gio/unstable/GApplication.html.
        app.hold()

        reactor.registerGApplication(app)
        ReactorBuilder.runReactor(self, reactor)
        self.assertEqual(result, ["activated", "stopped"])

    def test_gApplicationActivate(self):
        """
        L{Gio.Application} instances can be registered with a gireactor.
        """
        reactor = gireactor.GIReactor(useGtk=False)
        self.addCleanup(self.unbuildReactor, reactor)
        app = Gio.Application(
            application_id="com.twistedmatrix.trial.gireactor",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

        self.runReactor(app, reactor)

    @skipIf(
        gtk3reactor is None,
        "Gtk unavailable (may require running with X11 DISPLAY env set)",
    )
    def test_gtkApplicationActivate(self):
        """
        L{Gtk.Application} instances can be registered with a gtk3reactor.
        """
        reactor = gtk3reactor.Gtk3Reactor()
        self.addCleanup(self.unbuildReactor, reactor)
        app = Gtk.Application(
            application_id="com.twistedmatrix.trial.gtk3reactor",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

        self.runReactor(app, reactor)

    def test_portable(self):
        """
        L{gireactor.PortableGIReactor} doesn't support application
        registration at this time.
        """
        reactor = gireactor.PortableGIReactor()
        self.addCleanup(self.unbuildReactor, reactor)
        app = Gio.Application(
            application_id="com.twistedmatrix.trial.gireactor",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.assertRaises(NotImplementedError, reactor.registerGApplication, app)

    def test_noQuit(self):
        """
        Older versions of PyGObject lack C{Application.quit}, and so won't
        allow registration.
        """
        reactor = gireactor.GIReactor(useGtk=False)
        self.addCleanup(self.unbuildReactor, reactor)
        # An app with no "quit" method:
        app = object()
        exc = self.assertRaises(RuntimeError, reactor.registerGApplication, app)
        self.assertTrue(exc.args[0].startswith("Application registration is not"))

    def test_cantRegisterAfterRun(self):
        """
        It is not possible to register a C{Application} after the reactor has
        already started.
        """
        reactor = gireactor.GIReactor(useGtk=False)
        self.addCleanup(self.unbuildReactor, reactor)
        app = Gio.Application(
            application_id="com.twistedmatrix.trial.gireactor",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

        def tryRegister():
            exc = self.assertRaises(
                ReactorAlreadyRunning, reactor.registerGApplication, app
            )
            self.assertEqual(
                exc.args[0], "Can't register application after reactor was started."
            )
            reactor.stop()

        reactor.callLater(0, tryRegister)
        ReactorBuilder.runReactor(self, reactor)

    def test_cantRegisterTwice(self):
        """
        It is not possible to register more than one C{Application}.
        """
        reactor = gireactor.GIReactor(useGtk=False)
        self.addCleanup(self.unbuildReactor, reactor)
        app = Gio.Application(
            application_id="com.twistedmatrix.trial.gireactor",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        reactor.registerGApplication(app)
        app2 = Gio.Application(
            application_id="com.twistedmatrix.trial.gireactor2",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        exc = self.assertRaises(RuntimeError, reactor.registerGApplication, app2)
        self.assertEqual(
            exc.args[0], "Can't register more than one application instance."
        )


class PygtkCompatibilityTests(TestCase):
    """
    pygtk imports are either prevented, or a compatibility layer is used if
    possible.
    """

    def test_compatibilityLayer(self):
        """
        If compatibility layer is present, importing gobject uses
        the gi compatibility layer.
        """
        if "gi.pygtkcompat" not in sys.modules:
            raise SkipTest("This version of gi doesn't include pygtkcompat.")
        import gobject  # type: ignore[import]

        self.assertTrue(gobject.__name__.startswith("gi."))
