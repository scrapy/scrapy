# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Chat protocols.
"""

from twisted.python.versions import Version
from twisted.python.deprecate import deprecatedModuleAttribute


deprecatedModuleAttribute(
    Version("Twisted", 16, 2, 0),
    "There is no replacement for this module.",
    "twisted.words.protocols",
    "oscar")
