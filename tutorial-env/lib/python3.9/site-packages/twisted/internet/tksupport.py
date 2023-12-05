# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
This module integrates Tkinter with twisted.internet's mainloop.

Maintainer: Itamar Shtull-Trauring

To use, do::

    | tksupport.install(rootWidget)

and then run your reactor as usual - do *not* call Tk's mainloop(),
use Twisted's regular mechanism for running the event loop.

Likewise, to stop your program you will need to stop Twisted's
event loop. For example, if you want closing your root widget to
stop Twisted::

    | root.protocol('WM_DELETE_WINDOW', reactor.stop)

When using Aqua Tcl/Tk on macOS the standard Quit menu item in
your application might become unresponsive without the additional
fix::

    | root.createcommand("::tk::mac::Quit", reactor.stop)

@see: U{Tcl/TkAqua FAQ for more info<http://wiki.tcl.tk/12987>}
"""

import tkinter.messagebox as tkMessageBox
import tkinter.simpledialog as tkSimpleDialog

from twisted.internet import task

_task = None


def install(widget, ms=10, reactor=None):
    """Install a Tkinter.Tk() object into the reactor."""
    installTkFunctions()
    global _task
    _task = task.LoopingCall(widget.update)
    _task.start(ms / 1000.0, False)


def uninstall():
    """Remove the root Tk widget from the reactor.

    Call this before destroy()ing the root widget.
    """
    global _task
    _task.stop()
    _task = None


def installTkFunctions():
    import twisted.python.util

    twisted.python.util.getPassword = getPassword


def getPassword(prompt="", confirm=0):
    while 1:
        try1 = tkSimpleDialog.askstring("Password Dialog", prompt, show="*")
        if not confirm:
            return try1
        try2 = tkSimpleDialog.askstring("Password Dialog", "Confirm Password", show="*")
        if try1 == try2:
            return try1
        else:
            tkMessageBox.showerror(
                "Password Mismatch", "Passwords did not match, starting over"
            )


__all__ = ["install", "uninstall"]
