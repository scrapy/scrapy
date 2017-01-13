# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.service}.
"""

from __future__ import absolute_import, division

from zope.interface.verify import verifyObject

from twisted.persisted.sob import IPersistable
from twisted.application.service import Application, IProcess
from twisted.application.service import IService, IServiceCollection
from twisted.trial.unittest import TestCase



class ApplicationTests(TestCase):
    """
    Tests for L{twisted.application.service.Application}.
    """
    def test_applicationComponents(self):
        """
        Check L{twisted.application.service.Application} instantiation.
        """
        app = Application('app-name')

        self.assertTrue(verifyObject(IService, IService(app)))
        self.assertTrue(
            verifyObject(IServiceCollection, IServiceCollection(app)))
        self.assertTrue(verifyObject(IProcess, IProcess(app)))
        self.assertTrue(verifyObject(IPersistable, IPersistable(app)))
