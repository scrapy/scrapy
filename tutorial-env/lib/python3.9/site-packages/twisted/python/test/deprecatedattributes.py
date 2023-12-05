# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A module that is deprecated, used by L{twisted.python.test.test_deprecate} for
testing purposes.
"""


from incremental import Version

from twisted.python.deprecate import deprecatedModuleAttribute

# Known module-level attributes.
DEPRECATED_ATTRIBUTE = 42
ANOTHER_ATTRIBUTE = "hello"


version = Version("Twisted", 8, 0, 0)
message = "Oh noes!"


deprecatedModuleAttribute(version, message, __name__, "DEPRECATED_ATTRIBUTE")
