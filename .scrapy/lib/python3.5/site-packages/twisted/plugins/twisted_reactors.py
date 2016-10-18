# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import, division

from twisted.application.reactors import Reactor
from twisted.python.compat import _PY3

default = Reactor(
    'default', 'twisted.internet.default',
    'A reasonable default: poll(2) if available, otherwise select(2).')

select = Reactor(
    'select', 'twisted.internet.selectreactor', 'select(2)-based reactor.')

poll = Reactor(
    'poll', 'twisted.internet.pollreactor', 'poll(2)-based reactor.')
epoll = Reactor(
    'epoll', 'twisted.internet.epollreactor', 'epoll(4)-based reactor.')

kqueue = Reactor(
    'kqueue', 'twisted.internet.kqreactor', 'kqueue(2)-based reactor.')

__all__ = [
    "default", "select", "poll", "epoll", "kqueue"
]

if not _PY3:
    wx = Reactor(
        'wx', 'twisted.internet.wxreactor', 'wxPython integration reactor.')
    gi = Reactor(
        'gi', 'twisted.internet.gireactor',
        'GObject Introspection integration reactor.')
    gtk3 = Reactor(
        'gtk3', 'twisted.internet.gtk3reactor', 'Gtk3 integration reactor.')
    gtk2 = Reactor(
        'gtk2', 'twisted.internet.gtk2reactor', 'Gtk2 integration reactor.')
    glib2 = Reactor(
        'glib2', 'twisted.internet.glib2reactor',
        'GLib2 event-loop integration reactor.')
    win32er = Reactor(
        'win32', 'twisted.internet.win32eventreactor',
        'Win32 WaitForMultipleObjects-based reactor.')
    cf = Reactor(
        'cf' , 'twisted.internet.cfreactor',
        'CoreFoundation integration reactor.')
    iocp = Reactor(
        'iocp', 'twisted.internet.iocpreactor',
        'Win32 IO Completion Ports-based reactor.')

    __all__.extend([
        "wx", "gi", "gtk2", "gtk3", "glib2", "glade", "win32er", "cf", "iocp"
    ])
