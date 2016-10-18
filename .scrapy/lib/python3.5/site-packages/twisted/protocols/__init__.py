# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Protocols: A collection of internet protocol implementations.
"""

# Deprecating twisted.protocols.gps and twisted.protocols.mice.
from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute

deprecatedModuleAttribute(
    Version("Twisted", 15, 2, 0),
    "Use twisted.positioning instead.",
    "twisted.protocols", "gps")

deprecatedModuleAttribute(
    Version("Twisted", 16, 0, 0),
    "There is no replacement for this module.",
    "twisted.protocols", "mice")
