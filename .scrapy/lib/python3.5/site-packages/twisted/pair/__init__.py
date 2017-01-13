# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Pair: The framework of your ethernet.

Low-level networking transports and utilities.

See also twisted.protocols.ethernet, twisted.protocols.ip,
twisted.protocols.raw and twisted.protocols.rawudp.

Maintainer: Tommi Virtanen
"""

from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute

from twisted._version import version
__version__ = version.short()

deprecatedModuleAttribute(
    Version("Twisted", 16, 0, 0),
    "Use twisted.__version__ instead.",
    "twisted.pair", "__version__")
