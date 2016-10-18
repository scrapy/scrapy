# -*- test-case-name: twisted.web.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Web: HTTP clients and servers, plus tools for implementing them.

Contains a L{web server<twisted.web.server>} (including an
L{HTTP implementation<twisted.web.http>}, a
L{resource model<twisted.web.resource>}), and
a L{web client<twisted.web.client>}.
"""

from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute

from twisted._version import version
__version__ = version.short()

deprecatedModuleAttribute(
    Version("Twisted", 16, 0, 0),
    "Use twisted.__version__ instead.",
    "twisted.web", "__version__")
