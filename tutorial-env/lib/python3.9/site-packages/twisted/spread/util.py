# -*- test-case-name: twisted.test.test_pb -*-

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Utility classes for spread.
"""

from zope.interface import implementer

from twisted.internet import defer, interfaces
from twisted.protocols import basic
from twisted.python.failure import Failure
from twisted.spread import pb


class LocalMethod:
    def __init__(self, local, name):
        self.local = local
        self.name = name

    def __call__(self, *args, **kw):
        return self.local.callRemote(self.name, *args, **kw)


class LocalAsRemote:
    """
    A class useful for emulating the effects of remote behavior locally.
    """

    reportAllTracebacks = 1

    def callRemote(self, name, *args, **kw):
        """
        Call a specially-designated local method.

        self.callRemote('x') will first try to invoke a method named
        sync_x and return its result (which should probably be a
        Deferred).  Second, it will look for a method called async_x,
        which will be called and then have its result (or Failure)
        automatically wrapped in a Deferred.
        """
        if hasattr(self, "sync_" + name):
            return getattr(self, "sync_" + name)(*args, **kw)
        try:
            method = getattr(self, "async_" + name)
            return defer.succeed(method(*args, **kw))
        except BaseException:
            f = Failure()
            if self.reportAllTracebacks:
                f.printTraceback()
            return defer.fail(f)

    def remoteMethod(self, name):
        return LocalMethod(self, name)


class LocalAsyncForwarder:
    """
    A class useful for forwarding a locally-defined interface.
    """

    def __init__(self, forwarded, interfaceClass, failWhenNotImplemented=0):
        assert interfaceClass.providedBy(forwarded)
        self.forwarded = forwarded
        self.interfaceClass = interfaceClass
        self.failWhenNotImplemented = failWhenNotImplemented

    def _callMethod(self, method, *args, **kw):
        return getattr(self.forwarded, method)(*args, **kw)

    def callRemote(self, method, *args, **kw):
        if self.interfaceClass.queryDescriptionFor(method):
            result = defer.maybeDeferred(self._callMethod, method, *args, **kw)
            return result
        elif self.failWhenNotImplemented:
            return defer.fail(
                Failure(NotImplementedError, "No Such Method in Interface: %s" % method)
            )
        else:
            return defer.succeed(None)


class Pager:
    """
    I am an object which pages out information.
    """

    def __init__(self, collector, callback=None, *args, **kw):
        """
        Create a pager with a Reference to a remote collector and
        an optional callable to invoke upon completion.
        """
        if callable(callback):
            self.callback = callback
            self.callbackArgs = args
            self.callbackKeyword = kw
        else:
            self.callback = None
        self._stillPaging = 1
        self.collector = collector
        collector.broker.registerPageProducer(self)

    def stillPaging(self):
        """
        (internal) Method called by Broker.
        """
        if not self._stillPaging:
            self.collector.callRemote("endedPaging", pbanswer=False)
            if self.callback is not None:
                self.callback(*self.callbackArgs, **self.callbackKeyword)
        return self._stillPaging

    def sendNextPage(self):
        """
        (internal) Method called by Broker.
        """
        self.collector.callRemote("gotPage", self.nextPage(), pbanswer=False)

    def nextPage(self):
        """
        Override this to return an object to be sent to my collector.
        """
        raise NotImplementedError()

    def stopPaging(self):
        """
        Call this when you're done paging.
        """
        self._stillPaging = 0


class StringPager(Pager):
    """
    A simple pager that splits a string into chunks.
    """

    def __init__(self, collector, st, chunkSize=8192, callback=None, *args, **kw):
        self.string = st
        self.pointer = 0
        self.chunkSize = chunkSize
        Pager.__init__(self, collector, callback, *args, **kw)

    def nextPage(self):
        val = self.string[self.pointer : self.pointer + self.chunkSize]
        self.pointer += self.chunkSize
        if self.pointer >= len(self.string):
            self.stopPaging()
        return val


@implementer(interfaces.IConsumer)
class FilePager(Pager):
    """
    Reads a file in chunks and sends the chunks as they come.
    """

    def __init__(self, collector, fd, callback=None, *args, **kw):
        self.chunks = []
        Pager.__init__(self, collector, callback, *args, **kw)
        self.startProducing(fd)

    def startProducing(self, fd):
        self.deferred = basic.FileSender().beginFileTransfer(fd, self)
        self.deferred.addBoth(lambda x: self.stopPaging())

    def registerProducer(self, producer, streaming):
        self.producer = producer
        if not streaming:
            self.producer.resumeProducing()

    def unregisterProducer(self):
        self.producer = None

    def write(self, chunk):
        self.chunks.append(chunk)

    def sendNextPage(self):
        """
        Get the first chunk read and send it to collector.
        """
        if not self.chunks:
            return
        val = self.chunks.pop(0)
        self.producer.resumeProducing()
        self.collector.callRemote("gotPage", val, pbanswer=False)


# Utility paging stuff.
class CallbackPageCollector(pb.Referenceable):
    """
    I receive pages from the peer. You may instantiate a Pager with a
    remote reference to me. I will call the callback with a list of pages
    once they are all received.
    """

    def __init__(self, callback):
        self.pages = []
        self.callback = callback

    def remote_gotPage(self, page):
        self.pages.append(page)

    def remote_endedPaging(self):
        self.callback(self.pages)


def getAllPages(referenceable, methodName, *args, **kw):
    """
    A utility method that will call a remote method which expects a
    PageCollector as the first argument.
    """
    d = defer.Deferred()
    referenceable.callRemote(methodName, CallbackPageCollector(d.callback), *args, **kw)
    return d
