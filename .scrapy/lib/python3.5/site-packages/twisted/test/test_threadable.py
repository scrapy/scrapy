# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.threadable}.
"""

from __future__ import division, absolute_import

import sys, pickle

try:
    import threading
except ImportError:
    threadingSkip = "Platform lacks thread support"
else:
    threadingSkip = None

from twisted.python.compat import _PY3
from twisted.trial import unittest

from twisted.python import threadable

class TestObject:
    synchronized = ['aMethod']

    x = -1
    y = 1

    def aMethod(self):
        for i in range(10):
            self.x, self.y = self.y, self.x
            self.z = self.x + self.y
            assert self.z == 0, "z == %d, not 0 as expected" % (self.z,)

threadable.synchronize(TestObject)

class SynchronizationTests(unittest.SynchronousTestCase):
    def setUp(self):
        """
        Reduce the CPython check interval so that thread switches happen much
        more often, hopefully exercising more possible race conditions.  Also,
        delay actual test startup until the reactor has been started.
        """
        if _PY3:
            if getattr(sys, 'getswitchinterval', None) is not None:
                self.addCleanup(sys.setswitchinterval, sys.getswitchinterval())
                sys.setswitchinterval(0.0000001)
        else:
            if getattr(sys, 'getcheckinterval', None) is not None:
                self.addCleanup(sys.setcheckinterval, sys.getcheckinterval())
                sys.setcheckinterval(7)


    def test_synchronizedName(self):
        """
        The name of a synchronized method is inaffected by the synchronization
        decorator.
        """
        self.assertEqual("aMethod", TestObject.aMethod.__name__)


    def test_isInIOThread(self):
        """
        L{threadable.isInIOThread} returns C{True} if and only if it is called
        in the same thread as L{threadable.registerAsIOThread}.
        """
        threadable.registerAsIOThread()
        foreignResult = []
        t = threading.Thread(
            target=lambda: foreignResult.append(threadable.isInIOThread()))
        t.start()
        t.join()
        self.assertFalse(
            foreignResult[0], "Non-IO thread reported as IO thread")
        self.assertTrue(
            threadable.isInIOThread(), "IO thread reported as not IO thread")


    def testThreadedSynchronization(self):
        o = TestObject()

        errors = []

        def callMethodLots():
            try:
                for i in range(1000):
                    o.aMethod()
            except AssertionError as e:
                errors.append(str(e))

        threads = []
        for x in range(5):
            t = threading.Thread(target=callMethodLots)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        if errors:
            raise unittest.FailTest(errors)

    if threadingSkip is not None:
        testThreadedSynchronization.skip = threadingSkip
        test_isInIOThread.skip = threadingSkip


    def testUnthreadedSynchronization(self):
        o = TestObject()
        for i in range(1000):
            o.aMethod()



class SerializationTests(unittest.SynchronousTestCase):
    def testPickling(self):
        lock = threadable.XLock()
        lockType = type(lock)
        lockPickle = pickle.dumps(lock)
        newLock = pickle.loads(lockPickle)
        self.assertIsInstance(newLock, lockType)

    if threadingSkip is not None:
        testPickling.skip = threadingSkip


    def testUnpickling(self):
        lockPickle = b'ctwisted.python.threadable\nunpickle_lock\np0\n(tp1\nRp2\n.'
        lock = pickle.loads(lockPickle)
        newPickle = pickle.dumps(lock, 2)
        pickle.loads(newPickle)
