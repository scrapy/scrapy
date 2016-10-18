# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.main}.
"""

from __future__ import division, absolute_import

from twisted.trial import unittest
from twisted.internet.error import ReactorAlreadyInstalledError
from twisted.internet.main import installReactor

from twisted.internet.test.modulehelpers import NoReactor


class InstallReactorTests(unittest.SynchronousTestCase):
    """
    Tests for L{installReactor}.
    """

    def test_installReactor(self):
        """
        L{installReactor} installs a new reactor if none is present.
        """
        with NoReactor():
            newReactor = object()
            installReactor(newReactor)
            from twisted.internet import reactor
            self.assertIs(newReactor, reactor)


    def test_alreadyInstalled(self):
        """
        If a reactor is already installed, L{installReactor} raises
        L{ReactorAlreadyInstalledError}.
        """
        with NoReactor():
            installReactor(object())
            self.assertRaises(ReactorAlreadyInstalledError, installReactor,
                              object())


    def test_errorIsAnAssertionError(self):
        """
        For backwards compatibility, L{ReactorAlreadyInstalledError} is an
        L{AssertionError}.
        """
        self.assertTrue(issubclass(ReactorAlreadyInstalledError,
                        AssertionError))
