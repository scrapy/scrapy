# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorFDSet}.
"""

__metaclass__ = type

import os, socket, traceback

from zope.interface import implementer

from twisted.python.runtime import platform
from twisted.trial.unittest import SkipTest
from twisted.internet.interfaces import IReactorFDSet, IReadDescriptor
from twisted.internet.abstract import FileDescriptor
from twisted.internet.test.reactormixins import ReactorBuilder

# twisted.internet.tcp nicely defines some names with proper values on
# several different platforms.
from twisted.internet.tcp import EINPROGRESS, EWOULDBLOCK


def socketpair():
    serverSocket = socket.socket()
    serverSocket.bind(('127.0.0.1', 0))
    serverSocket.listen(1)
    try:
        client = socket.socket()
        try:
            client.setblocking(False)
            try:
                client.connect(('127.0.0.1', serverSocket.getsockname()[1]))
            except socket.error as e:
                if e.args[0] not in (EINPROGRESS, EWOULDBLOCK):
                    raise
            server, addr = serverSocket.accept()
        except:
            client.close()
            raise
    finally:
        serverSocket.close()

    return client, server


class ReactorFDSetTestsBuilder(ReactorBuilder):
    """
    Builder defining tests relating to L{IReactorFDSet}.
    """
    requiredInterfaces = [IReactorFDSet]

    def _connectedPair(self):
        """
        Return the two sockets which make up a new TCP connection.
        """
        client, server = socketpair()
        self.addCleanup(client.close)
        self.addCleanup(server.close)
        return client, server


    def _simpleSetup(self):
        reactor = self.buildReactor()

        client, server = self._connectedPair()

        fd = FileDescriptor(reactor)
        fd.fileno = client.fileno

        return reactor, fd, server


    def test_addReader(self):
        """
        C{reactor.addReader()} accepts an L{IReadDescriptor} provider and calls
        its C{doRead} method when there may be data available on its C{fileno}.
        """
        reactor, fd, server = self._simpleSetup()

        def removeAndStop():
            reactor.removeReader(fd)
            reactor.stop()
        fd.doRead = removeAndStop
        reactor.addReader(fd)
        server.sendall(b'x')

        # The reactor will only stop if it calls fd.doRead.
        self.runReactor(reactor)
        # Nothing to assert, just be glad we got this far.


    def test_removeReader(self):
        """
        L{reactor.removeReader()} accepts an L{IReadDescriptor} provider
        previously passed to C{reactor.addReader()} and causes it to no longer
        be monitored for input events.
        """
        reactor, fd, server = self._simpleSetup()

        def fail():
            self.fail("doRead should not be called")
        fd.doRead = fail

        reactor.addReader(fd)
        reactor.removeReader(fd)
        server.sendall(b'x')

        # Give the reactor two timed event passes to notice that there's I/O
        # (if it is incorrectly watching for I/O).
        reactor.callLater(0, reactor.callLater, 0, reactor.stop)

        self.runReactor(reactor)
        # Getting here means the right thing happened probably.


    def test_addWriter(self):
        """
        C{reactor.addWriter()} accepts an L{IWriteDescriptor} provider and
        calls its C{doWrite} method when it may be possible to write to its
        C{fileno}.
        """
        reactor, fd, server = self._simpleSetup()

        def removeAndStop():
            reactor.removeWriter(fd)
            reactor.stop()
        fd.doWrite = removeAndStop
        reactor.addWriter(fd)

        self.runReactor(reactor)
        # Getting here is great.


    def _getFDTest(self, kind):
        """
        Helper for getReaders and getWriters tests.
        """
        reactor = self.buildReactor()
        get = getattr(reactor, 'get' + kind + 's')
        add = getattr(reactor, 'add' + kind)
        remove = getattr(reactor, 'remove' + kind)

        client, server = self._connectedPair()

        self.assertNotIn(client, get())
        self.assertNotIn(server, get())

        add(client)
        self.assertIn(client, get())
        self.assertNotIn(server, get())

        remove(client)
        self.assertNotIn(client, get())
        self.assertNotIn(server, get())


    def test_getReaders(self):
        """
        L{IReactorFDSet.getReaders} reflects the additions and removals made
        with L{IReactorFDSet.addReader} and L{IReactorFDSet.removeReader}.
        """
        self._getFDTest('Reader')


    def test_removeWriter(self):
        """
        L{reactor.removeWriter()} accepts an L{IWriteDescriptor} provider
        previously passed to C{reactor.addWriter()} and causes it to no longer
        be monitored for outputability.
        """
        reactor, fd, server = self._simpleSetup()

        def fail():
            self.fail("doWrite should not be called")
        fd.doWrite = fail

        reactor.addWriter(fd)
        reactor.removeWriter(fd)

        # Give the reactor two timed event passes to notice that there's I/O
        # (if it is incorrectly watching for I/O).
        reactor.callLater(0, reactor.callLater, 0, reactor.stop)

        self.runReactor(reactor)
        # Getting here means the right thing happened probably.


    def test_getWriters(self):
        """
        L{IReactorFDSet.getWriters} reflects the additions and removals made
        with L{IReactorFDSet.addWriter} and L{IReactorFDSet.removeWriter}.
        """
        self._getFDTest('Writer')


    def test_removeAll(self):
        """
        C{reactor.removeAll()} removes all registered L{IReadDescriptor}
        providers and all registered L{IWriteDescriptor} providers and returns
        them.
        """
        reactor = self.buildReactor()

        reactor, fd, server = self._simpleSetup()

        fd.doRead = lambda: self.fail("doRead should not be called")
        fd.doWrite = lambda: self.fail("doWrite should not be called")

        server.sendall(b'x')

        reactor.addReader(fd)
        reactor.addWriter(fd)

        removed = reactor.removeAll()

        # Give the reactor two timed event passes to notice that there's I/O
        # (if it is incorrectly watching for I/O).
        reactor.callLater(0, reactor.callLater, 0, reactor.stop)

        self.runReactor(reactor)
        # Getting here means the right thing happened probably.

        self.assertEqual(removed, [fd])


    def test_removedFromReactor(self):
        """
        A descriptor's C{fileno} method should not be called after the
        descriptor has been removed from the reactor.
        """
        reactor = self.buildReactor()
        descriptor = RemovingDescriptor(reactor)
        reactor.callWhenRunning(descriptor.start)
        self.runReactor(reactor)
        self.assertEqual(descriptor.calls, [])


    def test_negativeOneFileDescriptor(self):
        """
        If L{FileDescriptor.fileno} returns C{-1}, the descriptor is removed
        from the reactor.
        """
        reactor = self.buildReactor()

        client, server = self._connectedPair()

        class DisappearingDescriptor(FileDescriptor):
            _fileno = server.fileno()

            _received = b""

            def fileno(self):
                return self._fileno

            def doRead(self):
                self._fileno = -1
                self._received += server.recv(1)
                client.send(b'y')

            def connectionLost(self, reason):
                reactor.stop()

        descriptor = DisappearingDescriptor(reactor)
        reactor.addReader(descriptor)
        client.send(b'x')
        self.runReactor(reactor)
        self.assertEqual(descriptor._received, b"x")


    def test_lostFileDescriptor(self):
        """
        The file descriptor underlying a FileDescriptor may be closed and
        replaced by another at some point.  Bytes which arrive on the new
        descriptor must not be delivered to the FileDescriptor which was
        originally registered with the original descriptor of the same number.

        Practically speaking, this is difficult or impossible to detect.  The
        implementation relies on C{fileno} raising an exception if the original
        descriptor has gone away.  If C{fileno} continues to return the original
        file descriptor value, the reactor may deliver events from that
        descriptor.  This is a best effort attempt to ease certain debugging
        situations.  Applications should not rely on it intentionally.
        """
        reactor = self.buildReactor()

        name = reactor.__class__.__name__
        if name in ('EPollReactor', 'KQueueReactor', 'CFReactor'):
            # Closing a file descriptor immediately removes it from the epoll
            # set without generating a notification.  That means epollreactor
            # will not call any methods on Victim after the close, so there's
            # no chance to notice the socket is no longer valid.
            raise SkipTest("%r cannot detect lost file descriptors" % (name,))

        client, server = self._connectedPair()

        class Victim(FileDescriptor):
            """
            This L{FileDescriptor} will have its socket closed out from under it
            and another socket will take its place.  It will raise a
            socket.error from C{fileno} after this happens (because socket
            objects remember whether they have been closed), so as long as the
            reactor calls the C{fileno} method the problem will be detected.
            """
            def fileno(self):
                return server.fileno()

            def doRead(self):
                raise Exception("Victim.doRead should never be called")

            def connectionLost(self, reason):
                """
                When the problem is detected, the reactor should disconnect this
                file descriptor.  When that happens, stop the reactor so the
                test ends.
                """
                reactor.stop()

        reactor.addReader(Victim())

        # Arrange for the socket to be replaced at some unspecified time.
        # Significantly, this will not be while any I/O processing code is on
        # the stack.  It is something that happens independently and cannot be
        # relied upon to happen at a convenient time, such as within a call to
        # doRead.
        def messItUp():
            newC, newS = self._connectedPair()
            fileno = server.fileno()
            server.close()
            os.dup2(newS.fileno(), fileno)
            newC.send(b"x")
        reactor.callLater(0, messItUp)

        self.runReactor(reactor)

        # If the implementation feels like logging the exception raised by
        # MessedUp.fileno, that's fine.
        self.flushLoggedErrors(socket.error)
    if platform.isWindows():
        test_lostFileDescriptor.skip = (
            "Cannot duplicate socket filenos on Windows")


    def test_connectionLostOnShutdown(self):
        """
        Any file descriptors added to the reactor have their C{connectionLost}
        called when C{reactor.stop} is called.
        """
        reactor = self.buildReactor()

        class DoNothingDescriptor(FileDescriptor):
            def doRead(self):
                return None
            def doWrite(self):
                return None

        client, server = self._connectedPair()

        fd1 = DoNothingDescriptor(reactor)
        fd1.fileno = client.fileno
        fd2 = DoNothingDescriptor(reactor)
        fd2.fileno = server.fileno
        reactor.addReader(fd1)
        reactor.addWriter(fd2)

        reactor.callWhenRunning(reactor.stop)
        self.runReactor(reactor)
        self.assertTrue(fd1.disconnected)
        self.assertTrue(fd2.disconnected)



@implementer(IReadDescriptor)
class RemovingDescriptor(object):
    """
    A read descriptor which removes itself from the reactor as soon as it
    gets a chance to do a read and keeps track of when its own C{fileno}
    method is called.

    @ivar insideReactor: A flag which is true as long as the reactor has
        this descriptor as a reader.

    @ivar calls: A list of the bottom of the call stack for any call to
        C{fileno} when C{insideReactor} is false.
    """


    def __init__(self, reactor):
        self.reactor = reactor
        self.insideReactor = False
        self.calls = []
        self.read, self.write = socketpair()


    def start(self):
        self.insideReactor = True
        self.reactor.addReader(self)
        self.write.send(b'a')


    def logPrefix(self):
        return 'foo'


    def doRead(self):
        self.reactor.removeReader(self)
        self.insideReactor = False
        self.reactor.stop()
        self.read.close()
        self.write.close()


    def fileno(self):
        if not self.insideReactor:
            self.calls.append(traceback.extract_stack(limit=5)[:-1])
        return self.read.fileno()


    def connectionLost(self, reason):
        # Ideally we'd close the descriptors here... but actually
        # connectionLost is never called because we remove ourselves from the
        # reactor before it stops.
        pass

globals().update(ReactorFDSetTestsBuilder.makeTestCaseClasses())
