# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Names: DNS server and client implementations.
"""

from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute

from twisted._version import version
__version__ = version.short()

deprecatedModuleAttribute(
    Version("Twisted", 16, 0, 0),
    "Use twisted.__version__ instead.",
    "twisted.names", "__version__")
