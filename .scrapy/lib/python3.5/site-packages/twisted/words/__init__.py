# -*- test-case-name: twisted.words.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Words: Client and server implementations for IRC, XMPP, and other chat
services.
"""

from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute

from twisted._version import version
__version__ = version.short()

deprecatedModuleAttribute(
    Version("Twisted", 16, 0, 0),
    "Use twisted.__version__ instead.",
    "twisted.words", "__version__")
