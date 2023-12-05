# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.versions}.
"""


import operator

from incremental import _inf

from twisted.python.versions import IncomparableVersions, Version, getVersionString
from twisted.trial.unittest import SynchronousTestCase as TestCase


class VersionsTests(TestCase):
    def test_versionComparison(self):
        """
        Versions can be compared for equality and order.
        """
        va = Version("dummy", 1, 0, 0)
        vb = Version("dummy", 0, 1, 0)
        self.assertTrue(va > vb)
        self.assertTrue(vb < va)
        self.assertTrue(va >= vb)
        self.assertTrue(vb <= va)
        self.assertTrue(va != vb)
        self.assertTrue(vb == Version("dummy", 0, 1, 0))
        self.assertTrue(vb == vb)

    def test_versionComparisonCaseInsensitive(self):
        """
        Version packages are compared case insensitively.
        """
        va = Version("twisted", 1, 0, 0)
        vb = Version("Twisted", 0, 1, 0)
        self.assertTrue(va > vb)
        self.assertTrue(vb < va)
        self.assertTrue(va >= vb)
        self.assertTrue(vb <= va)
        self.assertTrue(va != vb)
        self.assertTrue(vb == Version("twisted", 0, 1, 0))
        self.assertTrue(vb == Version("TWISted", 0, 1, 0))
        self.assertTrue(vb == vb)

    def test_comparingPrereleasesWithReleases(self):
        """
        Prereleases are always less than versions without prereleases.
        """
        va = Version("whatever", 1, 0, 0, prerelease=1)
        vb = Version("whatever", 1, 0, 0)
        self.assertTrue(va < vb)
        self.assertFalse(va > vb)
        self.assertNotEqual(vb, va)

    def test_comparingPrereleases(self):
        """
        The value specified as the prerelease is used in version comparisons.
        """
        va = Version("whatever", 1, 0, 0, prerelease=1)
        vb = Version("whatever", 1, 0, 0, prerelease=2)
        self.assertTrue(va < vb)
        self.assertTrue(vb > va)
        self.assertTrue(va <= vb)
        self.assertTrue(vb >= va)
        self.assertTrue(va != vb)
        self.assertTrue(vb == Version("whatever", 1, 0, 0, prerelease=2))
        self.assertTrue(va == va)

    def test_infComparison(self):
        """
        L{_inf} is equal to L{_inf}.

        This is a regression test.
        """
        self.assertEqual(_inf, _inf)

    def test_disallowBuggyComparisons(self):
        """
        The package names of the Version objects need to be the same,
        """
        self.assertRaises(
            IncomparableVersions,
            operator.eq,
            Version("dummy", 1, 0, 0),
            Version("dumym", 1, 0, 0),
        )

    def test_notImplementedComparisons(self):
        """
        Comparing a L{Version} to some other object type results in
        C{NotImplemented}.
        """
        va = Version("dummy", 1, 0, 0)
        vb = ("dummy", 1, 0, 0)  # a tuple is not a Version object
        self.assertEqual(va.__cmp__(vb), NotImplemented)  # type: ignore[operator]

    def test_repr(self):
        """
        Calling C{repr} on a version returns a human-readable string
        representation of the version.
        """
        self.assertEqual(repr(Version("dummy", 1, 2, 3)), "Version('dummy', 1, 2, 3)")

    def test_reprWithPrerelease(self):
        """
        Calling C{repr} on a version with a prerelease returns a human-readable
        string representation of the version including the prerelease.
        """
        self.assertEqual(
            repr(Version("dummy", 1, 2, 3, prerelease=4)),
            "Version('dummy', 1, 2, 3, release_candidate=4)",
        )

    def test_str(self):
        """
        Calling C{str} on a version returns a human-readable string
        representation of the version.
        """
        self.assertEqual(str(Version("dummy", 1, 2, 3)), "[dummy, version 1.2.3]")

    def test_strWithPrerelease(self):
        """
        Calling C{str} on a version with a prerelease includes the prerelease.
        """
        self.assertEqual(
            str(Version("dummy", 1, 0, 0, prerelease=1)), "[dummy, version 1.0.0.rc1]"
        )

    def testShort(self):
        self.assertEqual(Version("dummy", 1, 2, 3).short(), "1.2.3")

    def test_getVersionString(self):
        """
        L{getVersionString} returns a string with the package name and the
        short version number.
        """
        self.assertEqual("Twisted 8.0.0", getVersionString(Version("Twisted", 8, 0, 0)))

    def test_getVersionStringWithPrerelease(self):
        """
        L{getVersionString} includes the prerelease, if any.
        """
        self.assertEqual(
            getVersionString(Version("whatever", 8, 0, 0, prerelease=1)),
            "whatever 8.0.0.rc1",
        )

    def test_base(self):
        """
        The L{base} method returns a very simple representation of the version.
        """
        self.assertEqual(Version("foo", 1, 0, 0).base(), "1.0.0")

    def test_baseWithPrerelease(self):
        """
        The base version includes 'preX' for versions with prereleases.
        """
        self.assertEqual(Version("foo", 1, 0, 0, prerelease=8).base(), "1.0.0.rc8")
