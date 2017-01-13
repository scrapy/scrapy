# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the inotify wrapper in L{twisted.internet.inotify}.
"""
import sys

from twisted.internet import defer, reactor
from twisted.python import filepath, runtime
from twisted.python.reflect import requireModule
from twisted.trial import unittest

if requireModule('twisted.python._inotify') is not None:
    from twisted.internet import inotify
else:
    inotify = None



class INotifyTests(unittest.TestCase):
    """
    Define all the tests for the basic functionality exposed by
    L{inotify.INotify}.
    """
    if not runtime.platform.supportsINotify():
        skip = "This platform doesn't support INotify."

    def setUp(self):
        self.dirname = filepath.FilePath(self.mktemp())
        self.dirname.createDirectory()
        self.inotify = inotify.INotify()
        self.inotify.startReading()
        self.addCleanup(self.inotify.loseConnection)


    def test_initializationErrors(self):
        """
        L{inotify.INotify} emits a C{RuntimeError} when initialized
        in an environment that doesn't support inotify as we expect it.

        We just try to raise an exception for every possible case in
        the for loop in L{inotify.INotify._inotify__init__}.
        """
        class FakeINotify:
            def init(self):
                raise inotify.INotifyError()
        self.patch(inotify.INotify, '_inotify', FakeINotify())
        self.assertRaises(inotify.INotifyError, inotify.INotify)


    def _notificationTest(self, mask, operation, expectedPath=None):
        """
        Test notification from some filesystem operation.

        @param mask: The event mask to use when setting up the watch.

        @param operation: A function which will be called with the
            name of a file in the watched directory and which should
            trigger the event.

        @param expectedPath: Optionally, the name of the path which is
            expected to come back in the notification event; this will
            also be passed to C{operation} (primarily useful when the
            operation is being done to the directory itself, not a
            file in it).

        @return: A L{Deferred} which fires successfully when the
            expected event has been received or fails otherwise.
        """
        if expectedPath is None:
            expectedPath = self.dirname.child("foo.bar")
        notified = defer.Deferred()
        def cbNotified(result):
            (watch, filename, events) = result
            self.assertEqual(filename.asBytesMode(), expectedPath.asBytesMode())
            self.assertTrue(events & mask)
        notified.addCallback(cbNotified)

        self.inotify.watch(
            self.dirname, mask=mask,
            callbacks=[lambda *args: notified.callback(args)])
        operation(expectedPath)
        return notified


    def test_access(self):
        """
        Reading from a file in a monitored directory sends an
        C{inotify.IN_ACCESS} event to the callback.
        """
        def operation(path):
            path.setContent(b"foo")
            path.getContent()

        return self._notificationTest(inotify.IN_ACCESS, operation)


    def test_modify(self):
        """
        Writing to a file in a monitored directory sends an
        C{inotify.IN_MODIFY} event to the callback.
        """
        def operation(path):
            with path.open("w") as fObj:
                fObj.write(b'foo')

        return self._notificationTest(inotify.IN_MODIFY, operation)


    def test_attrib(self):
        """
        Changing the metadata of a file in a monitored directory
        sends an C{inotify.IN_ATTRIB} event to the callback.
        """
        def operation(path):
            path.touch()
            path.touch()

        return self._notificationTest(inotify.IN_ATTRIB, operation)


    def test_closeWrite(self):
        """
        Closing a file which was open for writing in a monitored
        directory sends an C{inotify.IN_CLOSE_WRITE} event to the
        callback.
        """
        def operation(path):
            path.open("w").close()

        return self._notificationTest(inotify.IN_CLOSE_WRITE, operation)


    def test_closeNoWrite(self):
        """
        Closing a file which was open for reading but not writing in a
        monitored directory sends an C{inotify.IN_CLOSE_NOWRITE} event
        to the callback.
        """
        def operation(path):
            path.touch()
            path.open("r").close()

        return self._notificationTest(inotify.IN_CLOSE_NOWRITE, operation)


    def test_open(self):
        """
        Opening a file in a monitored directory sends an
        C{inotify.IN_OPEN} event to the callback.
        """
        def operation(path):
            path.open("w").close()

        return self._notificationTest(inotify.IN_OPEN, operation)


    def test_movedFrom(self):
        """
        Moving a file out of a monitored directory sends an
        C{inotify.IN_MOVED_FROM} event to the callback.
        """
        def operation(path):
            path.open("w").close()
            path.moveTo(filepath.FilePath(self.mktemp()))

        return self._notificationTest(inotify.IN_MOVED_FROM, operation)


    def test_movedTo(self):
        """
        Moving a file into a monitored directory sends an
        C{inotify.IN_MOVED_TO} event to the callback.
        """
        def operation(path):
            p = filepath.FilePath(self.mktemp())
            p.touch()
            p.moveTo(path)

        return self._notificationTest(inotify.IN_MOVED_TO, operation)


    def test_create(self):
        """
        Creating a file in a monitored directory sends an
        C{inotify.IN_CREATE} event to the callback.
        """
        def operation(path):
            path.open("w").close()

        return self._notificationTest(inotify.IN_CREATE, operation)


    def test_delete(self):
        """
        Deleting a file in a monitored directory sends an
        C{inotify.IN_DELETE} event to the callback.
        """
        def operation(path):
            path.touch()
            path.remove()

        return self._notificationTest(inotify.IN_DELETE, operation)


    def test_deleteSelf(self):
        """
        Deleting the monitored directory itself sends an
        C{inotify.IN_DELETE_SELF} event to the callback.
        """
        def operation(path):
            path.remove()

        return self._notificationTest(
            inotify.IN_DELETE_SELF, operation, expectedPath=self.dirname)


    def test_moveSelf(self):
        """
        Renaming the monitored directory itself sends an
        C{inotify.IN_MOVE_SELF} event to the callback.
        """
        def operation(path):
            path.moveTo(filepath.FilePath(self.mktemp()))

        return self._notificationTest(
            inotify.IN_MOVE_SELF, operation, expectedPath=self.dirname)


    def test_simpleSubdirectoryAutoAdd(self):
        """
        L{inotify.INotify} when initialized with autoAdd==True adds
        also adds the created subdirectories to the watchlist.
        """
        def _callback(wp, filename, mask):
            # We are notified before we actually process new
            # directories, so we need to defer this check.
            def _():
                try:
                    self.assertTrue(self.inotify._isWatched(subdir))
                    d.callback(None)
                except Exception:
                    d.errback()
            reactor.callLater(0, _)

        checkMask = inotify.IN_ISDIR | inotify.IN_CREATE
        self.inotify.watch(
            self.dirname, mask=checkMask, autoAdd=True,
            callbacks=[_callback])
        subdir = self.dirname.child('test')
        d = defer.Deferred()
        subdir.createDirectory()
        return d


    def test_simpleDeleteDirectory(self):
        """
        L{inotify.INotify} removes a directory from the watchlist when
        it's removed from the filesystem.
        """
        calls = []
        def _callback(wp, filename, mask):
            # We are notified before we actually process new
            # directories, so we need to defer this check.
            def _():
                try:
                    self.assertTrue(self.inotify._isWatched(subdir))
                    subdir.remove()
                except Exception:
                    d.errback()
            def _eb():
                # second call, we have just removed the subdir
                try:
                    self.assertFalse(self.inotify._isWatched(subdir))
                    d.callback(None)
                except Exception:
                    d.errback()

            if not calls:
                # first call, it's the create subdir
                calls.append(filename)
                reactor.callLater(0, _)

            else:
                reactor.callLater(0, _eb)

        checkMask = inotify.IN_ISDIR | inotify.IN_CREATE
        self.inotify.watch(
            self.dirname, mask=checkMask, autoAdd=True,
            callbacks=[_callback])
        subdir = self.dirname.child('test')
        d = defer.Deferred()
        subdir.createDirectory()
        return d


    def test_ignoreDirectory(self):
        """
        L{inotify.INotify.ignore} removes a directory from the watchlist
        """
        self.inotify.watch(self.dirname, autoAdd=True)
        self.assertTrue(self.inotify._isWatched(self.dirname))
        self.inotify.ignore(self.dirname)
        self.assertFalse(self.inotify._isWatched(self.dirname))


    def test_humanReadableMask(self):
        """
        L{inotify.humaReadableMask} translates all the possible event
        masks to a human readable string.
        """
        for mask, value in inotify._FLAG_TO_HUMAN:
            self.assertEqual(inotify.humanReadableMask(mask)[0], value)

        checkMask = (
            inotify.IN_CLOSE_WRITE | inotify.IN_ACCESS | inotify.IN_OPEN)
        self.assertEqual(
            set(inotify.humanReadableMask(checkMask)),
            set(['close_write', 'access', 'open']))


    def test_recursiveWatch(self):
        """
        L{inotify.INotify.watch} with recursive==True will add all the
        subdirectories under the given path to the watchlist.
        """
        subdir = self.dirname.child('test')
        subdir2 = subdir.child('test2')
        subdir3 = subdir2.child('test3')
        subdir3.makedirs()
        dirs = [subdir, subdir2, subdir3]
        self.inotify.watch(self.dirname, recursive=True)
        # let's even call this twice so that we test that nothing breaks
        self.inotify.watch(self.dirname, recursive=True)
        for d in dirs:
            self.assertTrue(self.inotify._isWatched(d))


    def test_connectionLostError(self):
        """
        L{inotify.INotify.connectionLost} if there's a problem while closing
        the fd shouldn't raise the exception but should log the error
        """
        import os
        in_ = inotify.INotify()
        os.close(in_._fd)
        in_.loseConnection()
        self.flushLoggedErrors()

    def test_noAutoAddSubdirectory(self):
        """
        L{inotify.INotify.watch} with autoAdd==False will stop inotify
        from watching subdirectories created under the watched one.
        """
        def _callback(wp, fp, mask):
            # We are notified before we actually process new
            # directories, so we need to defer this check.
            def _():
                try:
                    self.assertFalse(self.inotify._isWatched(subdir))
                    d.callback(None)
                except Exception:
                    d.errback()
            reactor.callLater(0, _)

        checkMask = inotify.IN_ISDIR | inotify.IN_CREATE
        self.inotify.watch(
            self.dirname, mask=checkMask, autoAdd=False,
            callbacks=[_callback])
        subdir = self.dirname.child('test')
        d = defer.Deferred()
        subdir.createDirectory()
        return d


    def test_seriesOfWatchAndIgnore(self):
        """
        L{inotify.INotify} will watch a filepath for events even if the same
        path is repeatedly added/removed/re-added to the watchpoints.
        """
        expectedPath = self.dirname.child("foo.bar2")
        expectedPath.touch()

        notified = defer.Deferred()
        def cbNotified(result):
            (ignored, filename, events) = result
            self.assertEqual(filename.asBytesMode(), expectedPath.asBytesMode())
            self.assertTrue(events & inotify.IN_DELETE_SELF)

        def callIt(*args):
            notified.callback(args)

        # Watch, ignore, watch again to get into the state being tested.
        self.assertTrue(self.inotify.watch(expectedPath, callbacks=[callIt]))
        self.inotify.ignore(expectedPath)
        self.assertTrue(
            self.inotify.watch(
                expectedPath, mask=inotify.IN_DELETE_SELF, callbacks=[callIt]))

        notified.addCallback(cbNotified)

        # Apparently in kernel version < 2.6.25, inofify has a bug in the way
        # similar events are coalesced.  So, be sure to generate a different
        # event here than the touch() at the top of this method might have
        # generated.
        expectedPath.remove()

        return notified


    def test_ignoreFilePath(self):
        """
        L{inotify.INotify} will ignore a filepath after it has been removed from
        the watch list.
        """
        expectedPath = self.dirname.child("foo.bar2")
        expectedPath.touch()
        expectedPath2 = self.dirname.child("foo.bar3")
        expectedPath2.touch()

        notified = defer.Deferred()
        def cbNotified(result):
            (ignored, filename, events) = result
            self.assertEqual(filename.asBytesMode(), expectedPath2.asBytesMode())
            self.assertTrue(events & inotify.IN_DELETE_SELF)

        def callIt(*args):
            notified.callback(args)

        self.assertTrue(
            self.inotify.watch(
                expectedPath, inotify.IN_DELETE_SELF, callbacks=[callIt]))
        notified.addCallback(cbNotified)

        self.assertTrue(
            self.inotify.watch(
                expectedPath2, inotify.IN_DELETE_SELF, callbacks=[callIt]))

        self.inotify.ignore(expectedPath)

        expectedPath.remove()
        expectedPath2.remove()

        return notified


    def test_ignoreNonWatchedFile(self):
        """
        L{inotify.INotify} will raise KeyError if a non-watched filepath is
        ignored.
        """
        expectedPath = self.dirname.child("foo.ignored")
        expectedPath.touch()

        self.assertRaises(KeyError, self.inotify.ignore, expectedPath)


    def test_complexSubdirectoryAutoAdd(self):
        """
        L{inotify.INotify} with autoAdd==True for a watched path
        generates events for every file or directory already present
        in a newly created subdirectory under the watched one.

        This tests that we solve a race condition in inotify even though
        we may generate duplicate events.
        """
        calls = set()
        def _callback(wp, filename, mask):
            calls.add(filename)
            if len(calls) == 6:
                try:
                    self.assertTrue(self.inotify._isWatched(subdir))
                    self.assertTrue(self.inotify._isWatched(subdir2))
                    self.assertTrue(self.inotify._isWatched(subdir3))
                    created = someFiles + [subdir, subdir2, subdir3]
                    created = {f.asBytesMode() for f in created}
                    self.assertEqual(len(calls), len(created))
                    self.assertEqual(calls, created)
                except Exception:
                    d.errback()
                else:
                    d.callback(None)

        checkMask = inotify.IN_ISDIR | inotify.IN_CREATE
        self.inotify.watch(
            self.dirname, mask=checkMask, autoAdd=True,
            callbacks=[_callback])
        subdir = self.dirname.child('test')
        subdir2 = subdir.child('test2')
        subdir3 = subdir2.child('test3')
        d = defer.Deferred()
        subdir3.makedirs()

        someFiles = [subdir.child('file1.dat'),
                     subdir2.child('file2.dat'),
                     subdir3.child('file3.dat')]
        # Add some files in pretty much all the directories so that we
        # see that we process all of them.
        for i, filename in enumerate(someFiles):
            filename.setContent(
                filename.path.encode(sys.getfilesystemencoding()))
        return d
