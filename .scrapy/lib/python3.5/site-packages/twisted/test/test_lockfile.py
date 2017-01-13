# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.lockfile}.
"""

from __future__ import absolute_import, division

import errno
import os

from twisted.trial import unittest
from twisted.python import lockfile
from twisted.python.reflect import requireModule
from twisted.python.runtime import platform

skipKill = None
if platform.isWindows():
    if(requireModule('win32api.OpenProcess') is None and
        requireModule('pywintypes') is None
            ):
        skipKill = ("On windows, lockfile.kill is not implemented in the "
                    "absence of win32api and/or pywintypes.")

class UtilTests(unittest.TestCase):
    """
    Tests for the helper functions used to implement L{FilesystemLock}.
    """
    def test_symlinkEEXIST(self):
        """
        L{lockfile.symlink} raises L{OSError} with C{errno} set to L{EEXIST}
        when an attempt is made to create a symlink which already exists.
        """
        name = self.mktemp()
        lockfile.symlink('foo', name)
        exc = self.assertRaises(OSError, lockfile.symlink, 'foo', name)
        self.assertEqual(exc.errno, errno.EEXIST)


    def test_symlinkEIOWindows(self):
        """
        L{lockfile.symlink} raises L{OSError} with C{errno} set to L{EIO} when
        the underlying L{rename} call fails with L{EIO}.

        Renaming a file on Windows may fail if the target of the rename is in
        the process of being deleted (directory deletion appears not to be
        atomic).
        """
        name = self.mktemp()
        def fakeRename(src, dst):
            raise IOError(errno.EIO, None)
        self.patch(lockfile, 'rename', fakeRename)
        exc = self.assertRaises(IOError, lockfile.symlink, name, "foo")
        self.assertEqual(exc.errno, errno.EIO)
    if not platform.isWindows():
        test_symlinkEIOWindows.skip = (
            "special rename EIO handling only necessary and correct on "
            "Windows.")


    def test_readlinkENOENT(self):
        """
        L{lockfile.readlink} raises L{OSError} with C{errno} set to L{ENOENT}
        when an attempt is made to read a symlink which does not exist.
        """
        name = self.mktemp()
        exc = self.assertRaises(OSError, lockfile.readlink, name)
        self.assertEqual(exc.errno, errno.ENOENT)


    def test_readlinkEACCESWindows(self):
        """
        L{lockfile.readlink} raises L{OSError} with C{errno} set to L{EACCES}
        on Windows when the underlying file open attempt fails with C{EACCES}.

        Opening a file on Windows may fail if the path is inside a directory
        which is in the process of being deleted (directory deletion appears
        not to be atomic).
        """
        name = self.mktemp()
        def fakeOpen(path, mode):
            raise IOError(errno.EACCES, None)
        self.patch(lockfile, '_open', fakeOpen)
        exc = self.assertRaises(IOError, lockfile.readlink, name)
        self.assertEqual(exc.errno, errno.EACCES)
    if not platform.isWindows():
        test_readlinkEACCESWindows.skip = (
            "special readlink EACCES handling only necessary and correct on "
            "Windows.")


    def test_kill(self):
        """
        L{lockfile.kill} returns without error if passed the PID of a
        process which exists and signal C{0}.
        """
        lockfile.kill(os.getpid(), 0)
    test_kill.skip = skipKill


    def test_killESRCH(self):
        """
        L{lockfile.kill} raises L{OSError} with errno of L{ESRCH} if
        passed a PID which does not correspond to any process.
        """
        # Hopefully there is no process with PID 2 ** 31 - 1
        exc = self.assertRaises(OSError, lockfile.kill, 2 ** 31 - 1, 0)
        self.assertEqual(exc.errno, errno.ESRCH)
    test_killESRCH.skip = skipKill


    def test_noKillCall(self):
        """
        Verify that when L{lockfile.kill} does end up as None (e.g. on Windows
        without pywin32), it doesn't end up being called and raising a
        L{TypeError}.
        """
        self.patch(lockfile, "kill", None)
        fl = lockfile.FilesystemLock(self.mktemp())
        fl.lock()
        self.assertFalse(fl.lock())



class LockingTests(unittest.TestCase):
    def _symlinkErrorTest(self, errno):
        def fakeSymlink(source, dest):
            raise OSError(errno, None)
        self.patch(lockfile, 'symlink', fakeSymlink)

        lockf = self.mktemp()
        lock = lockfile.FilesystemLock(lockf)
        exc = self.assertRaises(OSError, lock.lock)
        self.assertEqual(exc.errno, errno)


    def test_symlinkError(self):
        """
        An exception raised by C{symlink} other than C{EEXIST} is passed up to
        the caller of L{FilesystemLock.lock}.
        """
        self._symlinkErrorTest(errno.ENOSYS)


    def test_symlinkErrorPOSIX(self):
        """
        An L{OSError} raised by C{symlink} on a POSIX platform with an errno of
        C{EACCES} or C{EIO} is passed to the caller of L{FilesystemLock.lock}.

        On POSIX, unlike on Windows, these are unexpected errors which cannot
        be handled by L{FilesystemLock}.
        """
        self._symlinkErrorTest(errno.EACCES)
        self._symlinkErrorTest(errno.EIO)
    if platform.isWindows():
        test_symlinkErrorPOSIX.skip = (
            "POSIX-specific error propagation not expected on Windows.")


    def test_cleanlyAcquire(self):
        """
        If the lock has never been held, it can be acquired and the C{clean}
        and C{locked} attributes are set to C{True}.
        """
        lockf = self.mktemp()
        lock = lockfile.FilesystemLock(lockf)
        self.assertTrue(lock.lock())
        self.assertTrue(lock.clean)
        self.assertTrue(lock.locked)


    def test_cleanlyRelease(self):
        """
        If a lock is released cleanly, it can be re-acquired and the C{clean}
        and C{locked} attributes are set to C{True}.
        """
        lockf = self.mktemp()
        lock = lockfile.FilesystemLock(lockf)
        self.assertTrue(lock.lock())
        lock.unlock()
        self.assertFalse(lock.locked)

        lock = lockfile.FilesystemLock(lockf)
        self.assertTrue(lock.lock())
        self.assertTrue(lock.clean)
        self.assertTrue(lock.locked)


    def test_cannotLockLocked(self):
        """
        If a lock is currently locked, it cannot be locked again.
        """
        lockf = self.mktemp()
        firstLock = lockfile.FilesystemLock(lockf)
        self.assertTrue(firstLock.lock())

        secondLock = lockfile.FilesystemLock(lockf)
        self.assertFalse(secondLock.lock())
        self.assertFalse(secondLock.locked)


    def test_uncleanlyAcquire(self):
        """
        If a lock was held by a process which no longer exists, it can be
        acquired, the C{clean} attribute is set to C{False}, and the
        C{locked} attribute is set to C{True}.
        """
        owner = 12345

        def fakeKill(pid, signal):
            if signal != 0:
                raise OSError(errno.EPERM, None)
            if pid == owner:
                raise OSError(errno.ESRCH, None)

        lockf = self.mktemp()
        self.patch(lockfile, 'kill', fakeKill)
        lockfile.symlink(str(owner), lockf)

        lock = lockfile.FilesystemLock(lockf)
        self.assertTrue(lock.lock())
        self.assertFalse(lock.clean)
        self.assertTrue(lock.locked)

        self.assertEqual(lockfile.readlink(lockf), str(os.getpid()))


    def test_lockReleasedBeforeCheck(self):
        """
        If the lock is initially held but then released before it can be
        examined to determine if the process which held it still exists, it is
        acquired and the C{clean} and C{locked} attributes are set to C{True}.
        """
        def fakeReadlink(name):
            # Pretend to be another process releasing the lock.
            lockfile.rmlink(lockf)
            # Fall back to the real implementation of readlink.
            readlinkPatch.restore()
            return lockfile.readlink(name)
        readlinkPatch = self.patch(lockfile, 'readlink', fakeReadlink)

        def fakeKill(pid, signal):
            if signal != 0:
                raise OSError(errno.EPERM, None)
            if pid == 43125:
                raise OSError(errno.ESRCH, None)
        self.patch(lockfile, 'kill', fakeKill)

        lockf = self.mktemp()
        lock = lockfile.FilesystemLock(lockf)
        lockfile.symlink(str(43125), lockf)
        self.assertTrue(lock.lock())
        self.assertTrue(lock.clean)
        self.assertTrue(lock.locked)


    def test_lockReleasedDuringAcquireSymlink(self):
        """
        If the lock is released while an attempt is made to acquire
        it, the lock attempt fails and C{FilesystemLock.lock} returns
        C{False}.  This can happen on Windows when L{lockfile.symlink}
        fails with L{IOError} of C{EIO} because another process is in
        the middle of a call to L{os.rmdir} (implemented in terms of
        RemoveDirectory) which is not atomic.
        """
        def fakeSymlink(src, dst):
            # While another process id doing os.rmdir which the Windows
            # implementation of rmlink does, a rename call will fail with EIO.
            raise OSError(errno.EIO, None)

        self.patch(lockfile, 'symlink', fakeSymlink)

        lockf = self.mktemp()
        lock = lockfile.FilesystemLock(lockf)
        self.assertFalse(lock.lock())
        self.assertFalse(lock.locked)
    if not platform.isWindows():
        test_lockReleasedDuringAcquireSymlink.skip = (
            "special rename EIO handling only necessary and correct on "
            "Windows.")


    def test_lockReleasedDuringAcquireReadlink(self):
        """
        If the lock is initially held but is released while an attempt
        is made to acquire it, the lock attempt fails and
        L{FilesystemLock.lock} returns C{False}.
        """
        def fakeReadlink(name):
            # While another process is doing os.rmdir which the
            # Windows implementation of rmlink does, a readlink call
            # will fail with EACCES.
            raise IOError(errno.EACCES, None)
        self.patch(lockfile, 'readlink', fakeReadlink)

        lockf = self.mktemp()
        lock = lockfile.FilesystemLock(lockf)
        lockfile.symlink(str(43125), lockf)
        self.assertFalse(lock.lock())
        self.assertFalse(lock.locked)
    if not platform.isWindows():
        test_lockReleasedDuringAcquireReadlink.skip = (
            "special readlink EACCES handling only necessary and correct on "
            "Windows.")


    def _readlinkErrorTest(self, exceptionType, errno):
        def fakeReadlink(name):
            raise exceptionType(errno, None)
        self.patch(lockfile, 'readlink', fakeReadlink)

        lockf = self.mktemp()

        # Make it appear locked so it has to use readlink
        lockfile.symlink(str(43125), lockf)

        lock = lockfile.FilesystemLock(lockf)
        exc = self.assertRaises(exceptionType, lock.lock)
        self.assertEqual(exc.errno, errno)
        self.assertFalse(lock.locked)


    def test_readlinkError(self):
        """
        An exception raised by C{readlink} other than C{ENOENT} is passed up to
        the caller of L{FilesystemLock.lock}.
        """
        self._readlinkErrorTest(OSError, errno.ENOSYS)
        self._readlinkErrorTest(IOError, errno.ENOSYS)


    def test_readlinkErrorPOSIX(self):
        """
        Any L{IOError} raised by C{readlink} on a POSIX platform passed to the
        caller of L{FilesystemLock.lock}.

        On POSIX, unlike on Windows, these are unexpected errors which cannot
        be handled by L{FilesystemLock}.
        """
        self._readlinkErrorTest(IOError, errno.ENOSYS)
        self._readlinkErrorTest(IOError, errno.EACCES)
    if platform.isWindows():
        test_readlinkErrorPOSIX.skip = (
            "POSIX-specific error propagation not expected on Windows.")


    def test_lockCleanedUpConcurrently(self):
        """
        If a second process cleans up the lock after a first one checks the
        lock and finds that no process is holding it, the first process does
        not fail when it tries to clean up the lock.
        """
        def fakeRmlink(name):
            rmlinkPatch.restore()
            # Pretend to be another process cleaning up the lock.
            lockfile.rmlink(lockf)
            # Fall back to the real implementation of rmlink.
            return lockfile.rmlink(name)
        rmlinkPatch = self.patch(lockfile, 'rmlink', fakeRmlink)

        def fakeKill(pid, signal):
            if signal != 0:
                raise OSError(errno.EPERM, None)
            if pid == 43125:
                raise OSError(errno.ESRCH, None)
        self.patch(lockfile, 'kill', fakeKill)

        lockf = self.mktemp()
        lock = lockfile.FilesystemLock(lockf)
        lockfile.symlink(str(43125), lockf)
        self.assertTrue(lock.lock())
        self.assertTrue(lock.clean)
        self.assertTrue(lock.locked)


    def test_rmlinkError(self):
        """
        An exception raised by L{rmlink} other than C{ENOENT} is passed up
        to the caller of L{FilesystemLock.lock}.
        """
        def fakeRmlink(name):
            raise OSError(errno.ENOSYS, None)
        self.patch(lockfile, 'rmlink', fakeRmlink)

        def fakeKill(pid, signal):
            if signal != 0:
                raise OSError(errno.EPERM, None)
            if pid == 43125:
                raise OSError(errno.ESRCH, None)
        self.patch(lockfile, 'kill', fakeKill)

        lockf = self.mktemp()

        # Make it appear locked so it has to use readlink
        lockfile.symlink(str(43125), lockf)

        lock = lockfile.FilesystemLock(lockf)
        exc = self.assertRaises(OSError, lock.lock)
        self.assertEqual(exc.errno, errno.ENOSYS)
        self.assertFalse(lock.locked)


    def test_killError(self):
        """
        If L{kill} raises an exception other than L{OSError} with errno set to
        C{ESRCH}, the exception is passed up to the caller of
        L{FilesystemLock.lock}.
        """
        def fakeKill(pid, signal):
            raise OSError(errno.EPERM, None)
        self.patch(lockfile, 'kill', fakeKill)

        lockf = self.mktemp()

        # Make it appear locked so it has to use readlink
        lockfile.symlink(str(43125), lockf)

        lock = lockfile.FilesystemLock(lockf)
        exc = self.assertRaises(OSError, lock.lock)
        self.assertEqual(exc.errno, errno.EPERM)
        self.assertFalse(lock.locked)


    def test_unlockOther(self):
        """
        L{FilesystemLock.unlock} raises L{ValueError} if called for a lock
        which is held by a different process.
        """
        lockf = self.mktemp()
        lockfile.symlink(str(os.getpid() + 1), lockf)
        lock = lockfile.FilesystemLock(lockf)
        self.assertRaises(ValueError, lock.unlock)


    def test_isLocked(self):
        """
        L{isLocked} returns C{True} if the named lock is currently locked,
        C{False} otherwise.
        """
        lockf = self.mktemp()
        self.assertFalse(lockfile.isLocked(lockf))
        lock = lockfile.FilesystemLock(lockf)
        self.assertTrue(lock.lock())
        self.assertTrue(lockfile.isLocked(lockf))
        lock.unlock()
        self.assertFalse(lockfile.isLocked(lockf))
