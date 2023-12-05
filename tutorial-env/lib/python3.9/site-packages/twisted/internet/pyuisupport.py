# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
This module integrates PyUI with twisted.internet's mainloop.

Maintainer: Jp Calderone

See doc/examples/pyuidemo.py for example usage.
"""

# System imports
import pyui  # type: ignore[import]


def _guiUpdate(reactor, delay):
    pyui.draw()
    if pyui.update() == 0:
        pyui.quit()
        reactor.stop()
    else:
        reactor.callLater(delay, _guiUpdate, reactor, delay)


def install(ms=10, reactor=None, args=(), kw={}):
    """
    Schedule PyUI's display to be updated approximately every C{ms}
    milliseconds, and initialize PyUI with the specified arguments.
    """
    d = pyui.init(*args, **kw)

    if reactor is None:
        from twisted.internet import reactor
    _guiUpdate(reactor, ms / 1000.0)
    return d


__all__ = ["install"]
