# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases covering L{twisted.python.filepath}.
"""


import errno
import os
import pickle
import stat
import time
from pprint import pformat
from unittest import skipIf

from zope.interface.verify import verifyObject

from twisted.python import filepath
from twisted.python.runtime import platform
from twisted.python.win32 import ERROR_DIRECTORY
from twisted.trial.unittest import SynchronousTestCase as TestCase

symlinkSkip = not platform._supportsSymlinks()


class BytesTestCase(TestCase):
    """
    Override default method implementations to support byte paths.
    """

    def mktemp(self):
        """
        Return a temporary path, encoded as bytes.
        """
        return TestCase.mktemp(self).encode("utf-8")


class AbstractFilePathTests(BytesTestCase):
    """
    Tests for L{IFilePath} implementations.
    """

    f1content = b"file 1"
    f2content = b"file 2"

    def _mkpath(self, *p):
        x = os.path.abspath(os.path.join(self.cmn, *p))
        self.all.append(x)
        return x

    def subdir(self, *dirname):
        os.mkdir(self._mkpath(*dirname))

    def subfile(self, *dirname):
        return open(self._mkpath(*dirname), "wb")

    def setUp(self):
        self.now = time.time()
        cmn = self.cmn = os.path.abspath(self.mktemp())
        self.all = [cmn]
        os.mkdir(cmn)
        self.subdir(b"sub1")
        with self.subfile(b"file1") as f:
            f.write(self.f1content)
        with self.subfile(b"sub1", b"file2") as f:
            f.write(self.f2content)
        self.subdir(b"sub3")
        self.subfile(b"sub3", b"file3.ext1").close()
        self.subfile(b"sub3", b"file3.ext2").close()
        self.subfile(b"sub3", b"file3.ext3").close()
        self.path = filepath.FilePath(cmn)
        self.root = filepath.FilePath(b"/")

    def test_verifyObject(self):
        """
        Instances of the path type being tested provide L{IFilePath}.
        """
        self.assertTrue(verifyObject(filepath.IFilePath, self.path))

    def test_segmentsFromPositive(self):
        """
        Verify that the segments between two paths are correctly identified.
        """
        self.assertEqual(
            self.path.child(b"a").child(b"b").child(b"c").segmentsFrom(self.path),
            [b"a", b"b", b"c"],
        )

    def test_segmentsFromNegative(self):
        """
        Verify that segmentsFrom notices when the ancestor isn't an ancestor.
        """
        self.assertRaises(
            ValueError,
            self.path.child(b"a").child(b"b").child(b"c").segmentsFrom,
            self.path.child(b"d").child(b"c").child(b"e"),
        )

    def test_walk(self):
        """
        Verify that walking the path gives the same result as the known file
        hierarchy.
        """
        x = [foo.path for foo in self.path.walk()]
        self.assertEqual(set(x), set(self.all))

    def test_parents(self):
        """
        L{FilePath.parents()} should return an iterator of every ancestor of
        the L{FilePath} in question.
        """
        L = []
        pathobj = self.path.child(b"a").child(b"b").child(b"c")
        fullpath = pathobj.path
        lastpath = fullpath
        thispath = os.path.dirname(fullpath)
        while lastpath != self.root.path:
            L.append(thispath)
            lastpath = thispath
            thispath = os.path.dirname(thispath)
        self.assertEqual([x.path for x in pathobj.parents()], L)

    def test_validSubdir(self):
        """
        Verify that a valid subdirectory will show up as a directory, but not as a
        file, not as a symlink, and be listable.
        """
        sub1 = self.path.child(b"sub1")
        self.assertTrue(sub1.exists(), "This directory does exist.")
        self.assertTrue(sub1.isdir(), "It's a directory.")
        self.assertFalse(sub1.isfile(), "It's a directory.")
        self.assertFalse(sub1.islink(), "It's a directory.")
        self.assertEqual(sub1.listdir(), [b"file2"])

    def test_invalidSubdir(self):
        """
        Verify that a subdirectory that doesn't exist is reported as such.
        """
        sub2 = self.path.child(b"sub2")
        self.assertFalse(sub2.exists(), "This directory does not exist.")

    def test_validFiles(self):
        """
        Make sure that we can read existent non-empty files.
        """
        f1 = self.path.child(b"file1")
        with f1.open() as f:
            self.assertEqual(f.read(), self.f1content)
        f2 = self.path.child(b"sub1").child(b"file2")
        with f2.open() as f:
            self.assertEqual(f.read(), self.f2content)

    def test_multipleChildSegments(self):
        """
        C{fp.descendant([a, b, c])} returns the same L{FilePath} as is returned
        by C{fp.child(a).child(b).child(c)}.
        """
        multiple = self.path.descendant([b"a", b"b", b"c"])
        single = self.path.child(b"a").child(b"b").child(b"c")
        self.assertEqual(multiple, single)

    def test_dictionaryKeys(self):
        """
        Verify that path instances are usable as dictionary keys.
        """
        f1 = self.path.child(b"file1")
        f1prime = self.path.child(b"file1")
        f2 = self.path.child(b"file2")
        dictoid = {}
        dictoid[f1] = 3
        dictoid[f1prime] = 4
        self.assertEqual(dictoid[f1], 4)
        self.assertEqual(list(dictoid.keys()), [f1])
        self.assertIs(list(dictoid.keys())[0], f1)
        self.assertIsNot(list(dictoid.keys())[0], f1prime)  # sanity check
        dictoid[f2] = 5
        self.assertEqual(dictoid[f2], 5)
        self.assertEqual(len(dictoid), 2)

    def test_dictionaryKeyWithString(self):
        """
        Verify that path instances are usable as dictionary keys which do not clash
        with their string counterparts.
        """
        f1 = self.path.child(b"file1")
        dictoid = {f1: "hello"}
        dictoid[f1.path] = "goodbye"
        self.assertEqual(len(dictoid), 2)

    def test_childrenNonexistentError(self):
        """
        Verify that children raises the appropriate exception for non-existent
        directories.
        """
        self.assertRaises(
            filepath.UnlistableError, self.path.child(b"not real").children
        )

    def test_childrenNotDirectoryError(self):
        """
        Verify that listdir raises the appropriate exception for attempting to list
        a file rather than a directory.
        """
        self.assertRaises(filepath.UnlistableError, self.path.child(b"file1").children)

    def test_newTimesAreFloats(self):
        """
        Verify that all times returned from the various new time functions are ints
        (and hopefully therefore 'high precision').
        """
        for p in self.path, self.path.child(b"file1"):
            self.assertEqual(type(p.getAccessTime()), float)
            self.assertEqual(type(p.getModificationTime()), float)
            self.assertEqual(type(p.getStatusChangeTime()), float)

    def test_oldTimesAreInts(self):
        """
        Verify that all times returned from the various time functions are
        integers, for compatibility.
        """
        for p in self.path, self.path.child(b"file1"):
            self.assertEqual(type(p.getatime()), int)
            self.assertEqual(type(p.getmtime()), int)
            self.assertEqual(type(p.getctime()), int)


class FakeWindowsPath(filepath.FilePath):
    """
    A test version of FilePath which overrides listdir to raise L{WindowsError}.
    """

    def listdir(self):
        """
        @raise WindowsError: always.
        """
        # For Python 3.3 and higher, WindowsError is an alias for OSError.
        # The first argument to the OSError constructor is errno,
        # and the fourth argument is winerror.
        # For further details, refer to:
        # https://docs.python.org/3/library/exceptions.html#OSError
        #
        # On Windows, if winerror is set in the constructor,
        # the errno value in the constructor is ignored, and OSError internally
        # maps the winerror value to an errno value.
        raise OSError(
            None,
            "A directory's validness was called into question",
            self.path,
            ERROR_DIRECTORY,
        )


class ListingCompatibilityTests(BytesTestCase):
    """
    These tests verify compatibility with legacy behavior of directory listing.
    """

    @skipIf(not platform.isWindows(), "Only relevant on on Windows.")
    def test_windowsErrorExcept(self):
        """
        Verify that when a WindowsError is raised from listdir, catching
        WindowsError works.
        """
        fwp = FakeWindowsPath(self.mktemp())
        self.assertRaises(filepath.UnlistableError, fwp.children)
        self.assertRaises(WindowsError, fwp.children)

    def test_alwaysCatchOSError(self):
        """
        Verify that in the normal case where a directory does not exist, we will
        get an OSError.
        """
        fp = filepath.FilePath(self.mktemp())
        self.assertRaises(OSError, fp.children)

    def test_keepOriginalAttributes(self):
        """
        Verify that the Unlistable exception raised will preserve the attributes of
        the previously-raised exception.
        """
        fp = filepath.FilePath(self.mktemp())
        ose = self.assertRaises(OSError, fp.children)
        d1 = list(ose.__dict__.keys())
        d1.remove("originalException")
        d2 = list(ose.originalException.__dict__.keys())
        d1.sort()
        d2.sort()
        self.assertEqual(d1, d2)


class ExplodingFile:
    """
    A C{file}-alike which raises exceptions from its I/O methods and keeps track
    of whether it has been closed.

    @ivar closed: A C{bool} which is C{False} until C{close} is called, then it
        is C{True}.
    """

    closed = False

    def read(self, n=0):
        """
        @raise IOError: Always raised.
        """
        raise OSError()

    def write(self, what):
        """
        @raise IOError: Always raised.
        """
        raise OSError()

    def close(self):
        """
        Mark the file as having been closed.
        """
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class TrackingFilePath(filepath.FilePath):
    """
    A subclass of L{filepath.FilePath} which maintains a list of all other paths
    created by clonePath.

    @ivar trackingList: A list of all paths created by this path via
        C{clonePath} (which also includes paths created by methods like
        C{parent}, C{sibling}, C{child}, etc (and all paths subsequently created
        by those paths, etc).

    @type trackingList: C{list} of L{TrackingFilePath}

    @ivar openedFiles: A list of all file objects opened by this
        L{TrackingFilePath} or any other L{TrackingFilePath} in C{trackingList}.

    @type openedFiles: C{list} of C{file}
    """

    def __init__(self, path, alwaysCreate=False, trackingList=None):
        filepath.FilePath.__init__(self, path, alwaysCreate)
        if trackingList is None:
            trackingList = []
        self.trackingList = trackingList
        self.openedFiles = []

    def open(self, *a, **k):
        """
        Override 'open' to track all files opened by this path.
        """
        f = filepath.FilePath.open(self, *a, **k)
        self.openedFiles.append(f)
        return f

    def openedPaths(self):
        """
        Return a list of all L{TrackingFilePath}s associated with this
        L{TrackingFilePath} that have had their C{open()} method called.
        """
        return [path for path in self.trackingList if path.openedFiles]

    def clonePath(self, name):
        """
        Override L{filepath.FilePath.clonePath} to give the new path a reference
        to the same tracking list.
        """
        clone = TrackingFilePath(name, trackingList=self.trackingList)
        self.trackingList.append(clone)
        return clone


class ExplodingFilePath(filepath.FilePath):
    """
    A specialized L{FilePath} which always returns an instance of
    L{ExplodingFile} from its C{open} method.

    @ivar fp: The L{ExplodingFile} instance most recently returned from the
        C{open} method.
    """

    def __init__(self, pathName, originalExploder=None):
        """
        Initialize an L{ExplodingFilePath} with a name and a reference to the

        @param pathName: The path name as passed to L{filepath.FilePath}.
        @type pathName: C{str}

        @param originalExploder: The L{ExplodingFilePath} to associate opened
        files with.
        @type originalExploder: L{ExplodingFilePath}
        """
        filepath.FilePath.__init__(self, pathName)
        if originalExploder is None:
            originalExploder = self
        self._originalExploder = originalExploder

    def open(self, mode=None):
        """
        Create, save, and return a new C{ExplodingFile}.

        @param mode: Present for signature compatibility.  Ignored.

        @return: A new C{ExplodingFile}.
        """
        f = self._originalExploder.fp = ExplodingFile()
        return f

    def clonePath(self, name):
        return ExplodingFilePath(name, self._originalExploder)


class PermissionsTests(BytesTestCase):
    """
    Test Permissions and RWX classes
    """

    def assertNotUnequal(self, first, second, msg=None):
        """
        Tests that C{first} != C{second} is false.  This method tests the
        __ne__ method, as opposed to L{assertEqual} (C{first} == C{second}),
        which tests the __eq__ method.

        Note: this should really be part of trial
        """
        if first != second:
            if msg is None:
                msg = ""
            if len(msg) > 0:
                msg += "\n"
            raise self.failureException(
                "%snot not unequal (__ne__ not implemented correctly):"
                "\na = %s\nb = %s\n" % (msg, pformat(first), pformat(second))
            )
        return first

    def test_rwxFromBools(self):
        """
        L{RWX}'s constructor takes a set of booleans
        """
        for r in (True, False):
            for w in (True, False):
                for x in (True, False):
                    rwx = filepath.RWX(r, w, x)
                    self.assertEqual(rwx.read, r)
                    self.assertEqual(rwx.write, w)
                    self.assertEqual(rwx.execute, x)
        rwx = filepath.RWX(True, True, True)
        self.assertTrue(rwx.read and rwx.write and rwx.execute)

    def test_rwxEqNe(self):
        """
        L{RWX}'s created with the same booleans are equivalent.  If booleans
        are different, they are not equal.
        """
        for r in (True, False):
            for w in (True, False):
                for x in (True, False):
                    self.assertEqual(filepath.RWX(r, w, x), filepath.RWX(r, w, x))
                    self.assertNotUnequal(filepath.RWX(r, w, x), filepath.RWX(r, w, x))
        self.assertNotEqual(
            filepath.RWX(True, True, True), filepath.RWX(True, True, False)
        )
        self.assertNotEqual(3, filepath.RWX(True, True, True))

    def test_rwxShorthand(self):
        """
        L{RWX}'s shorthand string should be 'rwx' if read, write, and execute
        permission bits are true.  If any of those permissions bits are false,
        the character is replaced by a '-'.
        """

        def getChar(val, letter):
            if val:
                return letter
            return "-"

        for r in (True, False):
            for w in (True, False):
                for x in (True, False):
                    rwx = filepath.RWX(r, w, x)
                    self.assertEqual(
                        rwx.shorthand(),
                        getChar(r, "r") + getChar(w, "w") + getChar(x, "x"),
                    )
        self.assertEqual(filepath.RWX(True, False, True).shorthand(), "r-x")

    def test_permissionsFromStat(self):
        """
        L{Permissions}'s constructor takes a valid permissions bitmask and
        parsaes it to produce the correct set of boolean permissions.
        """

        def _rwxFromStat(statModeInt, who):
            def getPermissionBit(what, who):
                return (statModeInt & getattr(stat, f"S_I{what}{who}")) > 0

            return filepath.RWX(
                *(getPermissionBit(what, who) for what in ("R", "W", "X"))
            )

        for u in range(0, 8):
            for g in range(0, 8):
                for o in range(0, 8):
                    chmodString = "%d%d%d" % (u, g, o)
                    chmodVal = int(chmodString, 8)
                    perm = filepath.Permissions(chmodVal)
                    self.assertEqual(
                        perm.user,
                        _rwxFromStat(chmodVal, "USR"),
                        f"{chmodString}: got user: {perm.user}",
                    )
                    self.assertEqual(
                        perm.group,
                        _rwxFromStat(chmodVal, "GRP"),
                        f"{chmodString}: got group: {perm.group}",
                    )
                    self.assertEqual(
                        perm.other,
                        _rwxFromStat(chmodVal, "OTH"),
                        f"{chmodString}: got other: {perm.other}",
                    )
        perm = filepath.Permissions(0o777)
        for who in ("user", "group", "other"):
            for what in ("read", "write", "execute"):
                self.assertTrue(getattr(getattr(perm, who), what))

    def test_permissionsEq(self):
        """
        Two L{Permissions}'s that are created with the same bitmask
        are equivalent
        """
        self.assertEqual(filepath.Permissions(0o777), filepath.Permissions(0o777))
        self.assertNotUnequal(filepath.Permissions(0o777), filepath.Permissions(0o777))
        self.assertNotEqual(filepath.Permissions(0o777), filepath.Permissions(0o700))
        self.assertNotEqual(3, filepath.Permissions(0o777))

    def test_permissionsShorthand(self):
        """
        L{Permissions}'s shorthand string is the RWX shorthand string for its
        user permission bits, group permission bits, and other permission bits
        concatenated together, without a space.
        """
        for u in range(0, 8):
            for g in range(0, 8):
                for o in range(0, 8):
                    perm = filepath.Permissions(int("0o%d%d%d" % (u, g, o), 8))
                    self.assertEqual(
                        perm.shorthand(),
                        "".join(
                            x.shorthand() for x in (perm.user, perm.group, perm.other)
                        ),
                    )
        self.assertEqual(filepath.Permissions(0o770).shorthand(), "rwxrwx---")


class FilePathTests(AbstractFilePathTests):
    """
    Test various L{FilePath} path manipulations.

    In particular, note that tests defined on this class instead of on the base
    class are only run against L{twisted.python.filepath}.
    """

    def test_chmod(self):
        """
        L{FilePath.chmod} modifies the permissions of
        the passed file as expected (using C{os.stat} to check). We use some
        basic modes that should work everywhere (even on Windows).
        """
        for mode in (0o555, 0o777):
            self.path.child(b"sub1").chmod(mode)
            self.assertEqual(
                stat.S_IMODE(os.stat(self.path.child(b"sub1").path).st_mode), mode
            )

    def createLinks(self):
        """
        Create several symbolic links to files and directories.
        """
        subdir = self.path.child(b"sub1")
        os.symlink(subdir.path, self._mkpath(b"sub1.link"))
        os.symlink(subdir.child(b"file2").path, self._mkpath(b"file2.link"))
        os.symlink(
            subdir.child(b"file2").path, self._mkpath(b"sub1", b"sub1.file2.link")
        )

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_realpathSymlink(self):
        """
        L{FilePath.realpath} returns the path of the ultimate target of a
        symlink.
        """
        self.createLinks()
        os.symlink(
            self.path.child(b"file2.link").path, self.path.child(b"link.link").path
        )
        self.assertEqual(
            self.path.child(b"link.link").realpath(),
            self.path.child(b"sub1").child(b"file2"),
        )

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_realpathCyclicalSymlink(self):
        """
        L{FilePath.realpath} raises L{filepath.LinkError} if the path is a
        symbolic link which is part of a cycle.
        """
        os.symlink(self.path.child(b"link1").path, self.path.child(b"link2").path)
        os.symlink(self.path.child(b"link2").path, self.path.child(b"link1").path)
        self.assertRaises(filepath.LinkError, self.path.child(b"link2").realpath)

    def test_realpathNoSymlink(self):
        """
        L{FilePath.realpath} returns the path itself if the path is not a
        symbolic link.
        """
        self.assertEqual(self.path.child(b"sub1").realpath(), self.path.child(b"sub1"))

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_walkCyclicalSymlink(self):
        """
        Verify that walking a path with a cyclical symlink raises an error
        """
        self.createLinks()
        os.symlink(
            self.path.child(b"sub1").path,
            self.path.child(b"sub1").child(b"sub1.loopylink").path,
        )

        def iterateOverPath():
            return [foo.path for foo in self.path.walk()]

        self.assertRaises(filepath.LinkError, iterateOverPath)

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_walkObeysDescendWithCyclicalSymlinks(self):
        """
        Verify that, after making a path with cyclical symlinks, when the
        supplied C{descend} predicate returns C{False}, the target is not
        traversed, as if it was a simple symlink.
        """
        self.createLinks()
        # we create cyclical symlinks
        os.symlink(
            self.path.child(b"sub1").path,
            self.path.child(b"sub1").child(b"sub1.loopylink").path,
        )

        def noSymLinks(path):
            return not path.islink()

        def iterateOverPath():
            return [foo.path for foo in self.path.walk(descend=noSymLinks)]

        self.assertTrue(iterateOverPath())

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_walkObeysDescend(self):
        """
        Verify that when the supplied C{descend} predicate returns C{False},
        the target is not traversed.
        """
        self.createLinks()

        def noSymLinks(path):
            return not path.islink()

        x = [foo.path for foo in self.path.walk(descend=noSymLinks)]
        self.assertEqual(set(x), set(self.all))

    def test_getAndSet(self):
        content = b"newcontent"
        self.path.child(b"new").setContent(content)
        newcontent = self.path.child(b"new").getContent()
        self.assertEqual(content, newcontent)
        content = b"content"
        self.path.child(b"new").setContent(content, b".tmp")
        newcontent = self.path.child(b"new").getContent()
        self.assertEqual(content, newcontent)

    def test_getContentFileClosing(self):
        """
        If reading from the underlying file raises an exception,
        L{FilePath.getContent} raises that exception after closing the file.
        """
        fp = ExplodingFilePath(b"")
        self.assertRaises(IOError, fp.getContent)
        self.assertTrue(fp.fp.closed)

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_symbolicLink(self):
        """
        Verify the behavior of the C{isLink} method against links and
        non-links. Also check that the symbolic link shares the directory
        property with its target.
        """
        s4 = self.path.child(b"sub4")
        s3 = self.path.child(b"sub3")
        os.symlink(s3.path, s4.path)
        self.assertTrue(s4.islink())
        self.assertFalse(s3.islink())
        self.assertTrue(s4.isdir())
        self.assertTrue(s3.isdir())

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_linkTo(self):
        """
        Verify that symlink creates a valid symlink that is both a link and a
        file if its target is a file, or a directory if its target is a
        directory.
        """
        targetLinks = [
            (self.path.child(b"sub2"), self.path.child(b"sub2.link")),
            (
                self.path.child(b"sub2").child(b"file3.ext1"),
                self.path.child(b"file3.ext1.link"),
            ),
        ]
        for target, link in targetLinks:
            target.linkTo(link)
            self.assertTrue(link.islink(), "This is a link")
            self.assertEqual(target.isdir(), link.isdir())
            self.assertEqual(target.isfile(), link.isfile())

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_linkToErrors(self):
        """
        Verify C{linkTo} fails in the following case:
            - the target is in a directory that doesn't exist
            - the target already exists
        """
        self.assertRaises(
            OSError,
            self.path.child(b"file1").linkTo,
            self.path.child(b"nosub").child(b"file1"),
        )
        self.assertRaises(
            OSError,
            self.path.child(b"file1").linkTo,
            self.path.child(b"sub1").child(b"file2"),
        )

    def testMultiExt(self):
        f3 = self.path.child(b"sub3").child(b"file3")
        exts = b".foo", b".bar", b"ext1", b"ext2", b"ext3"
        self.assertFalse(f3.siblingExtensionSearch(*exts))
        f3e = f3.siblingExtension(b".foo")
        f3e.touch()
        self.assertFalse(not f3.siblingExtensionSearch(*exts).exists())
        self.assertFalse(not f3.siblingExtensionSearch(b"*").exists())
        f3e.remove()
        self.assertFalse(f3.siblingExtensionSearch(*exts))

    def testPreauthChild(self):
        fp = filepath.FilePath(b".")
        fp.preauthChild(b"foo/bar")
        self.assertRaises(filepath.InsecurePath, fp.child, "/mon\u20acy")

    def testStatCache(self):
        p = self.path.child(b"stattest")
        p.touch()
        self.assertEqual(p.getsize(), 0)
        self.assertEqual(abs(p.getmtime() - time.time()) // 20, 0)
        self.assertEqual(abs(p.getctime() - time.time()) // 20, 0)
        self.assertEqual(abs(p.getatime() - time.time()) // 20, 0)
        self.assertTrue(p.exists())
        self.assertTrue(p.exists())
        # OOB removal: FilePath.remove() will automatically restat
        os.remove(p.path)
        # test caching
        self.assertTrue(p.exists())
        p.restat(reraise=False)
        self.assertFalse(p.exists())
        self.assertFalse(p.islink())
        self.assertFalse(p.isdir())
        self.assertFalse(p.isfile())

    def testPersist(self):
        newpath = pickle.loads(pickle.dumps(self.path))
        self.assertEqual(self.path.__class__, newpath.__class__)
        self.assertEqual(self.path.path, newpath.path)

    def testInsecureUNIX(self):
        self.assertRaises(filepath.InsecurePath, self.path.child, b"..")
        self.assertRaises(filepath.InsecurePath, self.path.child, b"/etc")
        self.assertRaises(filepath.InsecurePath, self.path.child, b"../..")

    @skipIf(platform.getType() != "win32", "Test will run only on Windows.")
    def testInsecureWin32(self):
        self.assertRaises(filepath.InsecurePath, self.path.child, b"..\\..")
        self.assertRaises(filepath.InsecurePath, self.path.child, b"C:randomfile")

    @skipIf(platform.getType() != "win32", "Test will run only on Windows.")
    def testInsecureWin32Whacky(self):
        """
        Windows has 'special' filenames like NUL and CON and COM1 and LPR
        and PRN and ... god knows what else.  They can be located anywhere in
        the filesystem.  For obvious reasons, we do not wish to normally permit
        access to these.
        """
        self.assertRaises(filepath.InsecurePath, self.path.child, b"CON")
        self.assertRaises(filepath.InsecurePath, self.path.child, b"C:CON")
        self.assertRaises(filepath.InsecurePath, self.path.child, r"C:\CON")

    def testComparison(self):
        self.assertEqual(filepath.FilePath(b"a"), filepath.FilePath(b"a"))
        self.assertTrue(filepath.FilePath(b"z") > filepath.FilePath(b"a"))
        self.assertTrue(filepath.FilePath(b"z") >= filepath.FilePath(b"a"))
        self.assertTrue(filepath.FilePath(b"a") >= filepath.FilePath(b"a"))
        self.assertTrue(filepath.FilePath(b"a") <= filepath.FilePath(b"a"))
        self.assertTrue(filepath.FilePath(b"a") < filepath.FilePath(b"z"))
        self.assertTrue(filepath.FilePath(b"a") <= filepath.FilePath(b"z"))
        self.assertTrue(filepath.FilePath(b"a") != filepath.FilePath(b"z"))
        self.assertTrue(filepath.FilePath(b"z") != filepath.FilePath(b"a"))

        self.assertFalse(filepath.FilePath(b"z") != filepath.FilePath(b"z"))

    def test_descendantOnly(self):
        """
        If C{".."} is in the sequence passed to L{FilePath.descendant},
        L{InsecurePath} is raised.
        """
        self.assertRaises(
            filepath.InsecurePath, self.path.descendant, ["mon\u20acy", ".."]
        )

    def testSibling(self):
        p = self.path.child(b"sibling_start")
        ts = p.sibling(b"sibling_test")
        self.assertEqual(ts.dirname(), p.dirname())
        self.assertEqual(ts.basename(), b"sibling_test")
        ts.createDirectory()
        self.assertIn(ts, self.path.children())

    def testTemporarySibling(self):
        ts = self.path.temporarySibling()
        self.assertEqual(ts.dirname(), self.path.dirname())
        self.assertNotIn(ts.basename(), self.path.listdir())
        ts.createDirectory()
        self.assertIn(ts, self.path.parent().children())

    def test_temporarySiblingExtension(self):
        """
        If L{FilePath.temporarySibling} is given an extension argument, it will
        produce path objects with that extension appended to their names.
        """
        testExtension = b".test-extension"
        ts = self.path.temporarySibling(testExtension)
        self.assertTrue(
            ts.basename().endswith(testExtension),
            f"{ts.basename()} does not end with {testExtension}",
        )

    def test_removeDirectory(self):
        """
        L{FilePath.remove} on a L{FilePath} that refers to a directory will
        recursively delete its contents.
        """
        self.path.remove()
        self.assertFalse(self.path.exists())

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_removeWithSymlink(self):
        """
        For a path which is a symbolic link, L{FilePath.remove} just deletes
        the link, not the target.
        """
        link = self.path.child(b"sub1.link")
        # setUp creates the sub1 child
        os.symlink(self.path.child(b"sub1").path, link.path)
        link.remove()
        self.assertFalse(link.exists())
        self.assertTrue(self.path.child(b"sub1").exists())

    def test_copyToDirectory(self):
        """
        L{FilePath.copyTo} makes a copy of all the contents of the directory
        named by that L{FilePath} if it is able to do so.
        """
        oldPaths = list(self.path.walk())  # Record initial state
        fp = filepath.FilePath(self.mktemp())
        self.path.copyTo(fp)
        self.path.remove()
        fp.copyTo(self.path)
        newPaths = list(self.path.walk())  # Record double-copy state
        newPaths.sort()
        oldPaths.sort()
        self.assertEqual(newPaths, oldPaths)

    def test_copyToMissingDestFileClosing(self):
        """
        If an exception is raised while L{FilePath.copyTo} is trying to open
        source file to read from, the destination file is closed and the
        exception is raised to the caller of L{FilePath.copyTo}.
        """
        nosuch = self.path.child(b"nothere")
        # Make it look like something to copy, even though it doesn't exist.
        # This could happen if the file is deleted between the isfile check and
        # the file actually being opened.
        nosuch.isfile = lambda: True

        # We won't get as far as writing to this file, but it's still useful for
        # tracking whether we closed it.
        destination = ExplodingFilePath(self.mktemp())

        self.assertRaises(IOError, nosuch.copyTo, destination)
        self.assertTrue(destination.fp.closed)

    def test_copyToFileClosing(self):
        """
        If an exception is raised while L{FilePath.copyTo} is copying bytes
        between two regular files, the source and destination files are closed
        and the exception propagates to the caller of L{FilePath.copyTo}.
        """
        destination = ExplodingFilePath(self.mktemp())
        source = ExplodingFilePath(__file__)
        self.assertRaises(IOError, source.copyTo, destination)
        self.assertTrue(source.fp.closed)
        self.assertTrue(destination.fp.closed)

    def test_copyToDirectoryItself(self):
        """
        L{FilePath.copyTo} fails with an OSError or IOError (depending on
        platform, as it propagates errors from open() and write()) when
        attempting to copy a directory to a child of itself.
        """
        self.assertRaises(
            (OSError, IOError), self.path.copyTo, self.path.child(b"file1")
        )

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_copyToWithSymlink(self):
        """
        Verify that copying with followLinks=True copies symlink targets
        instead of symlinks
        """
        os.symlink(self.path.child(b"sub1").path, self.path.child(b"link1").path)
        fp = filepath.FilePath(self.mktemp())
        self.path.copyTo(fp)
        self.assertFalse(fp.child(b"link1").islink())
        self.assertEqual(
            [x.basename() for x in fp.child(b"sub1").children()],
            [x.basename() for x in fp.child(b"link1").children()],
        )

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_copyToWithoutSymlink(self):
        """
        Verify that copying with followLinks=False copies symlinks as symlinks
        """
        os.symlink(b"sub1", self.path.child(b"link1").path)
        fp = filepath.FilePath(self.mktemp())
        self.path.copyTo(fp, followLinks=False)
        self.assertTrue(fp.child(b"link1").islink())
        self.assertEqual(
            os.readlink(self.path.child(b"link1").path),
            os.readlink(fp.child(b"link1").path),
        )

    def test_copyToMissingSource(self):
        """
        If the source path is missing, L{FilePath.copyTo} raises L{OSError}.
        """
        path = filepath.FilePath(self.mktemp())
        exc = self.assertRaises(OSError, path.copyTo, b"some other path")
        self.assertEqual(exc.errno, errno.ENOENT)

    def test_moveTo(self):
        """
        Verify that moving an entire directory results into another directory
        with the same content.
        """
        oldPaths = list(self.path.walk())  # Record initial state
        fp = filepath.FilePath(self.mktemp())
        self.path.moveTo(fp)
        fp.moveTo(self.path)
        newPaths = list(self.path.walk())  # Record double-move state
        newPaths.sort()
        oldPaths.sort()
        self.assertEqual(newPaths, oldPaths)

    def test_moveToExistsCache(self):
        """
        A L{FilePath} that has been moved aside with L{FilePath.moveTo} no
        longer registers as existing.  Its previously non-existent target
        exists, though, as it was created by the call to C{moveTo}.
        """
        fp = filepath.FilePath(self.mktemp())
        fp2 = filepath.FilePath(self.mktemp())
        fp.touch()

        # Both a sanity check (make sure the file status looks right) and an
        # enticement for stat-caching logic to kick in and remember that these
        # exist / don't exist.
        self.assertTrue(fp.exists())
        self.assertFalse(fp2.exists())

        fp.moveTo(fp2)
        self.assertFalse(fp.exists())
        self.assertTrue(fp2.exists())

    def test_moveToExistsCacheCrossMount(self):
        """
        The assertion of test_moveToExistsCache should hold in the case of a
        cross-mount move.
        """
        self.setUpFaultyRename()
        self.test_moveToExistsCache()

    def test_moveToSizeCache(self, hook=lambda: None):
        """
        L{FilePath.moveTo} clears its destination's status cache, such that
        calls to L{FilePath.getsize} after the call to C{moveTo} will report the
        new size, not the old one.

        This is a separate test from C{test_moveToExistsCache} because it is
        intended to cover the fact that the destination's cache is dropped;
        test_moveToExistsCache doesn't cover this case because (currently) a
        file that doesn't exist yet does not cache the fact of its non-
        existence.
        """
        fp = filepath.FilePath(self.mktemp())
        fp2 = filepath.FilePath(self.mktemp())
        fp.setContent(b"1234")
        fp2.setContent(b"1234567890")
        hook()

        # Sanity check / kick off caching.
        self.assertEqual(fp.getsize(), 4)
        self.assertEqual(fp2.getsize(), 10)
        # Actually attempting to replace a file on Windows would fail with
        # ERROR_ALREADY_EXISTS, but we don't need to test that, just the cached
        # metadata, so, delete the file ...
        os.remove(fp2.path)
        # ... but don't clear the status cache, as fp2.remove() would.
        self.assertEqual(fp2.getsize(), 10)

        fp.moveTo(fp2)
        self.assertEqual(fp2.getsize(), 4)

    def test_moveToSizeCacheCrossMount(self):
        """
        The assertion of test_moveToSizeCache should hold in the case of a
        cross-mount move.
        """
        self.test_moveToSizeCache(hook=self.setUpFaultyRename)

    def test_moveToError(self):
        """
        Verify error behavior of moveTo: it should raises one of OSError or
        IOError if you want to move a path into one of its child. It's simply
        the error raised by the underlying rename system call.
        """
        self.assertRaises(
            (OSError, IOError), self.path.moveTo, self.path.child(b"file1")
        )

    def setUpFaultyRename(self):
        """
        Set up a C{os.rename} that will fail with L{errno.EXDEV} on first call.
        This is used to simulate a cross-device rename failure.

        @return: a list of pair (src, dest) of calls to C{os.rename}
        @rtype: C{list} of C{tuple}
        """
        invokedWith = []

        def faultyRename(src, dest):
            invokedWith.append((src, dest))
            if len(invokedWith) == 1:
                raise OSError(
                    errno.EXDEV,
                    "Test-induced failure simulating " "cross-device rename failure",
                )
            return originalRename(src, dest)

        originalRename = os.rename
        self.patch(os, "rename", faultyRename)
        return invokedWith

    def test_crossMountMoveTo(self):
        """
        C{moveTo} should be able to handle C{EXDEV} error raised by
        C{os.rename} when trying to move a file on a different mounted
        filesystem.
        """
        invokedWith = self.setUpFaultyRename()
        # Bit of a whitebox test - force os.rename, which moveTo tries
        # before falling back to a slower method, to fail, forcing moveTo to
        # use the slower behavior.
        self.test_moveTo()
        # A bit of a sanity check for this whitebox test - if our rename
        # was never invoked, the test has probably fallen into disrepair!
        self.assertTrue(invokedWith)

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_crossMountMoveToWithSymlink(self):
        """
        By default, when moving a symlink, it should follow the link and
        actually copy the content of the linked node.
        """
        invokedWith = self.setUpFaultyRename()
        f2 = self.path.child(b"file2")
        f3 = self.path.child(b"file3")
        os.symlink(self.path.child(b"file1").path, f2.path)
        f2.moveTo(f3)
        self.assertFalse(f3.islink())
        self.assertEqual(f3.getContent(), b"file 1")
        self.assertTrue(invokedWith)

    @skipIf(symlinkSkip, "Platform does not support symlinks")
    def test_crossMountMoveToWithoutSymlink(self):
        """
        Verify that moveTo called with followLinks=False actually create
        another symlink.
        """
        invokedWith = self.setUpFaultyRename()
        f2 = self.path.child(b"file2")
        f3 = self.path.child(b"file3")
        os.symlink(self.path.child(b"file1").path, f2.path)
        f2.moveTo(f3, followLinks=False)
        self.assertTrue(f3.islink())
        self.assertEqual(f3.getContent(), b"file 1")
        self.assertTrue(invokedWith)

    def test_createBinaryMode(self):
        """
        L{FilePath.create} should always open (and write to) files in binary
        mode; line-feed octets should be unmodified.

        (While this test should pass on all platforms, it is only really
        interesting on platforms which have the concept of binary mode, i.e.
        Windows platforms.)
        """
        path = filepath.FilePath(self.mktemp())
        with path.create() as f:
            self.assertIn("b", f.mode)
            f.write(b"\n")
        with open(path.path, "rb") as fp:
            read = fp.read()
            self.assertEqual(read, b"\n")

    def testOpen(self):
        # Opening a file for reading when it does not already exist is an error
        nonexistent = self.path.child(b"nonexistent")
        e = self.assertRaises(IOError, nonexistent.open)
        self.assertEqual(e.errno, errno.ENOENT)

        # Opening a file for writing when it does not exist is okay
        writer = self.path.child(b"writer")
        with writer.open("w") as f:
            f.write(b"abc\ndef")

        # Make sure those bytes ended up there - and test opening a file for
        # reading when it does exist at the same time
        with writer.open() as f:
            self.assertEqual(f.read(), b"abc\ndef")

        # Re-opening that file in write mode should erase whatever was there.
        writer.open("w").close()
        with writer.open() as f:
            self.assertEqual(f.read(), b"")

        # Put some bytes in a file so we can test that appending does not
        # destroy them.
        appender = self.path.child(b"appender")
        with appender.open("w") as f:
            f.write(b"abc")

        with appender.open("a") as f:
            f.write(b"def")

        with appender.open("r") as f:
            self.assertEqual(f.read(), b"abcdef")

        # read/write should let us do both without erasing those bytes
        with appender.open("r+") as f:
            self.assertEqual(f.read(), b"abcdef")
            # ANSI C *requires* an fseek or an fgetpos between an fread and an
            # fwrite or an fwrite and an fread.  We can't reliably get Python to
            # invoke fgetpos, so we seek to a 0 byte offset from the current
            # position instead.  Also, Python sucks for making this seek
            # relative to 1 instead of a symbolic constant representing the
            # current file position.
            f.seek(0, 1)
            # Put in some new bytes for us to test for later.
            f.write(b"ghi")

        # Make sure those new bytes really showed up
        with appender.open("r") as f:
            self.assertEqual(f.read(), b"abcdefghi")

        # write/read should let us do both, but erase anything that's there
        # already.
        with appender.open("w+") as f:
            self.assertEqual(f.read(), b"")
            f.seek(0, 1)  # Don't forget this!
            f.write(b"123")

        # super append mode should let us read and write and also position the
        # cursor at the end of the file, without erasing everything.
        with appender.open("a+") as f:

            # The order of these lines may seem surprising, but it is
            # necessary. The cursor is not at the end of the file until after
            # the first write.

            f.write(b"456")
            f.seek(0, 1)  # Asinine.
            self.assertEqual(f.read(), b"")

            f.seek(0, 0)
            self.assertEqual(f.read(), b"123456")

        # Opening a file exclusively must fail if that file exists already.
        nonexistent.requireCreate(True)
        nonexistent.open("w").close()
        existent = nonexistent
        del nonexistent
        self.assertRaises((OSError, IOError), existent.open)

    def test_openWithExplicitBinaryMode(self):
        """
        Due to a bug in Python 2.7 on Windows including multiple 'b'
        characters in the mode passed to the built-in open() will cause an
        error.  FilePath.open() ensures that only a single 'b' character is
        included in the mode passed to the built-in open().

        See http://bugs.python.org/issue7686 for details about the bug.
        """
        writer = self.path.child(b"explicit-binary")
        with writer.open("wb") as file:
            file.write(b"abc\ndef")
        self.assertTrue(writer.exists)

    def test_openWithRedundantExplicitBinaryModes(self):
        """
        Due to a bug in Python 2.7 on Windows including multiple 'b'
        characters in the mode passed to the built-in open() will cause an
        error.  No matter how many 'b' modes are specified, FilePath.open()
        ensures that only a single 'b' character is included in the mode
        passed to the built-in open().

        See http://bugs.python.org/issue7686 for details about the bug.
        """
        writer = self.path.child(b"multiple-binary")
        with writer.open("wbb") as file:
            file.write(b"abc\ndef")
        self.assertTrue(writer.exists)

    def test_existsCache(self):
        """
        Check that C{filepath.FilePath.exists} correctly restat the object if
        an operation has occurred in the mean time.
        """
        fp = filepath.FilePath(self.mktemp())
        self.assertFalse(fp.exists())

        fp.makedirs()
        self.assertTrue(fp.exists())

    def test_makedirsMakesDirectoriesRecursively(self):
        """
        C{FilePath.makedirs} creates a directory at C{path}}, including
        recursively creating all parent directories leading up to the path.
        """
        fp = filepath.FilePath(os.path.join(self.mktemp(), b"foo", b"bar", b"baz"))
        self.assertFalse(fp.exists())

        fp.makedirs()

        self.assertTrue(fp.exists())
        self.assertTrue(fp.isdir())

    def test_makedirsMakesDirectoriesWithIgnoreExistingDirectory(self):
        """
        Calling C{FilePath.makedirs} with C{ignoreExistingDirectory} set to
        C{True} has no effect if directory does not exist.
        """
        fp = filepath.FilePath(self.mktemp())
        self.assertFalse(fp.exists())

        fp.makedirs(ignoreExistingDirectory=True)

        self.assertTrue(fp.exists())
        self.assertTrue(fp.isdir())

    def test_makedirsThrowsWithExistentDirectory(self):
        """
        C{FilePath.makedirs} throws an C{OSError} exception
        when called on a directory that already exists.
        """
        fp = filepath.FilePath(os.path.join(self.mktemp()))
        fp.makedirs()

        exception = self.assertRaises(OSError, fp.makedirs)

        self.assertEqual(exception.errno, errno.EEXIST)

    def test_makedirsAcceptsIgnoreExistingDirectory(self):
        """
        C{FilePath.makedirs} succeeds when called on a directory that already
        exists and the c{ignoreExistingDirectory} argument is set to C{True}.
        """
        fp = filepath.FilePath(self.mktemp())
        fp.makedirs()
        self.assertTrue(fp.exists())

        fp.makedirs(ignoreExistingDirectory=True)

        self.assertTrue(fp.exists())

    def test_makedirsIgnoreExistingDirectoryExistAlreadyAFile(self):
        """
        When C{FilePath.makedirs} is called with C{ignoreExistingDirectory} set
        to C{True} it throws an C{OSError} exceptions if path is a file.
        """
        fp = filepath.FilePath(self.mktemp())
        fp.create()
        self.assertTrue(fp.isfile())

        exception = self.assertRaises(
            OSError, fp.makedirs, ignoreExistingDirectory=True
        )

        self.assertEqual(exception.errno, errno.EEXIST)

    def test_makedirsRaisesNonEexistErrorsIgnoreExistingDirectory(self):
        """
        When C{FilePath.makedirs} is called with C{ignoreExistingDirectory} set
        to C{True} it raises an C{OSError} exception if exception errno is not
        EEXIST.
        """

        def faultyMakedirs(path):
            raise OSError(errno.EACCES, "Permission Denied")

        self.patch(os, "makedirs", faultyMakedirs)
        fp = filepath.FilePath(self.mktemp())

        exception = self.assertRaises(
            OSError, fp.makedirs, ignoreExistingDirectory=True
        )

        self.assertEqual(exception.errno, errno.EACCES)

    def test_changed(self):
        """
        L{FilePath.changed} indicates that the L{FilePath} has changed, but does
        not re-read the status information from the filesystem until it is
        queried again via another method, such as C{getsize}.
        """
        fp = filepath.FilePath(self.mktemp())
        fp.setContent(b"12345")
        self.assertEqual(fp.getsize(), 5)

        # Someone else comes along and changes the file.
        with open(fp.path, "wb") as fObj:
            fObj.write(b"12345678")

        # Sanity check for caching: size should still be 5.
        self.assertEqual(fp.getsize(), 5)
        fp.changed()

        # This path should look like we don't know what status it's in, not
        # that we know that it didn't exist when last we checked.
        self.assertEqual(fp.getsize(), 8)

    @skipIf(platform.isWindows(), "Test does not run on Windows")
    def test_getPermissions_POSIX(self):
        """
        Getting permissions for a file returns a L{Permissions} object for
        POSIX platforms (which supports separate user, group, and other
        permissions bits.
        """
        for mode in (0o777, 0o700):
            self.path.child(b"sub1").chmod(mode)
            self.assertEqual(
                self.path.child(b"sub1").getPermissions(), filepath.Permissions(mode)
            )
        self.path.child(b"sub1").chmod(0o764)  # sanity check
        self.assertEqual(
            self.path.child(b"sub1").getPermissions().shorthand(), "rwxrw-r--"
        )

    def test_filePathNotDeprecated(self):
        """
        While accessing L{twisted.python.filepath.FilePath.statinfo} is
        deprecated, the filepath itself is not.
        """
        filepath.FilePath(self.mktemp())
        warningInfo = self.flushWarnings([self.test_filePathNotDeprecated])
        self.assertEqual(warningInfo, [])

    @skipIf(not platform.isWindows(), "Test will run only on Windows")
    def test_getPermissions_Windows(self):
        """
        Getting permissions for a file returns a L{Permissions} object in
        Windows.  Windows requires a different test, because user permissions
        = group permissions = other permissions.  Also, chmod may not be able
        to set the execute bit, so we are skipping tests that set the execute
        bit.
        """
        # Change permission after test so file can be deleted
        self.addCleanup(self.path.child(b"sub1").chmod, 0o777)

        for mode in (0o777, 0o555):
            self.path.child(b"sub1").chmod(mode)
            self.assertEqual(
                self.path.child(b"sub1").getPermissions(), filepath.Permissions(mode)
            )
        self.path.child(b"sub1").chmod(0o511)  # sanity check to make sure that
        # user=group=other permissions
        self.assertEqual(
            self.path.child(b"sub1").getPermissions().shorthand(), "r-xr-xr-x"
        )

    def test_whetherBlockOrSocket(self):
        """
        Ensure that a file is not a block or socket
        """
        self.assertFalse(self.path.isBlockDevice())
        self.assertFalse(self.path.isSocket())

    @skipIf(not platform.isWindows(), "Test will run only on Windows")
    def test_statinfoBitsNotImplementedInWindows(self):
        """
        Verify that certain file stats are not available on Windows
        """
        self.assertRaises(NotImplementedError, self.path.getInodeNumber)
        self.assertRaises(NotImplementedError, self.path.getDevice)
        self.assertRaises(NotImplementedError, self.path.getNumberOfHardLinks)
        self.assertRaises(NotImplementedError, self.path.getUserID)
        self.assertRaises(NotImplementedError, self.path.getGroupID)

    @skipIf(platform.isWindows(), "Test does not run on Windows")
    def test_statinfoBitsAreNumbers(self):
        """
        Verify that file inode/device/nlinks/uid/gid stats are numbers in
        a POSIX environment
        """
        c = self.path.child(b"file1")
        for p in self.path, c:
            self.assertIsInstance(p.getInodeNumber(), int)
            self.assertIsInstance(p.getDevice(), int)
            self.assertIsInstance(p.getNumberOfHardLinks(), int)
            self.assertIsInstance(p.getUserID(), int)
            self.assertIsInstance(p.getGroupID(), int)
        self.assertEqual(self.path.getUserID(), c.getUserID())
        self.assertEqual(self.path.getGroupID(), c.getGroupID())

    @skipIf(platform.isWindows(), "Test does not run on Windows")
    def test_statinfoNumbersAreValid(self):
        """
        Verify that the right numbers come back from the right accessor methods
        for file inode/device/nlinks/uid/gid (in a POSIX environment)
        """
        # specify fake statinfo information
        class FakeStat:
            st_ino = 200
            st_dev = 300
            st_nlink = 400
            st_uid = 500
            st_gid = 600

        # monkey patch in a fake restat method for self.path
        fake = FakeStat()

        def fakeRestat(*args, **kwargs):
            self.path._statinfo = fake

        self.path.restat = fakeRestat

        # ensure that restat will need to be called to get values
        self.path._statinfo = None

        self.assertEqual(self.path.getInodeNumber(), fake.st_ino)
        self.assertEqual(self.path.getDevice(), fake.st_dev)
        self.assertEqual(self.path.getNumberOfHardLinks(), fake.st_nlink)
        self.assertEqual(self.path.getUserID(), fake.st_uid)
        self.assertEqual(self.path.getGroupID(), fake.st_gid)


class SetContentTests(BytesTestCase):
    """
    Tests for L{FilePath.setContent}.
    """

    def test_write(self):
        """
        Contents of the file referred to by a L{FilePath} can be written using
        L{FilePath.setContent}.
        """
        pathString = self.mktemp()
        path = filepath.FilePath(pathString)
        path.setContent(b"hello, world")
        with open(pathString, "rb") as fObj:
            contents = fObj.read()
        self.assertEqual(b"hello, world", contents)

    def test_fileClosing(self):
        """
        If writing to the underlying file raises an exception,
        L{FilePath.setContent} raises that exception after closing the file.
        """
        fp = ExplodingFilePath(b"")
        self.assertRaises(IOError, fp.setContent, b"blah")
        self.assertTrue(fp.fp.closed)

    def test_nameCollision(self):
        """
        L{FilePath.setContent} will use a different temporary filename on each
        invocation, so that multiple processes, threads, or reentrant
        invocations will not collide with each other.
        """
        fp = TrackingFilePath(self.mktemp())
        fp.setContent(b"alpha")
        fp.setContent(b"beta")

        # Sanity check: setContent should only open one derivative path each
        # time to store the temporary file.
        openedSiblings = fp.openedPaths()
        self.assertEqual(len(openedSiblings), 2)
        self.assertNotEqual(openedSiblings[0], openedSiblings[1])

    def _assertOneOpened(self, fp, extension):
        """
        Assert that the L{TrackingFilePath} C{fp} was used to open one sibling
        with the given extension.

        @param fp: A L{TrackingFilePath} which should have been used to open
            file at a sibling path.
        @type fp: L{TrackingFilePath}

        @param extension: The extension the sibling path is expected to have
            had.
        @type extension: L{bytes}

        @raise: C{self.failureException} is raised if the extension of the
            opened file is incorrect or if not exactly one file was opened
            using C{fp}.
        """
        opened = fp.openedPaths()
        self.assertEqual(len(opened), 1, "expected exactly one opened file")
        self.assertTrue(
            opened[0].basename().endswith(extension),
            "{} does not end with {!r} extension".format(
                opened[0].basename(), extension
            ),
        )

    def test_defaultExtension(self):
        """
        L{FilePath.setContent} creates temporary files with the extension
        I{.new} if no alternate extension value is given.
        """
        fp = TrackingFilePath(self.mktemp())
        fp.setContent(b"hello")
        self._assertOneOpened(fp, b".new")

    def test_customExtension(self):
        """
        L{FilePath.setContent} creates temporary files with a user-supplied
        extension so that if it is somehow interrupted while writing them the
        file that it leaves behind will be identifiable.
        """
        fp = TrackingFilePath(self.mktemp())
        fp.setContent(b"goodbye", b"-something-else")
        self._assertOneOpened(fp, b"-something-else")


class UnicodeFilePathTests(TestCase):
    """
    L{FilePath} instances should have the same internal representation as they
    were instantiated with.
    """

    def test_UnicodeInstantiation(self):
        """
        L{FilePath} instantiated with a text path will return a text-mode
        FilePath.
        """
        fp = filepath.FilePath("./mon\u20acy")
        self.assertEqual(type(fp.path), str)

    def test_UnicodeInstantiationBytesChild(self):
        """
        Calling L{FilePath.child} on a text-mode L{FilePath} with a L{bytes}
        subpath will return a bytes-mode FilePath.
        """
        fp = filepath.FilePath("./parent-mon\u20acy")
        child = fp.child("child-mon\u20acy".encode())
        self.assertEqual(type(child.path), bytes)

    def test_UnicodeInstantiationUnicodeChild(self):
        """
        Calling L{FilePath.child} on a text-mode L{FilePath} with a text
        subpath will return a text-mode FilePath.
        """
        fp = filepath.FilePath("./parent-mon\u20acy")
        child = fp.child("mon\u20acy")
        self.assertEqual(type(child.path), str)

    def test_UnicodeInstantiationUnicodePreauthChild(self):
        """
        Calling L{FilePath.preauthChild} on a text-mode L{FilePath} with a text
        subpath will return a text-mode FilePath.
        """
        fp = filepath.FilePath("./parent-mon\u20acy")
        child = fp.preauthChild("mon\u20acy")
        self.assertEqual(type(child.path), str)

    def test_UnicodeInstantiationBytesPreauthChild(self):
        """
        Calling L{FilePath.preauthChild} on a text-mode L{FilePath} with a bytes
        subpath will return a bytes-mode FilePath.
        """
        fp = filepath.FilePath("./parent-mon\u20acy")
        child = fp.preauthChild("child-mon\u20acy".encode())
        self.assertEqual(type(child.path), bytes)

    def test_BytesInstantiation(self):
        """
        L{FilePath} instantiated with a L{bytes} path will return a bytes-mode
        FilePath.
        """
        fp = filepath.FilePath(b"./")
        self.assertEqual(type(fp.path), bytes)

    def test_BytesInstantiationBytesChild(self):
        """
        Calling L{FilePath.child} on a bytes-mode L{FilePath} with a bytes
        subpath will return a bytes-mode FilePath.
        """
        fp = filepath.FilePath(b"./")
        child = fp.child("child-mon\u20acy".encode())
        self.assertEqual(type(child.path), bytes)

    def test_BytesInstantiationUnicodeChild(self):
        """
        Calling L{FilePath.child} on a bytes-mode L{FilePath} with a text
        subpath will return a text-mode FilePath.
        """
        fp = filepath.FilePath("parent-mon\u20acy".encode())
        child = fp.child("mon\u20acy")
        self.assertEqual(type(child.path), str)

    def test_BytesInstantiationBytesPreauthChild(self):
        """
        Calling L{FilePath.preauthChild} on a bytes-mode L{FilePath} with a
        bytes subpath will return a bytes-mode FilePath.
        """
        fp = filepath.FilePath("./parent-mon\u20acy".encode())
        child = fp.preauthChild("child-mon\u20acy".encode())
        self.assertEqual(type(child.path), bytes)

    def test_BytesInstantiationUnicodePreauthChild(self):
        """
        Calling L{FilePath.preauthChild} on a bytes-mode L{FilePath} with a text
        subpath will return a text-mode FilePath.
        """
        fp = filepath.FilePath("./parent-mon\u20acy".encode())
        child = fp.preauthChild("mon\u20acy")
        self.assertEqual(type(child.path), str)

    @skipIf(platform.isWindows(), "Test will not work on Windows")
    def test_unicoderepr(self):
        """
        The repr of a L{unicode} L{FilePath} shouldn't burst into flames.
        """
        fp = filepath.FilePath("/mon\u20acy")
        reprOutput = repr(fp)
        self.assertEqual("FilePath('/mon\u20acy')", reprOutput)

    @skipIf(platform.isWindows(), "Test will not work on Windows")
    def test_bytesrepr(self):
        """
        The repr of a L{bytes} L{FilePath} shouldn't burst into flames.
        """
        fp = filepath.FilePath("/parent-mon\u20acy".encode())
        reprOutput = repr(fp)
        self.assertEqual("FilePath(b'/parent-mon\\xe2\\x82\\xacy')", reprOutput)

    @skipIf(not platform.isWindows(), "Test only works on Windows")
    def test_unicodereprWindows(self):
        """
        The repr of a L{unicode} L{FilePath} shouldn't burst into flames.
        """
        fp = filepath.FilePath("C:\\")
        reprOutput = repr(fp)
        self.assertEqual("FilePath('C:\\\\')", reprOutput)

    @skipIf(not platform.isWindows(), "Test only works on Windows")
    def test_bytesreprWindows(self):
        """
        The repr of a L{bytes} L{FilePath} shouldn't burst into flames.
        """
        fp = filepath.FilePath(b"C:\\")
        reprOutput = repr(fp)
        self.assertEqual("FilePath(b'C:\\\\')", reprOutput)

    def test_mixedTypeGlobChildren(self):
        """
        C{globChildren} will return the same type as the pattern argument.
        """
        fp = filepath.FilePath("/")
        children = fp.globChildren(b"*")
        self.assertIsInstance(children[0].path, bytes)

    def test_unicodeGlobChildren(self):
        """
        C{globChildren} works with L{unicode}.
        """
        fp = filepath.FilePath("/")
        children = fp.globChildren("*")
        self.assertIsInstance(children[0].path, str)

    def test_unicodeBasename(self):
        """
        Calling C{basename} on an text- L{FilePath} returns L{unicode}.
        """
        fp = filepath.FilePath("./")
        self.assertIsInstance(fp.basename(), str)

    def test_unicodeDirname(self):
        """
        Calling C{dirname} on a text-mode L{FilePath} returns L{unicode}.
        """
        fp = filepath.FilePath("./")
        self.assertIsInstance(fp.dirname(), str)

    def test_unicodeParent(self):
        """
        Calling C{parent} on a text-mode L{FilePath} will return a text-mode
        L{FilePath}.
        """
        fp = filepath.FilePath("./")
        parent = fp.parent()
        self.assertIsInstance(parent.path, str)

    def test_mixedTypeTemporarySibling(self):
        """
        A L{bytes} extension to C{temporarySibling} will mean a L{bytes} mode
        L{FilePath} is returned.
        """
        fp = filepath.FilePath("./mon\u20acy")
        tempSibling = fp.temporarySibling(b".txt")
        self.assertIsInstance(tempSibling.path, bytes)

    def test_unicodeTemporarySibling(self):
        """
        A L{unicode} extension to C{temporarySibling} will mean a L{unicode}
        mode L{FilePath} is returned.
        """
        fp = filepath.FilePath("/tmp/mon\u20acy")
        tempSibling = fp.temporarySibling(".txt")
        self.assertIsInstance(tempSibling.path, str)

    def test_mixedTypeSiblingExtensionSearch(self):
        """
        C{siblingExtensionSearch} called with L{bytes} on a L{unicode}-mode
        L{FilePath} will return a L{list} of L{bytes}-mode L{FilePath}s.
        """
        fp = filepath.FilePath("./mon\u20acy")
        sibling = filepath.FilePath(fp._asTextPath() + ".txt")
        sibling.touch()
        newPath = fp.siblingExtensionSearch(b".txt")

        self.assertIsInstance(newPath, filepath.FilePath)
        self.assertIsInstance(newPath.path, bytes)

    def test_unicodeSiblingExtensionSearch(self):
        """
        C{siblingExtensionSearch} called with L{unicode} on a L{unicode}-mode
        L{FilePath} will return a L{list} of L{unicode}-mode L{FilePath}s.
        """
        fp = filepath.FilePath("./mon\u20acy")
        sibling = filepath.FilePath(fp._asTextPath() + ".txt")
        sibling.touch()

        newPath = fp.siblingExtensionSearch(".txt")

        self.assertIsInstance(newPath, filepath.FilePath)
        self.assertIsInstance(newPath.path, str)

    def test_mixedTypeSiblingExtension(self):
        """
        C{siblingExtension} called with L{bytes} on a L{unicode}-mode
        L{FilePath} will return a L{bytes}-mode L{FilePath}.
        """
        fp = filepath.FilePath("./mon\u20acy")
        sibling = filepath.FilePath(fp._asTextPath() + ".txt")
        sibling.touch()

        newPath = fp.siblingExtension(b".txt")

        self.assertIsInstance(newPath, filepath.FilePath)
        self.assertIsInstance(newPath.path, bytes)

    def test_unicodeSiblingExtension(self):
        """
        C{siblingExtension} called with L{unicode} on a L{unicode}-mode
        L{FilePath} will return a L{unicode}-mode L{FilePath}.
        """
        fp = filepath.FilePath("./mon\u20acy")
        sibling = filepath.FilePath(fp._asTextPath() + ".txt")
        sibling.touch()

        newPath = fp.siblingExtension(".txt")

        self.assertIsInstance(newPath, filepath.FilePath)
        self.assertIsInstance(newPath.path, str)

    def test_mixedTypeChildSearchPreauth(self):
        """
        C{childSearchPreauth} called with L{bytes} on a L{unicode}-mode
        L{FilePath} will return a L{bytes}-mode L{FilePath}.
        """
        fp = filepath.FilePath("./mon\u20acy")
        fp.createDirectory()
        self.addCleanup(lambda: fp.remove())
        child = fp.child("text.txt")
        child.touch()

        newPath = fp.childSearchPreauth(b"text.txt")

        self.assertIsInstance(newPath, filepath.FilePath)
        self.assertIsInstance(newPath.path, bytes)

    def test_unicodeChildSearchPreauth(self):
        """
        C{childSearchPreauth} called with L{unicode} on a L{unicode}-mode
        L{FilePath} will return a L{unicode}-mode L{FilePath}.
        """
        fp = filepath.FilePath("./mon\u20acy")
        fp.createDirectory()
        self.addCleanup(lambda: fp.remove())
        child = fp.child("text.txt")
        child.touch()

        newPath = fp.childSearchPreauth("text.txt")

        self.assertIsInstance(newPath, filepath.FilePath)
        self.assertIsInstance(newPath.path, str)

    def test_asBytesModeFromUnicode(self):
        """
        C{asBytesMode} on a L{unicode}-mode L{FilePath} returns a new
        L{bytes}-mode L{FilePath}.
        """
        fp = filepath.FilePath("./tmp")
        newfp = fp.asBytesMode()
        self.assertIsNot(fp, newfp)
        self.assertIsInstance(newfp.path, bytes)

    def test_asTextModeFromBytes(self):
        """
        C{asBytesMode} on a L{unicode}-mode L{FilePath} returns a new
        L{bytes}-mode L{FilePath}.
        """
        fp = filepath.FilePath(b"./tmp")
        newfp = fp.asTextMode()
        self.assertIsNot(fp, newfp)
        self.assertIsInstance(newfp.path, str)

    def test_asBytesModeFromBytes(self):
        """
        C{asBytesMode} on a L{bytes}-mode L{FilePath} returns the same
        L{bytes}-mode L{FilePath}.
        """
        fp = filepath.FilePath(b"./tmp")
        newfp = fp.asBytesMode()
        self.assertIs(fp, newfp)
        self.assertIsInstance(newfp.path, bytes)

    def test_asTextModeFromUnicode(self):
        """
        C{asTextMode} on a L{unicode}-mode L{FilePath} returns the same
        L{unicode}-mode L{FilePath}.
        """
        fp = filepath.FilePath("./tmp")
        newfp = fp.asTextMode()
        self.assertIs(fp, newfp)
        self.assertIsInstance(newfp.path, str)

    def test_asBytesModeFromUnicodeWithEncoding(self):
        """
        C{asBytesMode} with an C{encoding} argument uses that encoding when
        coercing the L{unicode}-mode L{FilePath} to a L{bytes}-mode L{FilePath}.
        """
        fp = filepath.FilePath("\u2603")
        newfp = fp.asBytesMode(encoding="utf-8")
        self.assertIn(b"\xe2\x98\x83", newfp.path)

    def test_asTextModeFromBytesWithEncoding(self):
        """
        C{asTextMode} with an C{encoding} argument uses that encoding when
        coercing the L{bytes}-mode L{FilePath} to a L{unicode}-mode L{FilePath}.
        """
        fp = filepath.FilePath(b"\xe2\x98\x83")
        newfp = fp.asTextMode(encoding="utf-8")
        self.assertIn("\u2603", newfp.path)

    def test_asBytesModeFromUnicodeWithUnusableEncoding(self):
        """
        C{asBytesMode} with an C{encoding} argument that can't be used to encode
        the unicode path raises a L{UnicodeError}.
        """
        fp = filepath.FilePath("\u2603")
        with self.assertRaises(UnicodeError):
            fp.asBytesMode(encoding="ascii")

    def test_asTextModeFromBytesWithUnusableEncoding(self):
        """
        C{asTextMode} with an C{encoding} argument that can't be used to encode
        the unicode path raises a L{UnicodeError}.
        """
        fp = filepath.FilePath(br"\u2603")
        with self.assertRaises(UnicodeError):
            fp.asTextMode(encoding="utf-32")
