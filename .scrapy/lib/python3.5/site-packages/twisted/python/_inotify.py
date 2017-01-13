# -*- test-case-name: twisted.internet.test.test_inotify -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Very low-level ctypes-based interface to Linux inotify(7).

ctypes and a version of libc which supports inotify system calls are
required.
"""

import ctypes
import ctypes.util



class INotifyError(Exception):
    """
    Unify all the possible exceptions that can be raised by the INotify API.
    """



def init():
    """
    Create an inotify instance and return the associated file descriptor.
    """
    fd = libc.inotify_init()
    if fd < 0:
        raise INotifyError("INotify initialization error.")
    return fd



def add(fd, path, mask):
    """
    Add a watch for the given path to the inotify file descriptor, and return
    the watch descriptor.

    @param fd: The file descriptor returned by C{libc.inotify_init}.
    @type fd: L{int}

    @param path: The path to watch via inotify.
    @type path: L{twisted.python.filepath.FilePath}

    @param mask: Bitmask specifying the events that inotify should monitor.
    @type mask: L{int}
    """
    wd = libc.inotify_add_watch(fd, path.asBytesMode().path, mask)
    if wd < 0:
        raise INotifyError("Failed to add watch on '%r' - (%r)" % (path, wd))
    return wd



def remove(fd, wd):
    """
    Remove the given watch descriptor from the inotify file descriptor.
    """
    # When inotify_rm_watch returns -1 there's an error:
    # The errno for this call can be either one of the following:
    #  EBADF: fd is not a valid file descriptor.
    #  EINVAL: The watch descriptor wd is not valid; or fd is
    #          not an inotify file descriptor.
    #
    # if we can't access the errno here we cannot even raise
    # an exception and we need to ignore the problem, one of
    # the most common cases is when you remove a directory from
    # the filesystem and that directory is observed. When inotify
    # tries to call inotify_rm_watch with a non existing directory
    # either of the 2 errors might come up because the files inside
    # it might have events generated way before they were handled.
    # Unfortunately only ctypes in Python 2.6 supports accessing errno:
    #  http://bugs.python.org/issue1798 and in order to solve
    # the problem for previous versions we need to introduce
    # code that is quite complex:
    #  http://stackoverflow.com/questions/661017/access-to-errno-from-python
    #
    # See #4310 for future resolution of this issue.
    libc.inotify_rm_watch(fd, wd)



def initializeModule(libc):
    """
    Initialize the module, checking if the expected APIs exist and setting the
    argtypes and restype for C{inotify_init}, C{inotify_add_watch}, and
    C{inotify_rm_watch}.
    """
    for function in ("inotify_add_watch", "inotify_init", "inotify_rm_watch"):
        if getattr(libc, function, None) is None:
            raise ImportError("libc6 2.4 or higher needed")
    libc.inotify_init.argtypes = []
    libc.inotify_init.restype = ctypes.c_int

    libc.inotify_rm_watch.argtypes = [
        ctypes.c_int, ctypes.c_int]
    libc.inotify_rm_watch.restype = ctypes.c_int

    libc.inotify_add_watch.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int



name = ctypes.util.find_library('c')
if not name:
    raise ImportError("Can't find C library.")
libc = ctypes.cdll.LoadLibrary(name)
initializeModule(libc)
