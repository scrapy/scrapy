# -*- test-case-name: twisted.test.test_stdio -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Standard input/out/err support.

This module exposes one name, StandardIO, which is a factory that takes an
IProtocol provider as an argument.  It connects that protocol to standard input
and output on the current process.

It should work on any UNIX and also on Win32 (with some caveats: due to
platform limitations, it will perform very poorly on Win32).

Future Plans::

    support for stderr, perhaps
    Rewrite to use the reactor instead of an ad-hoc mechanism for connecting
        protocols to transport.


Maintainer: James Y Knight
"""


from twisted.python.runtime import platform

if platform.isWindows():
    from twisted.internet._win32stdio import StandardIO, Win32PipeAddress as PipeAddress

else:
    from twisted.internet._posixstdio import (  # type: ignore[misc]
        PipeAddress,
        StandardIO,
    )

__all__ = ["StandardIO", "PipeAddress"]
