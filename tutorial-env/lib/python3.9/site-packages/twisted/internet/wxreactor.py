# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module provides wxPython event loop support for Twisted.

In order to use this support, simply do the following::

    |  from twisted.internet import wxreactor
    |  wxreactor.install()

Then, when your root wxApp has been created::

    | from twisted.internet import reactor
    | reactor.registerWxApp(yourApp)
    | reactor.run()

Then use twisted.internet APIs as usual. Stop the event loop using
reactor.stop(), not yourApp.ExitMainLoop().

IMPORTANT: tests will fail when run under this reactor. This is
expected and probably does not reflect on the reactor's ability to run
real applications.
"""

from queue import Empty, Queue

try:
    from wx import (  # type: ignore[import]
        CallAfter as wxCallAfter,
        PySimpleApp as wxPySimpleApp,
        Timer as wxTimer,
    )
except ImportError:
    # older version of wxPython:
    from wxPython.wx import wxPySimpleApp, wxCallAfter, wxTimer  # type: ignore[import]

from twisted.internet import _threadedselect
from twisted.python import log, runtime


class ProcessEventsTimer(wxTimer):
    """
    Timer that tells wx to process pending events.

    This is necessary on macOS, probably due to a bug in wx, if we want
    wxCallAfters to be handled when modal dialogs, menus, etc.  are open.
    """

    def __init__(self, wxapp):
        wxTimer.__init__(self)
        self.wxapp = wxapp

    def Notify(self):
        """
        Called repeatedly by wx event loop.
        """
        self.wxapp.ProcessPendingEvents()


class WxReactor(_threadedselect.ThreadedSelectReactor):
    """
    wxPython reactor.

    wxPython drives the event loop, select() runs in a thread.
    """

    _stopping = False

    def registerWxApp(self, wxapp):
        """
        Register wxApp instance with the reactor.
        """
        self.wxapp = wxapp

    def _installSignalHandlersAgain(self):
        """
        wx sometimes removes our own signal handlers, so re-add them.
        """
        try:
            # make _handleSignals happy:
            import signal

            signal.signal(signal.SIGINT, signal.default_int_handler)
        except ImportError:
            return
        self._handleSignals()

    def stop(self):
        """
        Stop the reactor.
        """
        if self._stopping:
            return
        self._stopping = True
        _threadedselect.ThreadedSelectReactor.stop(self)

    def _runInMainThread(self, f):
        """
        Schedule function to run in main wx/Twisted thread.

        Called by the select() thread.
        """
        if hasattr(self, "wxapp"):
            wxCallAfter(f)
        else:
            # wx shutdown but twisted hasn't
            self._postQueue.put(f)

    def _stopWx(self):
        """
        Stop the wx event loop if it hasn't already been stopped.

        Called during Twisted event loop shutdown.
        """
        if hasattr(self, "wxapp"):
            self.wxapp.ExitMainLoop()

    def run(self, installSignalHandlers=True):
        """
        Start the reactor.
        """
        self._postQueue = Queue()
        if not hasattr(self, "wxapp"):
            log.msg(
                "registerWxApp() was not called on reactor, "
                "registering my own wxApp instance."
            )
            self.registerWxApp(wxPySimpleApp())

        # start select() thread:
        self.interleave(
            self._runInMainThread, installSignalHandlers=installSignalHandlers
        )
        if installSignalHandlers:
            self.callLater(0, self._installSignalHandlersAgain)

        # add cleanup events:
        self.addSystemEventTrigger("after", "shutdown", self._stopWx)
        self.addSystemEventTrigger(
            "after", "shutdown", lambda: self._postQueue.put(None)
        )

        # On macOS, work around wx bug by starting timer to ensure
        # wxCallAfter calls are always processed. We don't wake up as
        # often as we could since that uses too much CPU.
        if runtime.platform.isMacOSX():
            t = ProcessEventsTimer(self.wxapp)
            t.Start(2)  # wake up every 2ms

        self.wxapp.MainLoop()
        wxapp = self.wxapp
        del self.wxapp

        if not self._stopping:
            # wx event loop exited without reactor.stop() being
            # called.  At this point events from select() thread will
            # be added to _postQueue, but some may still be waiting
            # unprocessed in wx, thus the ProcessPendingEvents()
            # below.
            self.stop()
            wxapp.ProcessPendingEvents()  # deal with any queued wxCallAfters
            while 1:
                try:
                    f = self._postQueue.get(timeout=0.01)
                except Empty:
                    continue
                else:
                    if f is None:
                        break
                    try:
                        f()
                    except BaseException:
                        log.err()


def install():
    """
    Configure the twisted mainloop to be run inside the wxPython mainloop.
    """
    reactor = WxReactor()
    from twisted.internet.main import installReactor

    installReactor(reactor)
    return reactor


__all__ = ["install"]
