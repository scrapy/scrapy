# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.application.reactors import Reactor

__all__ = []

default = Reactor(
    "default",
    "twisted.internet.default",
    "A reasonable default: poll(2) if available, otherwise select(2).",
)
__all__.append("default")

select = Reactor("select", "twisted.internet.selectreactor", "select(2) based reactor.")
__all__.append("select")

poll = Reactor("poll", "twisted.internet.pollreactor", "poll(2) based reactor.")
__all__.append("poll")

epoll = Reactor("epoll", "twisted.internet.epollreactor", "epoll(4) based reactor.")
__all__.append("epoll")

kqueue = Reactor("kqueue", "twisted.internet.kqreactor", "kqueue(2) based reactor.")
__all__.append("kqueue")

cf = Reactor("cf", "twisted.internet.cfreactor", "CoreFoundation based reactor.")
__all__.append("cf")

asyncio = Reactor("asyncio", "twisted.internet.asyncioreactor", "asyncio based reactor")
__all__.append("asyncio")

wx = Reactor("wx", "twisted.internet.wxreactor", "wxPython based reactor.")
__all__.append("wx")

gi = Reactor("gi", "twisted.internet.gireactor", "GObject Introspection based reactor.")
__all__.append("gi")

gtk3 = Reactor("gtk3", "twisted.internet.gtk3reactor", "Gtk3 based reactor.")
__all__.append("gtk3")

gtk2 = Reactor("gtk2", "twisted.internet.gtk2reactor", "Gtk2 based reactor.")
__all__.append("gtk2")

glib2 = Reactor("glib2", "twisted.internet.glib2reactor", "GLib2 based reactor.")
__all__.append("glib2")

win32er = Reactor(
    "win32",
    "twisted.internet.win32eventreactor",
    "Win32 WaitForMultipleObjects based reactor.",
)
__all__.append("win32er")

iocp = Reactor(
    "iocp", "twisted.internet.iocpreactor", "Win32 IO Completion Ports based reactor."
)
__all__.append("iocp")
