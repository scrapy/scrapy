# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted's unit tests.
"""


from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.versions import Version
from twisted.test import proto_helpers

for obj in proto_helpers.__all__:
    deprecatedModuleAttribute(
        Version("Twisted", 19, 7, 0),
        f"Please use twisted.internet.testing.{obj} instead.",
        "twisted.test.proto_helpers",
        obj,
    )
