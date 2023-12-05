# -*- test-case-name: twisted.python.test.test_zippath -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module contains implementations of L{IFilePath} for zip files.

See the constructor of L{ZipArchive} for use.
"""


import errno
import os
import time
from typing import Dict
from zipfile import ZipFile

from zope.interface import implementer

from twisted.python.compat import cmp, comparable
from twisted.python.filepath import (
    AbstractFilePath,
    FilePath,
    IFilePath,
    UnlistableError,
    _coerceToFilesystemEncoding,
)

ZIP_PATH_SEP = "/"  # In zipfiles, "/" is universally used as the
# path separator, regardless of platform.


@comparable
@implementer(IFilePath)
class ZipPath(AbstractFilePath):
    """
    I represent a file or directory contained within a zip file.
    """

    def __init__(self, archive, pathInArchive):
        """
        Don't construct me directly.  Use C{ZipArchive.child()}.

        @param archive: a L{ZipArchive} instance.

        @param pathInArchive: a ZIP_PATH_SEP-separated string.
        """
        self.archive = archive
        self.pathInArchive = pathInArchive

        # self.path pretends to be os-specific because that's the way the
        # 'zipimport' module does it.
        sep = _coerceToFilesystemEncoding(pathInArchive, ZIP_PATH_SEP)
        archiveFilename = _coerceToFilesystemEncoding(
            pathInArchive, archive.zipfile.filename
        )
        self.path = os.path.join(archiveFilename, *(self.pathInArchive.split(sep)))

    def __cmp__(self, other):
        if not isinstance(other, ZipPath):
            return NotImplemented
        return cmp(
            (self.archive, self.pathInArchive), (other.archive, other.pathInArchive)
        )

    def __repr__(self) -> str:
        parts = [
            _coerceToFilesystemEncoding(self.sep, os.path.abspath(self.archive.path))
        ]
        parts.extend(self.pathInArchive.split(self.sep))
        ossep = _coerceToFilesystemEncoding(self.sep, os.sep)
        return f"ZipPath({ossep.join(parts)!r})"

    @property
    def sep(self):
        """
        Return a zip directory separator.

        @return: The zip directory separator.
        @returntype: The same type as C{self.path}.
        """
        return _coerceToFilesystemEncoding(self.path, ZIP_PATH_SEP)

    def parent(self):
        splitup = self.pathInArchive.split(self.sep)
        if len(splitup) == 1:
            return self.archive
        return ZipPath(self.archive, self.sep.join(splitup[:-1]))

    def child(self, path):
        """
        Return a new ZipPath representing a path in C{self.archive} which is
        a child of this path.

        @note: Requesting the C{".."} (or other special name) child will not
            cause L{InsecurePath} to be raised since these names do not have
            any special meaning inside a zip archive.  Be particularly
            careful with the C{path} attribute (if you absolutely must use
            it) as this means it may include special names with special
            meaning outside of the context of a zip archive.
        """
        joiner = _coerceToFilesystemEncoding(path, ZIP_PATH_SEP)
        pathInArchive = _coerceToFilesystemEncoding(path, self.pathInArchive)
        return ZipPath(self.archive, joiner.join([pathInArchive, path]))

    def sibling(self, path):
        return self.parent().child(path)

    def exists(self):
        return self.isdir() or self.isfile()

    def isdir(self):
        return self.pathInArchive in self.archive.childmap

    def isfile(self):
        return self.pathInArchive in self.archive.zipfile.NameToInfo

    def islink(self):
        return False

    def listdir(self):
        if self.exists():
            if self.isdir():
                return list(self.archive.childmap[self.pathInArchive].keys())
            else:
                raise UnlistableError(OSError(errno.ENOTDIR, "Leaf zip entry listed"))
        else:
            raise UnlistableError(
                OSError(errno.ENOENT, "Non-existent zip entry listed")
            )

    def splitext(self):
        """
        Return a value similar to that returned by C{os.path.splitext}.
        """
        # This happens to work out because of the fact that we use OS-specific
        # path separators in the constructor to construct our fake 'path'
        # attribute.
        return os.path.splitext(self.path)

    def basename(self):
        return self.pathInArchive.split(self.sep)[-1]

    def dirname(self):
        # XXX NOTE: This API isn't a very good idea on filepath, but it's even
        # less meaningful here.
        return self.parent().path

    def open(self, mode="r"):
        pathInArchive = _coerceToFilesystemEncoding("", self.pathInArchive)
        return self.archive.zipfile.open(pathInArchive, mode=mode)

    def changed(self):
        pass

    def getsize(self):
        """
        Retrieve this file's size.

        @return: file size, in bytes
        """
        pathInArchive = _coerceToFilesystemEncoding("", self.pathInArchive)
        return self.archive.zipfile.NameToInfo[pathInArchive].file_size

    def getAccessTime(self):
        """
        Retrieve this file's last access-time.  This is the same as the last access
        time for the archive.

        @return: a number of seconds since the epoch
        """
        return self.archive.getAccessTime()

    def getModificationTime(self):
        """
        Retrieve this file's last modification time.  This is the time of
        modification recorded in the zipfile.

        @return: a number of seconds since the epoch.
        """
        pathInArchive = _coerceToFilesystemEncoding("", self.pathInArchive)
        return time.mktime(
            self.archive.zipfile.NameToInfo[pathInArchive].date_time + (0, 0, 0)
        )

    def getStatusChangeTime(self):
        """
        Retrieve this file's last modification time.  This name is provided for
        compatibility, and returns the same value as getmtime.

        @return: a number of seconds since the epoch.
        """
        return self.getModificationTime()


class ZipArchive(ZipPath):
    """
    I am a L{FilePath}-like object which can wrap a zip archive as if it were a
    directory.

    It works similarly to L{FilePath} in L{bytes} and L{unicode} handling --
    instantiating with a L{bytes} will return a "bytes mode" L{ZipArchive},
    and instantiating with a L{unicode} will return a "text mode"
    L{ZipArchive}. Methods that return new L{ZipArchive} or L{ZipPath}
    instances will be in the mode of the argument to the creator method,
    converting if required.
    """

    @property
    def archive(self):
        return self

    def __init__(self, archivePathname):
        """
        Create a ZipArchive, treating the archive at archivePathname as a zip
        file.

        @param archivePathname: a L{bytes} or L{unicode}, naming a path in the
            filesystem.
        """
        self.path = archivePathname
        self.zipfile = ZipFile(_coerceToFilesystemEncoding("", archivePathname))
        self.pathInArchive = _coerceToFilesystemEncoding(archivePathname, "")
        # zipfile is already wasting O(N) memory on cached ZipInfo instances,
        # so there's no sense in trying to do this lazily or intelligently
        self.childmap: Dict[str, Dict[str, int]] = {}

        for name in self.zipfile.namelist():
            name = _coerceToFilesystemEncoding(self.path, name).split(self.sep)
            for x in range(len(name)):
                child = name[-x]
                parent = self.sep.join(name[:-x])
                if parent not in self.childmap:
                    self.childmap[parent] = {}
                self.childmap[parent][child] = 1
            parent = _coerceToFilesystemEncoding(archivePathname, "")

    def child(self, path):
        """
        Create a ZipPath pointing at a path within the archive.

        @param path: a L{bytes} or L{unicode} with no path separators in it
            (either '/' or the system path separator, if it's different).
        """
        return ZipPath(self, path)

    def exists(self):
        """
        Returns C{True} if the underlying archive exists.
        """
        return FilePath(self.zipfile.filename).exists()

    def getAccessTime(self):
        """
        Return the archive file's last access time.
        """
        return FilePath(self.zipfile.filename).getAccessTime()

    def getModificationTime(self):
        """
        Return the archive file's modification time.
        """
        return FilePath(self.zipfile.filename).getModificationTime()

    def getStatusChangeTime(self):
        """
        Return the archive file's status change time.
        """
        return FilePath(self.zipfile.filename).getStatusChangeTime()

    def __repr__(self) -> str:
        return f"ZipArchive({os.path.abspath(self.path)!r})"


__all__ = ["ZipArchive", "ZipPath"]
