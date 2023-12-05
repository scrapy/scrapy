# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Python: Utilities and Enhancements for Python.
"""


from .deprecate import deprecatedModuleAttribute

# Deprecating twisted.python.constants.
from .versions import Version

deprecatedModuleAttribute(
    Version("Twisted", 16, 5, 0),
    "Please use constantly from PyPI instead.",
    "twisted.python",
    "constants",
)


deprecatedModuleAttribute(
    Version("Twisted", 17, 5, 0),
    "Please use hyperlink from PyPI instead.",
    "twisted.python",
    "url",
)


del Version
del deprecatedModuleAttribute
