# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Whitebox tests for L{twisted.internet.abstract.FileDescriptor}.
"""

from __future__ import division, absolute_import

from zope.interface.verify import verifyClass

from twisted.internet.abstract import FileDescriptor
from twisted.internet.interfaces import IPushProducer
from twisted.trial.unittest import SynchronousTestCase



class MemoryFile(FileDescriptor):
    """
    A L{FileDescriptor} customization which writes to a Python list in memory
    with certain limitations.

    @ivar _written: A C{list} of C{bytes} which have been accepted as written.

    @ivar _freeSpace: A C{int} giving the number of bytes which will be accepted
        by future writes.
    """
    connected = True

    def __init__(self):
        FileDescriptor.__init__(self, reactor=object())
        self._written = []
        self._freeSpace = 0


    def startWriting(self):
        pass


    def stopWriting(self):
        pass


    def writeSomeData(self, data):
        """
        Copy at most C{self._freeSpace} bytes from C{data} into C{self._written}.

        @return: A C{int} indicating how many bytes were copied from C{data}.
        """
        acceptLength = min(self._freeSpace, len(data))
        if acceptLength:
            self._freeSpace -= acceptLength
            self._written.append(data[:acceptLength])
        return acceptLength



class FileDescriptorTests(SynchronousTestCase):
    """
    Tests for L{FileDescriptor}.
    """
    def test_writeWithUnicodeRaisesException(self):
        """
        L{FileDescriptor.write} doesn't accept unicode data.
        """
        fileDescriptor = FileDescriptor(reactor=object())
        self.assertRaises(TypeError, fileDescriptor.write, u'foo')


    def test_writeSequenceWithUnicodeRaisesException(self):
        """
        L{FileDescriptor.writeSequence} doesn't accept unicode data.
        """
        fileDescriptor = FileDescriptor(reactor=object())
        self.assertRaises(
            TypeError, fileDescriptor.writeSequence, [b'foo', u'bar', b'baz'])


    def test_implementInterfaceIPushProducer(self):
        """
        L{FileDescriptor} should implement L{IPushProducer}.
        """
        self.assertTrue(verifyClass(IPushProducer, FileDescriptor))



class WriteDescriptorTests(SynchronousTestCase):
    """
    Tests for L{FileDescriptor}'s implementation of L{IWriteDescriptor}.
    """
    def test_kernelBufferFull(self):
        """
        When L{FileDescriptor.writeSomeData} returns C{0} to indicate no more
        data can be written immediately, L{FileDescriptor.doWrite} returns
        L{None}.
        """
        descriptor = MemoryFile()
        descriptor.write(b"hello, world")
        self.assertIsNone(descriptor.doWrite())
