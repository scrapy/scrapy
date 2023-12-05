# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Facilities for helping test code which interacts with Python's module system
to load code.
"""

import sys
from types import ModuleType
from typing import Iterable, List, Tuple

from twisted.python.filepath import FilePath


class TwistedModulesMixin:
    """
    A mixin for C{twisted.trial.unittest.SynchronousTestCase} providing useful
    methods for manipulating Python's module system.
    """

    def replaceSysPath(self, sysPath: List[str]) -> None:
        """
        Replace sys.path, for the duration of the test, with the given value.
        """
        originalSysPath = sys.path[:]

        def cleanUpSysPath() -> None:
            sys.path[:] = originalSysPath

        self.addCleanup(cleanUpSysPath)  # type: ignore[attr-defined]
        sys.path[:] = sysPath

    def replaceSysModules(self, sysModules: Iterable[Tuple[str, ModuleType]]) -> None:
        """
        Replace sys.modules, for the duration of the test, with the given value.
        """
        originalSysModules = sys.modules.copy()

        def cleanUpSysModules() -> None:
            sys.modules.clear()
            sys.modules.update(originalSysModules)

        self.addCleanup(cleanUpSysModules)  # type: ignore[attr-defined]
        sys.modules.clear()
        sys.modules.update(sysModules)

    def pathEntryWithOnePackage(self, pkgname: str = "test_package") -> FilePath:
        """
        Generate a L{FilePath} with one package, named C{pkgname}, on it, and
        return the L{FilePath} of the path entry.
        """
        entry = FilePath(self.mktemp())  # type: ignore[attr-defined]
        pkg = entry.child("test_package")
        pkg.makedirs()
        pkg.child("__init__.py").setContent(b"")
        return entry
