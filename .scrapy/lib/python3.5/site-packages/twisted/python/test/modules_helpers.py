# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Facilities for helping test code which interacts with Python's module system
to load code.
"""

from __future__ import division, absolute_import

import sys

from twisted.python.filepath import FilePath


class TwistedModulesMixin:
    """
    A mixin for C{twisted.trial.unittest.SynchronousTestCase} providing useful
    methods for manipulating Python's module system.
    """

    def replaceSysPath(self, sysPath):
        """
        Replace sys.path, for the duration of the test, with the given value.
        """
        originalSysPath = sys.path[:]
        def cleanUpSysPath():
            sys.path[:] = originalSysPath
        self.addCleanup(cleanUpSysPath)
        sys.path[:] = sysPath


    def replaceSysModules(self, sysModules):
        """
        Replace sys.modules, for the duration of the test, with the given value.
        """
        originalSysModules = sys.modules.copy()
        def cleanUpSysModules():
            sys.modules.clear()
            sys.modules.update(originalSysModules)
        self.addCleanup(cleanUpSysModules)
        sys.modules.clear()
        sys.modules.update(sysModules)


    def pathEntryWithOnePackage(self, pkgname="test_package"):
        """
        Generate a L{FilePath} with one package, named C{pkgname}, on it, and
        return the L{FilePath} of the path entry.
        """
        entry = FilePath(self.mktemp())
        pkg = entry.child("test_package")
        pkg.makedirs()
        pkg.child("__init__.py").setContent(b"")
        return entry
