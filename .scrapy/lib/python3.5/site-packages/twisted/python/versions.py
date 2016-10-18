# -*- test-case-name: twisted.python.test.test_versions -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Versions for Python packages.

See L{Version}.
"""

from __future__ import division, absolute_import

import sys, os

from twisted.python.compat import cmp, comparable, nativeString

@comparable
class _inf(object):
    """
    An object that is bigger than all other objects.
    """
    def __cmp__(self, other):
        """
        @param other: Another object.
        @type other: any

        @return: 0 if other is inf, 1 otherwise.
        @rtype: C{int}
        """
        if other is _inf:
            return 0
        return 1

_inf = _inf()



class IncomparableVersions(TypeError):
    """
    Two versions could not be compared.
    """



@comparable
class Version(object):
    """
    An object that represents a three-part version number.

    If running from an svn checkout, include the revision number in
    the version string.
    """
    def __init__(self, package, major, minor, micro, prerelease=None):
        """
        @param package: Name of the package that this is a version of.
        @type package: C{str}
        @param major: The major version number.
        @type major: C{int}
        @param minor: The minor version number.
        @type minor: C{int}
        @param micro: The micro version number.
        @type micro: C{int}
        @param prerelease: The prerelease number.
        @type prerelease: C{int}
        """
        self.package = package
        self.major = major
        self.minor = minor
        self.micro = micro
        self.prerelease = prerelease


    def short(self):
        """
        Return a string in canonical short version format,
        <major>.<minor>.<micro>[+rSVNVer].
        """
        s = self.base()
        svnver = self._getSVNVersion()
        if svnver:
            s += '+r' + nativeString(svnver)
        return s


    def base(self):
        """
        Like L{short}, but without the +rSVNVer.
        """
        if self.prerelease is None:
            pre = ""
        else:
            pre = "pre%s" % (self.prerelease,)
        return '%d.%d.%d%s' % (self.major,
                               self.minor,
                               self.micro,
                               pre)


    def __repr__(self):
        svnver = self._formatSVNVersion()
        if svnver:
            svnver = '  #' + svnver
        if self.prerelease is None:
            prerelease = ""
        else:
            prerelease = ", prerelease=%r" % (self.prerelease,)
        return '%s(%r, %d, %d, %d%s)%s' % (
            self.__class__.__name__,
            self.package,
            self.major,
            self.minor,
            self.micro,
            prerelease,
            svnver)


    def __str__(self):
        return '[%s, version %s]' % (
            self.package,
            self.short())


    def __cmp__(self, other):
        """
        Compare two versions, considering major versions, minor versions, micro
        versions, then prereleases.

        A version with a prerelease is always less than a version without a
        prerelease. If both versions have prereleases, they will be included in
        the comparison.

        @param other: Another version.
        @type other: L{Version}

        @return: NotImplemented when the other object is not a Version, or one
            of -1, 0, or 1.

        @raise IncomparableVersions: when the package names of the versions
            differ.
        """
        if not isinstance(other, self.__class__):
            return NotImplemented
        if self.package != other.package:
            raise IncomparableVersions("%r != %r"
                                       % (self.package, other.package))

        if self.prerelease is None:
            prerelease = _inf
        else:
            prerelease = self.prerelease

        if other.prerelease is None:
            otherpre = _inf
        else:
            otherpre = other.prerelease

        x = cmp((self.major,
                    self.minor,
                    self.micro,
                    prerelease),
                   (other.major,
                    other.minor,
                    other.micro,
                    otherpre))
        return x


    def _parseSVNEntries_4(self, entriesFile):
        """
        Given a readable file object which represents a .svn/entries file in
        format version 4, return the revision as a string.  We do this by
        reading first XML element in the document that has a 'revision'
        attribute.
        """
        from xml.dom.minidom import parse
        doc = parse(entriesFile).documentElement
        for node in doc.childNodes:
            if hasattr(node, 'getAttribute'):
                rev = node.getAttribute('revision')
                if rev is not None:
                    return rev.encode('ascii')


    def _parseSVNEntries_8(self, entriesFile):
        """
        Given a readable file object which represents a .svn/entries file in
        format version 8, return the revision as a string.
        """
        entriesFile.readline()
        entriesFile.readline()
        entriesFile.readline()
        return entriesFile.readline().strip()


    # Add handlers for version 9 and 10 formats, which are the same as
    # version 8 as far as revision information is concerned.
    _parseSVNEntries_9 = _parseSVNEntries_8
    _parseSVNEntriesTenPlus = _parseSVNEntries_8


    def _getSVNVersion(self):
        """
        Figure out the SVN revision number based on the existence of
        <package>/.svn/entries, and its contents. This requires discovering the
        format version from the 'format' file and parsing the entries file
        accordingly.

        @return: None or string containing SVN Revision number.
        """
        mod = sys.modules.get(self.package)
        if mod:
            svn = os.path.join(os.path.dirname(mod.__file__), '.svn')
            if not os.path.exists(svn):
                # It's not an svn working copy
                return None

            formatFile = os.path.join(svn, 'format')
            if os.path.exists(formatFile):
                # It looks like a less-than-version-10 working copy.
                with open(formatFile, 'rb') as fObj:
                    format = fObj.read().strip()
                parser = getattr(self, '_parseSVNEntries_' + format.decode('ascii'), None)
            else:
                # It looks like a version-10-or-greater working copy, which
                # has version information in the entries file.
                parser = self._parseSVNEntriesTenPlus

            if parser is None:
                return b'Unknown'

            entriesFile = os.path.join(svn, 'entries')
            try:
                with open(entriesFile, 'rb') as entries:
                    return parser(entries)
            except:
                return b'Unknown'


    def _formatSVNVersion(self):
        ver = self._getSVNVersion()
        if ver is None:
            return ''
        return ' (SVN r%s)' % (ver,)



def getVersionString(version):
    """
    Get a friendly string for the given version object.

    @param version: A L{Version} object.
    @return: A string containing the package and short version number.
    """
    result = '%s %s' % (version.package, version.short())
    return result
