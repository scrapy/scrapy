# -*- test-case-name: twisted.python.test_threadable -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A module to provide some very basic threading primitives, such as
synchronization.
"""

from __future__ import division, absolute_import

from functools import wraps

class DummyLock(object):
    """
    Hack to allow locks to be unpickled on an unthreaded system.
    """

    def __reduce__(self):
        return (unpickle_lock, ())



def unpickle_lock():
    if threadingmodule is not None:
        return XLock()
    else:
        return DummyLock()
unpickle_lock.__safe_for_unpickling__ = True



def _synchPre(self):
    if '_threadable_lock' not in self.__dict__:
        _synchLockCreator.acquire()
        if '_threadable_lock' not in self.__dict__:
            self.__dict__['_threadable_lock'] = XLock()
        _synchLockCreator.release()
    self._threadable_lock.acquire()



def _synchPost(self):
    self._threadable_lock.release()



def _sync(klass, function):
    @wraps(function)
    def sync(self, *args, **kwargs):
        _synchPre(self)
        try:
            return function(self, *args, **kwargs)
        finally:
            _synchPost(self)
    return sync



def synchronize(*klasses):
    """
    Make all methods listed in each class' synchronized attribute synchronized.

    The synchronized attribute should be a list of strings, consisting of the
    names of methods that must be synchronized. If we are running in threaded
    mode these methods will be wrapped with a lock.
    """
    if threadingmodule is not None:
        for klass in klasses:
            for methodName in klass.synchronized:
                sync = _sync(klass, klass.__dict__[methodName])
                setattr(klass, methodName, sync)



def init(with_threads=1):
    """Initialize threading.

    Don't bother calling this.  If it needs to happen, it will happen.
    """
    global threaded, _synchLockCreator, XLock

    if with_threads:
        if not threaded:
            if threadingmodule is not None:
                threaded = True

                class XLock(threadingmodule._RLock, object):
                    def __reduce__(self):
                        return (unpickle_lock, ())

                _synchLockCreator = XLock()
            else:
                raise RuntimeError("Cannot initialize threading, platform lacks thread support")
    else:
        if threaded:
            raise RuntimeError("Cannot uninitialize threads")
        else:
            pass



_dummyID = object()
def getThreadID():
    if threadingmodule is None:
        return _dummyID
    return threadingmodule.currentThread().ident



def isInIOThread():
    """Are we in the thread responsible for I/O requests (the event loop)?
    """
    return ioThread == getThreadID()



def registerAsIOThread():
    """Mark the current thread as responsible for I/O requests.
    """
    global ioThread
    ioThread = getThreadID()


ioThread = None
threaded = False
# Define these globals which might be overwritten in init().
_synchLockCreator = None
XLock = None


try:
    import threading as threadingmodule
except ImportError:
    threadingmodule = None
else:
    init(True)



__all__ = ['isInIOThread', 'registerAsIOThread', 'getThreadID', 'XLock']
