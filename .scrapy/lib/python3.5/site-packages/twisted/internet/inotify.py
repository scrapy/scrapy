# -*- test-case-name: twisted.internet.test.test_inotify -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module provides support for Twisted to linux inotify API.

In order to use this support, simply do the following (and start a reactor
at some point)::

    from twisted.internet import inotify
    from twisted.python import filepath

    def notify(ignored, filepath, mask):
        \"""
        For historical reasons, an opaque handle is passed as first
        parameter. This object should never be used.

        @param filepath: FilePath on which the event happened.
        @param mask: inotify event as hexadecimal masks
        \"""
        print("event %s on %s" % (
            ', '.join(inotify.humanReadableMask(mask)), filepath))

    notifier = inotify.INotify()
    notifier.startReading()
    notifier.watch(filepath.FilePath("/some/directory"), callbacks=[notify])
    notifier.watch(filepath.FilePath(b"/some/directory2"), callbacks=[notify])

Note that in the above example, a L{FilePath} which is a L{bytes} path name
or L{str} path name may be used.  However, no matter what type of
L{FilePath} is passed to this module, internally the L{FilePath} is
converted to L{bytes} according to L{sys.getfilesystemencoding}.
For any L{FilePath} returned by this module, the caller is responsible for
converting from a L{bytes} path name to a L{str} path name.

@since: 10.1
"""

from __future__ import print_function

import os
import struct

from twisted.internet import fdesc
from twisted.internet.abstract import FileDescriptor
from twisted.python import log, _inotify


# from /usr/src/linux/include/linux/inotify.h

IN_ACCESS = 0x00000001         # File was accessed
IN_MODIFY = 0x00000002         # File was modified
IN_ATTRIB = 0x00000004         # Metadata changed
IN_CLOSE_WRITE = 0x00000008    # Writeable file was closed
IN_CLOSE_NOWRITE = 0x00000010  # Unwriteable file closed
IN_OPEN = 0x00000020           # File was opened
IN_MOVED_FROM = 0x00000040     # File was moved from X
IN_MOVED_TO = 0x00000080       # File was moved to Y
IN_CREATE = 0x00000100         # Subfile was created
IN_DELETE = 0x00000200         # Subfile was delete
IN_DELETE_SELF = 0x00000400    # Self was deleted
IN_MOVE_SELF = 0x00000800      # Self was moved
IN_UNMOUNT = 0x00002000        # Backing fs was unmounted
IN_Q_OVERFLOW = 0x00004000     # Event queued overflowed
IN_IGNORED = 0x00008000        # File was ignored

IN_ONLYDIR = 0x01000000         # only watch the path if it is a directory
IN_DONT_FOLLOW = 0x02000000     # don't follow a sym link
IN_MASK_ADD = 0x20000000        # add to the mask of an already existing watch
IN_ISDIR = 0x40000000           # event occurred against dir
IN_ONESHOT = 0x80000000         # only send event once

IN_CLOSE = IN_CLOSE_WRITE | IN_CLOSE_NOWRITE     # closes
IN_MOVED = IN_MOVED_FROM | IN_MOVED_TO           # moves
IN_CHANGED = IN_MODIFY | IN_ATTRIB               # changes

IN_WATCH_MASK = (IN_MODIFY | IN_ATTRIB |
                 IN_CREATE | IN_DELETE |
                 IN_DELETE_SELF | IN_MOVE_SELF |
                 IN_UNMOUNT | IN_MOVED_FROM | IN_MOVED_TO)


_FLAG_TO_HUMAN = [
    (IN_ACCESS, 'access'),
    (IN_MODIFY, 'modify'),
    (IN_ATTRIB, 'attrib'),
    (IN_CLOSE_WRITE, 'close_write'),
    (IN_CLOSE_NOWRITE, 'close_nowrite'),
    (IN_OPEN, 'open'),
    (IN_MOVED_FROM, 'moved_from'),
    (IN_MOVED_TO, 'moved_to'),
    (IN_CREATE, 'create'),
    (IN_DELETE, 'delete'),
    (IN_DELETE_SELF, 'delete_self'),
    (IN_MOVE_SELF, 'move_self'),
    (IN_UNMOUNT, 'unmount'),
    (IN_Q_OVERFLOW, 'queue_overflow'),
    (IN_IGNORED, 'ignored'),
    (IN_ONLYDIR, 'only_dir'),
    (IN_DONT_FOLLOW, 'dont_follow'),
    (IN_MASK_ADD, 'mask_add'),
    (IN_ISDIR, 'is_dir'),
    (IN_ONESHOT, 'one_shot')
]



def humanReadableMask(mask):
    """
    Auxiliary function that converts a hexadecimal mask into a series
    of human readable flags.
    """
    s = []
    for k, v in _FLAG_TO_HUMAN:
        if k & mask:
            s.append(v)
    return s



class _Watch(object):
    """
    Watch object that represents a Watch point in the filesystem. The
    user should let INotify to create these objects

    @ivar path: The path over which this watch point is monitoring
    @ivar mask: The events monitored by this watchpoint
    @ivar autoAdd: Flag that determines whether this watch point
        should automatically add created subdirectories
    @ivar callbacks: L{list} of callback functions that will be called
        when an event occurs on this watch.
    """
    def __init__(self, path, mask=IN_WATCH_MASK, autoAdd=False,
                 callbacks=None):
        self.path = path.asBytesMode()
        self.mask = mask
        self.autoAdd = autoAdd
        if callbacks is None:
            callbacks = []
        self.callbacks = callbacks


    def _notify(self, filepath, events):
        """
        Callback function used by L{INotify} to dispatch an event.
        """
        filepath = filepath.asBytesMode()
        for callback in self.callbacks:
            callback(self, filepath, events)



class INotify(FileDescriptor, object):
    """
    The INotify file descriptor, it basically does everything related
    to INotify, from reading to notifying watch points.

    @ivar _buffer: a L{bytes} containing the data read from the inotify fd.

    @ivar _watchpoints: a L{dict} that maps from inotify watch ids to
        watchpoints objects

    @ivar _watchpaths: a L{dict} that maps from watched paths to the
        inotify watch ids
    """
    _inotify = _inotify

    def __init__(self, reactor=None):
        FileDescriptor.__init__(self, reactor=reactor)

        # Smart way to allow parametrization of libc so I can override
        # it and test for the system errors.
        self._fd = self._inotify.init()

        fdesc.setNonBlocking(self._fd)
        fdesc._setCloseOnExec(self._fd)

        # The next 2 lines are needed to have self.loseConnection()
        # to call connectionLost() on us. Since we already created the
        # fd that talks to inotify we want to be notified even if we
        # haven't yet started reading.
        self.connected = 1
        self._writeDisconnected = True

        self._buffer = b''
        self._watchpoints = {}
        self._watchpaths = {}


    def _addWatch(self, path, mask, autoAdd, callbacks):
        """
        Private helper that abstracts the use of ctypes.

        Calls the internal inotify API and checks for any errors after the
        call. If there's an error L{INotify._addWatch} can raise an
        INotifyError. If there's no error it proceeds creating a watchpoint and
        adding a watchpath for inverse lookup of the file descriptor from the
        path.
        """
        path = path.asBytesMode()
        wd = self._inotify.add(self._fd, path, mask)

        iwp = _Watch(path, mask, autoAdd, callbacks)

        self._watchpoints[wd] = iwp
        self._watchpaths[path] = wd

        return wd


    def _rmWatch(self, wd):
        """
        Private helper that abstracts the use of ctypes.

        Calls the internal inotify API to remove an fd from inotify then
        removes the corresponding watchpoint from the internal mapping together
        with the file descriptor from the watchpath.
        """
        self._inotify.remove(self._fd, wd)
        iwp = self._watchpoints.pop(wd)
        self._watchpaths.pop(iwp.path)


    def connectionLost(self, reason):
        """
        Release the inotify file descriptor and do the necessary cleanup
        """
        FileDescriptor.connectionLost(self, reason)
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError as e:
                log.err(e, "Couldn't close INotify file descriptor.")


    def fileno(self):
        """
        Get the underlying file descriptor from this inotify observer.
        Required by L{abstract.FileDescriptor} subclasses.
        """
        return self._fd


    def doRead(self):
        """
        Read some data from the observed file descriptors
        """
        fdesc.readFromFD(self._fd, self._doRead)


    def _doRead(self, in_):
        """
        Work on the data just read from the file descriptor.
        """
        self._buffer += in_
        while len(self._buffer) >= 16:

            wd, mask, cookie, size = struct.unpack("=LLLL", self._buffer[0:16])

            if size:
                name = self._buffer[16:16 + size].rstrip(b'\0')
            else:
                name = None

            self._buffer = self._buffer[16 + size:]

            try:
                iwp = self._watchpoints[wd]
            except KeyError:
                continue

            path = iwp.path.asBytesMode()
            if name:
                path = path.child(name)
            iwp._notify(path, mask)

            if (iwp.autoAdd and mask & IN_ISDIR and mask & IN_CREATE):
                # mask & IN_ISDIR already guarantees that the path is a
                # directory. There's no way you can get here without a
                # directory anyway, so no point in checking for that again.
                new_wd = self.watch(
                    path, mask=iwp.mask, autoAdd=True,
                    callbacks=iwp.callbacks
                )
                # This is very very very hacky and I'd rather not do this but
                # we have no other alternative that is less hacky other than
                # surrender.  We use callLater because we don't want to have
                # too many events waiting while we process these subdirs, we
                # must always answer events as fast as possible or the overflow
                # might come.
                self.reactor.callLater(0,
                    self._addChildren, self._watchpoints[new_wd])
            if mask & IN_DELETE_SELF:
                self._rmWatch(wd)


    def _addChildren(self, iwp):
        """
        This is a very private method, please don't even think about using it.

        Note that this is a fricking hack... it's because we cannot be fast
        enough in adding a watch to a directory and so we basically end up
        getting here too late if some operations have already been going on in
        the subdir, we basically need to catchup.  This eventually ends up
        meaning that we generate double events, your app must be resistant.
        """
        try:
            listdir = iwp.path.children()
        except OSError:
            # Somebody or something (like a test) removed this directory while
            # we were in the callLater(0...) waiting. It doesn't make sense to
            # process it anymore
            return

        # note that it's true that listdir will only see the subdirs inside
        # path at the moment of the call but path is monitored already so if
        # something is created we will receive an event.
        for f in listdir:
            # It's a directory, watch it and then add its children
            if f.isdir():
                wd = self.watch(
                    f, mask=iwp.mask, autoAdd=True,
                    callbacks=iwp.callbacks
                )
                iwp._notify(f, IN_ISDIR|IN_CREATE)
                # now f is watched, we can add its children the callLater is to
                # avoid recursion
                self.reactor.callLater(0,
                    self._addChildren, self._watchpoints[wd])

            # It's a file and we notify it.
            if f.isfile():
                iwp._notify(f, IN_CREATE|IN_CLOSE_WRITE)


    def watch(self, path, mask=IN_WATCH_MASK, autoAdd=False,
              callbacks=None, recursive=False):
        """
        Watch the 'mask' events in given path. Can raise C{INotifyError} when
        there's a problem while adding a directory.

        @param path: The path needing monitoring
        @type path: L{FilePath}

        @param mask: The events that should be watched
        @type mask: L{int}

        @param autoAdd: if True automatically add newly created
                        subdirectories
        @type autoAdd: L{bool}

        @param callbacks: A list of callbacks that should be called
                          when an event happens in the given path.
                          The callback should accept 3 arguments:
                          (ignored, filepath, mask)
        @type callbacks: L{list} of callables

        @param recursive: Also add all the subdirectories in this path
        @type recursive: L{bool}
        """
        if recursive:
            # This behavior is needed to be compatible with the windows
            # interface for filesystem changes:
            # http://msdn.microsoft.com/en-us/library/aa365465(VS.85).aspx
            # ReadDirectoryChangesW can do bWatchSubtree so it doesn't
            # make sense to implement this at a higher abstraction
            # level when other platforms support it already
            for child in path.walk():
                if child.isdir():
                    self.watch(child, mask, autoAdd, callbacks,
                               recursive=False)
        else:
            wd = self._isWatched(path)
            if wd:
                return wd

            mask = mask | IN_DELETE_SELF # need this to remove the watch

            return self._addWatch(path, mask, autoAdd, callbacks)


    def ignore(self, path):
        """
        Remove the watch point monitoring the given path

        @param path: The path that should be ignored
        @type path: L{FilePath}
        """
        path = path.asBytesMode()
        wd = self._isWatched(path)
        if wd is None:
            raise KeyError("%r is not watched" % (path,))
        else:
            self._rmWatch(wd)


    def _isWatched(self, path):
        """
        Helper function that checks if the path is already monitored
        and returns its watchdescriptor if so or None otherwise.

        @param path: The path that should be checked
        @type path: L{FilePath}
        """
        path = path.asBytesMode()
        return self._watchpaths.get(path, None)


INotifyError = _inotify.INotifyError


__all__ = ["INotify", "humanReadableMask", "IN_WATCH_MASK", "IN_ACCESS",
           "IN_MODIFY", "IN_ATTRIB", "IN_CLOSE_NOWRITE", "IN_CLOSE_WRITE",
           "IN_OPEN", "IN_MOVED_FROM", "IN_MOVED_TO", "IN_CREATE",
           "IN_DELETE", "IN_DELETE_SELF", "IN_MOVE_SELF", "IN_UNMOUNT",
           "IN_Q_OVERFLOW", "IN_IGNORED", "IN_ONLYDIR", "IN_DONT_FOLLOW",
           "IN_MASK_ADD", "IN_ISDIR", "IN_ONESHOT", "IN_CLOSE",
           "IN_MOVED", "IN_CHANGED"]
