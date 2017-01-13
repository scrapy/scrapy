# -*- test-case-name: twisted.internet.test.test_default -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The most suitable default reactor for the current platform.

Depending on a specific application's needs, some other reactor may in
fact be better.
"""

from __future__ import division, absolute_import

__all__ = ["install"]

from twisted.python.runtime import platform


def _getInstallFunction(platform):
    """
    Return a function to install the reactor most suited for the given platform.

    @param platform: The platform for which to select a reactor.
    @type platform: L{twisted.python.runtime.Platform}

    @return: A zero-argument callable which will install the selected
        reactor.
    """
    # Linux: epoll(7) is the default, since it scales well.
    #
    # OS X: poll(2) is not exposed by Python because it doesn't support all
    # file descriptors (in particular, lack of PTY support is a problem) --
    # see <http://bugs.python.org/issue5154>. kqueue has the same restrictions
    # as poll(2) as far PTY support goes.
    #
    # Windows: IOCP should eventually be default, but still has some serious
    # bugs, e.g. <http://twistedmatrix.com/trac/ticket/4667>.
    #
    # We therefore choose epoll(7) on Linux, poll(2) on other non-OS X POSIX
    # platforms, and select(2) everywhere else.
    try:
        if platform.isLinux():
            try:
                from twisted.internet.epollreactor import install
            except ImportError:
                from twisted.internet.pollreactor import install
        elif platform.getType() == 'posix' and not platform.isMacOSX():
            from twisted.internet.pollreactor import install
        else:
            from twisted.internet.selectreactor import install
    except ImportError:
        from twisted.internet.selectreactor import install
    return install


install = _getInstallFunction(platform)
