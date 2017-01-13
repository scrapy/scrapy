# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the data directory support.
"""

from __future__ import division, absolute_import

try:
    from twisted.python import _appdirs
except ImportError:
    _appdirs = None

from twisted.trial import unittest


class AppdirsTests(unittest.TestCase):
    """
    Tests for L{_appdirs}.
    """
    if not _appdirs:
        skip = "appdirs package not installed"


    def test_moduleName(self):
        """
        Calling L{appdirs.getDataDirectory} will return a user data directory
        in the system convention, with the module of the caller as the
        subdirectory.
        """
        res = _appdirs.getDataDirectory()
        self.assertTrue(res.endswith("twisted.python.test.test_appdirs"))


    def test_manual(self):
        """
        Calling L{appdirs.getDataDirectory} with a C{moduleName} argument will
        make a data directory with that name instead.
        """
        res = _appdirs.getDataDirectory("foo.bar.baz")
        self.assertTrue(res.endswith("foo.bar.baz"))
