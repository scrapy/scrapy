# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for twisted.internet.glibbase.
"""


import sys

from twisted.internet._glibbase import ensureNotImported
from twisted.trial.unittest import TestCase


class EnsureNotImportedTests(TestCase):
    """
    L{ensureNotImported} protects against unwanted past and future imports.
    """

    def test_ensureWhenNotImported(self):
        """
        If the specified modules have never been imported, and import
        prevention is requested, L{ensureNotImported} makes sure they will not
        be imported in the future.
        """
        modules = {}
        self.patch(sys, "modules", modules)
        ensureNotImported(["m1", "m2"], "A message.", preventImports=["m1", "m2", "m3"])
        self.assertEqual(modules, {"m1": None, "m2": None, "m3": None})

    def test_ensureWhenNotImportedDontPrevent(self):
        """
        If the specified modules have never been imported, and import
        prevention is not requested, L{ensureNotImported} has no effect.
        """
        modules = {}
        self.patch(sys, "modules", modules)
        ensureNotImported(["m1", "m2"], "A message.")
        self.assertEqual(modules, {})

    def test_ensureWhenFailedToImport(self):
        """
        If the specified modules have been set to L{None} in C{sys.modules},
        L{ensureNotImported} does not complain.
        """
        modules = {"m2": None}
        self.patch(sys, "modules", modules)
        ensureNotImported(["m1", "m2"], "A message.", preventImports=["m1", "m2"])
        self.assertEqual(modules, {"m1": None, "m2": None})

    def test_ensureFailsWhenImported(self):
        """
        If one of the specified modules has been previously imported,
        L{ensureNotImported} raises an exception.
        """
        module = object()
        modules = {"m2": module}
        self.patch(sys, "modules", modules)
        e = self.assertRaises(
            ImportError,
            ensureNotImported,
            ["m1", "m2"],
            "A message.",
            preventImports=["m1", "m2"],
        )
        self.assertEqual(modules, {"m2": module})
        self.assertEqual(e.args, ("A message.",))


try:
    from twisted.internet import gireactor as _gireactor
except ImportError:
    gireactor = None
else:
    gireactor = _gireactor

missingGlibReactor = None
if gireactor is None:
    missingGlibReactor = "gi reactor not available"


class GlibReactorBaseTests(TestCase):
    """
    Tests for the private C{twisted.internet._glibbase.GlibReactorBase}
    done via the public C{twisted.internet.gireactor.PortableGIReactor}
    """

    skip = missingGlibReactor

    def test_simulate(self):
        """
        C{simulate} can be called without raising any errors when there are
        no delayed calls for the reactor and hence there is no defined sleep
        period.
        """
        sut = gireactor.PortableGIReactor(useGtk=False)
        # Double check that reactor has no sleep period.
        self.assertIs(None, sut.timeout())

        sut.simulate()
