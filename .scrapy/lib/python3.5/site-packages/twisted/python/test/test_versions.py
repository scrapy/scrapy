# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.versions}.
"""

from __future__ import division, absolute_import

import sys
import operator
from io import BytesIO

from twisted.python.versions import getVersionString, IncomparableVersions
from twisted.python.versions import Version, _inf
from twisted.python.filepath import FilePath

from twisted.trial.unittest import SynchronousTestCase as TestCase


VERSION_4_ENTRIES = b"""\
<?xml version="1.0" encoding="utf-8"?>
<wc-entries
   xmlns="svn:">
<entry
   committed-rev="18210"
   name=""
   committed-date="2006-09-21T04:43:09.542953Z"
   url="svn+ssh://svn.twistedmatrix.com/svn/Twisted/trunk/twisted"
   last-author="exarkun"
   kind="dir"
   uuid="bbbe8e31-12d6-0310-92fd-ac37d47ddeeb"
   repos="svn+ssh://svn.twistedmatrix.com/svn/Twisted"
   revision="18211"/>
</wc-entries>
"""



VERSION_8_ENTRIES = b"""\
8

dir
22715
svn+ssh://svn.twistedmatrix.com/svn/Twisted/trunk
"""


VERSION_9_ENTRIES = b"""\
9

dir
22715
svn+ssh://svn.twistedmatrix.com/svn/Twisted/trunk
"""


VERSION_10_ENTRIES = b"""\
10

dir
22715
svn+ssh://svn.twistedmatrix.com/svn/Twisted/trunk
"""


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
        self.assertRaises(IncomparableVersions,
                          operator.eq,
                          Version("dummy", 1, 0, 0),
                          Version("dumym", 1, 0, 0))


    def test_notImplementedComparisons(self):
        """
        Comparing a L{Version} to some other object type results in
        C{NotImplemented}.
        """
        va = Version("dummy", 1, 0, 0)
        vb = ("dummy", 1, 0, 0) # a tuple is not a Version object
        self.assertEqual(va.__cmp__(vb), NotImplemented)


    def test_repr(self):
        """
        Calling C{repr} on a version returns a human-readable string
        representation of the version.
        """
        self.assertEqual(repr(Version("dummy", 1, 2, 3)),
                          "Version('dummy', 1, 2, 3)")


    def test_reprWithPrerelease(self):
        """
        Calling C{repr} on a version with a prerelease returns a human-readable
        string representation of the version including the prerelease.
        """
        self.assertEqual(repr(Version("dummy", 1, 2, 3, prerelease=4)),
                          "Version('dummy', 1, 2, 3, prerelease=4)")


    def test_str(self):
        """
        Calling C{str} on a version returns a human-readable string
        representation of the version.
        """
        self.assertEqual(str(Version("dummy", 1, 2, 3)),
                          "[dummy, version 1.2.3]")


    def test_strWithPrerelease(self):
        """
        Calling C{str} on a version with a prerelease includes the prerelease.
        """
        self.assertEqual(str(Version("dummy", 1, 0, 0, prerelease=1)),
                          "[dummy, version 1.0.0pre1]")


    def testShort(self):
        self.assertEqual(Version('dummy', 1, 2, 3).short(), '1.2.3')


    def test_goodSVNEntries_4(self):
        """
        Version should be able to parse an SVN format 4 entries file.
        """
        version = Version("dummy", 1, 0, 0)
        self.assertEqual(
            version._parseSVNEntries_4(BytesIO(VERSION_4_ENTRIES)), b'18211')


    def test_goodSVNEntries_8(self):
        """
        Version should be able to parse an SVN format 8 entries file.
        """
        version = Version("dummy", 1, 0, 0)
        self.assertEqual(
            version._parseSVNEntries_8(BytesIO(VERSION_8_ENTRIES)), b'22715')


    def test_goodSVNEntries_9(self):
        """
        Version should be able to parse an SVN format 9 entries file.
        """
        version = Version("dummy", 1, 0, 0)
        self.assertEqual(
            version._parseSVNEntries_9(BytesIO(VERSION_9_ENTRIES)), b'22715')


    def test_goodSVNEntriesTenPlus(self):
        """
        Version should be able to parse an SVN format 10 entries file.
        """
        version = Version("dummy", 1, 0, 0)
        self.assertEqual(
            version._parseSVNEntriesTenPlus(BytesIO(VERSION_10_ENTRIES)), b'22715')


    def test_getVersionString(self):
        """
        L{getVersionString} returns a string with the package name and the
        short version number.
        """
        self.assertEqual(
            'Twisted 8.0.0', getVersionString(Version('Twisted', 8, 0, 0)))


    def test_getVersionStringWithPrerelease(self):
        """
        L{getVersionString} includes the prerelease, if any.
        """
        self.assertEqual(
            getVersionString(Version("whatever", 8, 0, 0, prerelease=1)),
            "whatever 8.0.0pre1")


    def test_base(self):
        """
        The L{base} method returns a very simple representation of the version.
        """
        self.assertEqual(Version("foo", 1, 0, 0).base(), "1.0.0")


    def test_baseWithPrerelease(self):
        """
        The base version includes 'preX' for versions with prereleases.
        """
        self.assertEqual(Version("foo", 1, 0, 0, prerelease=8).base(),
                          "1.0.0pre8")



class FormatDiscoveryTests(TestCase):
    """
    Tests which discover the parsing method based on the imported module name.
    """
    def mktemp(self):
        return TestCase.mktemp(self).encode("utf-8")


    def setUp(self):
        """
        Create a temporary directory with a package structure in it.
        """
        self.entry = FilePath(self.mktemp())
        self.preTestModules = sys.modules.copy()
        sys.path.append(self.entry.path.decode('utf-8'))
        pkg = self.entry.child(b"twisted_python_versions_package")
        pkg.makedirs()
        pkg.child(b"__init__.py").setContent(
            b"from twisted.python.versions import Version\n"
            b"version = Version('twisted_python_versions_package', 1, 0, 0)\n")
        self.svnEntries = pkg.child(b".svn")
        self.svnEntries.makedirs()


    def tearDown(self):
        """
        Remove the imported modules and sys.path modifications.
        """
        sys.modules.clear()
        sys.modules.update(self.preTestModules)
        sys.path.remove(self.entry.path.decode('utf-8'))


    def checkSVNFormat(self, formatVersion, entriesText, expectedRevision):
        """
        Check for the given revision being detected after setting the SVN
        entries text and format version of the test directory structure.
        """
        self.svnEntries.child(b"format").setContent(formatVersion + b"\n")
        self.svnEntries.child(b"entries").setContent(entriesText)
        self.assertEqual(self.getVersion()._getSVNVersion(), expectedRevision)


    def getVersion(self):
        """
        Import and retrieve the Version object from our dynamically created
        package.
        """
        import twisted_python_versions_package
        return twisted_python_versions_package.version


    def test_detectVersion4(self):
        """
        Verify that version 4 format file will be properly detected and parsed.
        """
        self.checkSVNFormat(b"4", VERSION_4_ENTRIES, b'18211')


    def test_detectVersion8(self):
        """
        Verify that version 8 format files will be properly detected and
        parsed.
        """
        self.checkSVNFormat(b"8", VERSION_8_ENTRIES, b'22715')


    def test_detectVersion9(self):
        """
        Verify that version 9 format files will be properly detected and
        parsed.
        """
        self.checkSVNFormat(b"9", VERSION_9_ENTRIES, b'22715')


    def test_unparseableEntries(self):
        """
        Verify that the result is C{b"Unknown"} for an apparently supported
        version for which parsing of the entries file fails.
        """
        self.checkSVNFormat(b"4", b"some unsupported stuff", b"Unknown")


    def test_detectVersion10(self):
        """
        Verify that version 10 format files will be properly detected and
        parsed.

        Differing from previous formats, the version 10 format lacks a
        I{format} file and B{only} has the version information on the first
        line of the I{entries} file.
        """
        self.svnEntries.child(b"entries").setContent(VERSION_10_ENTRIES)
        self.assertEqual(self.getVersion()._getSVNVersion(), b'22715')


    def test_detectUnknownVersion(self):
        """
        Verify that a new version of SVN will result in the revision 'Unknown'.
        """
        self.checkSVNFormat(b"some-random-new-version", b"ooga booga!", b'Unknown')


    def test_getVersionStringWithRevision(self):
        """
        L{getVersionString} includes the discovered revision number.
        """
        self.svnEntries.child(b"format").setContent(b"9\n")
        self.svnEntries.child(b"entries").setContent(VERSION_10_ENTRIES)
        version = getVersionString(self.getVersion())
        self.assertEqual(
            "twisted_python_versions_package 1.0.0+r22715",
            version)
        self.assertIsInstance(version, type(""))
