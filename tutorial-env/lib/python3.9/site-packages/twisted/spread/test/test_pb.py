# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for Perspective Broker module.

TODO: update protocol level tests to use new connection API, leaving
only specific tests for old API.
"""

# issue1195 TODOs: replace pump.pump() with something involving Deferreds.
# Clean up warning suppression.


import gc
import os
import sys
import time
import weakref
from collections import deque
from io import BytesIO as StringIO
from typing import Dict

from zope.interface import Interface, implementer

from twisted.cred import checkers, credentials, portal
from twisted.cred.error import UnauthorizedLogin, UnhandledCredentials
from twisted.internet import address, main, protocol, reactor
from twisted.internet.defer import Deferred, gatherResults, succeed
from twisted.internet.error import ConnectionRefusedError
from twisted.protocols.policies import WrappingFactory
from twisted.python import failure, log
from twisted.python.compat import iterbytes
from twisted.spread import jelly, pb, publish, util
from twisted.test.proto_helpers import _FakeConnector
from twisted.trial import unittest


class Dummy(pb.Viewable):
    def view_doNothing(self, user):
        if isinstance(user, DummyPerspective):
            return "hello world!"
        else:
            return "goodbye, cruel world!"


class DummyPerspective(pb.Avatar):
    """
    An L{IPerspective} avatar which will be used in some tests.
    """

    def perspective_getDummyViewPoint(self):
        return Dummy()


@implementer(portal.IRealm)
class DummyRealm:
    def requestAvatar(self, avatarId, mind, *interfaces):
        for iface in interfaces:
            if iface is pb.IPerspective:
                return iface, DummyPerspective(avatarId), lambda: None


class IOPump:
    """
    Utility to pump data between clients and servers for protocol testing.

    Perhaps this is a utility worthy of being in protocol.py?
    """

    def __init__(self, client, server, clientIO, serverIO):
        self.client = client
        self.server = server
        self.clientIO = clientIO
        self.serverIO = serverIO

    def flush(self):
        """
        Pump until there is no more input or output or until L{stop} is called.
        This does not run any timers, so don't use it with any code that calls
        reactor.callLater.
        """
        # failsafe timeout
        self._stop = False
        timeout = time.time() + 5
        while not self._stop and self.pump():
            if time.time() > timeout:
                return

    def stop(self):
        """
        Stop a running L{flush} operation, even if data remains to be
        transferred.
        """
        self._stop = True

    def pump(self):
        """
        Move data back and forth.

        Returns whether any data was moved.
        """
        self.clientIO.seek(0)
        self.serverIO.seek(0)
        cData = self.clientIO.read()
        sData = self.serverIO.read()
        self.clientIO.seek(0)
        self.serverIO.seek(0)
        self.clientIO.truncate()
        self.serverIO.truncate()
        self.client.transport._checkProducer()
        self.server.transport._checkProducer()
        for byte in iterbytes(cData):
            self.server.dataReceived(byte)
        for byte in iterbytes(sData):
            self.client.dataReceived(byte)
        if cData or sData:
            return 1
        else:
            return 0


def connectServerAndClient(test, clientFactory, serverFactory):
    """
    Create a server and a client and connect the two with an
    L{IOPump}.

    @param test: the test case where the client and server will be
        used.
    @type test: L{twisted.trial.unittest.TestCase}

    @param clientFactory: The factory that creates the client object.
    @type clientFactory: L{twisted.spread.pb.PBClientFactory}

    @param serverFactory: The factory that creates the server object.
    @type serverFactory: L{twisted.spread.pb.PBServerFactory}

    @return: a 3-tuple of (client, server, pump)
    @rtype: (L{twisted.spread.pb.Broker}, L{twisted.spread.pb.Broker},
        L{IOPump})
    """
    addr = ("127.0.0.1",)
    clientBroker = clientFactory.buildProtocol(addr)
    serverBroker = serverFactory.buildProtocol(addr)

    clientTransport = StringIO()
    serverTransport = StringIO()

    clientBroker.makeConnection(protocol.FileWrapper(clientTransport))
    serverBroker.makeConnection(protocol.FileWrapper(serverTransport))
    pump = IOPump(clientBroker, serverBroker, clientTransport, serverTransport)

    def maybeDisconnect(broker):
        if not broker.disconnected:
            broker.connectionLost(failure.Failure(main.CONNECTION_DONE))

    def disconnectClientFactory():
        # There's no connector, just a FileWrapper mediated by the
        # IOPump.  Fortunately PBClientFactory.clientConnectionLost
        # doesn't do anything with the connector so we can get away
        # with passing None here.
        clientFactory.clientConnectionLost(
            connector=None, reason=failure.Failure(main.CONNECTION_DONE)
        )

    test.addCleanup(maybeDisconnect, clientBroker)
    test.addCleanup(maybeDisconnect, serverBroker)
    test.addCleanup(disconnectClientFactory)
    # Establish the connection
    pump.pump()
    return clientBroker, serverBroker, pump


class _ReconnectingFakeConnectorState:
    """
    Manages connection notifications for a
    L{_ReconnectingFakeConnector} instance.

    @ivar notifications: pending L{Deferreds} that will fire when the
        L{_ReconnectingFakeConnector}'s connect method is called
    """

    def __init__(self):
        self.notifications = deque()

    def notifyOnConnect(self):
        """
        Connection notification.

        @return: A L{Deferred} that fires when this instance's
            L{twisted.internet.interfaces.IConnector.connect} method
            is called.
        @rtype: L{Deferred}
        """
        notifier = Deferred()
        self.notifications.appendleft(notifier)
        return notifier

    def notifyAll(self):
        """
        Fire all pending notifications.
        """
        while self.notifications:
            self.notifications.pop().callback(self)


class _ReconnectingFakeConnector(_FakeConnector):
    """
    A fake L{IConnector} that can fire L{Deferred}s when its
    C{connect} method is called.
    """

    def __init__(self, address, state):
        """
        @param address: An L{IAddress} provider that represents this
            connector's destination.
        @type address: An L{IAddress} provider.

        @param state: The state instance
        @type state: L{_ReconnectingFakeConnectorState}
        """
        super().__init__(address)
        self._state = state

    def connect(self):
        """
        A C{connect} implementation that calls C{reconnectCallback}
        """
        super().connect()
        self._state.notifyAll()


def connectedServerAndClient(test, realm=None):
    """
    Connect a client and server L{Broker} together with an L{IOPump}

    @param realm: realm to use, defaulting to a L{DummyRealm}

    @returns: a 3-tuple (client, server, pump).
    """
    realm = realm or DummyRealm()
    checker = checkers.InMemoryUsernamePasswordDatabaseDontUse(guest=b"guest")
    serverFactory = pb.PBServerFactory(portal.Portal(realm, [checker]))
    clientFactory = pb.PBClientFactory()
    return connectServerAndClient(test, clientFactory, serverFactory)


class SimpleRemote(pb.Referenceable):
    def remote_thunk(self, arg):
        self.arg = arg
        return arg + 1

    def remote_knuth(self, arg):
        raise Exception()


class NestedRemote(pb.Referenceable):
    def remote_getSimple(self):
        return SimpleRemote()


class SimpleCopy(pb.Copyable):
    def __init__(self):
        self.x = 1
        self.y = {"Hello": "World"}
        self.z = ["test"]


class SimpleLocalCopy(pb.RemoteCopy):
    pass


pb.setUnjellyableForClass(SimpleCopy, SimpleLocalCopy)


class SimpleFactoryCopy(pb.Copyable):
    """
    @cvar allIDs: hold every created instances of this class.
    @type allIDs: C{dict}
    """

    allIDs: Dict[int, "SimpleFactoryCopy"] = {}

    def __init__(self, id):
        self.id = id
        SimpleFactoryCopy.allIDs[id] = self


def createFactoryCopy(state):
    """
    Factory of L{SimpleFactoryCopy}, getting a created instance given the
    C{id} found in C{state}.
    """
    stateId = state.get("id", None)
    if stateId is None:
        raise RuntimeError(f"factory copy state has no 'id' member {repr(state)}")
    if stateId not in SimpleFactoryCopy.allIDs:
        raise RuntimeError(f"factory class has no ID: {SimpleFactoryCopy.allIDs}")
    inst = SimpleFactoryCopy.allIDs[stateId]
    if not inst:
        raise RuntimeError("factory method found no object with id")
    return inst


pb.setUnjellyableFactoryForClass(SimpleFactoryCopy, createFactoryCopy)


class NestedCopy(pb.Referenceable):
    def remote_getCopy(self):
        return SimpleCopy()

    def remote_getFactory(self, value):
        return SimpleFactoryCopy(value)


class SimpleCache(pb.Cacheable):
    def __init___(self):
        self.x = 1
        self.y = {"Hello": "World"}
        self.z = ["test"]


class NestedComplicatedCache(pb.Referenceable):
    def __init__(self):
        self.c = VeryVeryComplicatedCacheable()

    def remote_getCache(self):
        return self.c


class VeryVeryComplicatedCacheable(pb.Cacheable):
    def __init__(self):
        self.x = 1
        self.y = 2
        self.foo = 3

    def setFoo4(self):
        self.foo = 4
        self.observer.callRemote("foo", 4)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        self.observer = observer
        return {"x": self.x, "y": self.y, "foo": self.foo}

    def stoppedObserving(self, perspective, observer):
        log.msg("stopped observing")
        observer.callRemote("end")
        if observer == self.observer:
            self.observer = None


class RatherBaroqueCache(pb.RemoteCache):
    def observe_foo(self, newFoo):
        self.foo = newFoo

    def observe_end(self):
        log.msg("the end of things")


pb.setUnjellyableForClass(VeryVeryComplicatedCacheable, RatherBaroqueCache)


class SimpleLocalCache(pb.RemoteCache):
    def setCopyableState(self, state):
        self.__dict__.update(state)

    def checkMethod(self):
        return self.check

    def checkSelf(self):
        return self

    def check(self):
        return 1


pb.setUnjellyableForClass(SimpleCache, SimpleLocalCache)


class NestedCache(pb.Referenceable):
    def __init__(self):
        self.x = SimpleCache()

    def remote_getCache(self):
        return [self.x, self.x]

    def remote_putCache(self, cache):
        return self.x is cache


class Observable(pb.Referenceable):
    def __init__(self):
        self.observers = []

    def remote_observe(self, obs):
        self.observers.append(obs)

    def remote_unobserve(self, obs):
        self.observers.remove(obs)

    def notify(self, obj):
        for observer in self.observers:
            observer.callRemote("notify", self, obj)


class DeferredRemote(pb.Referenceable):
    def __init__(self):
        self.run = 0

    def runMe(self, arg):
        self.run = arg
        return arg + 1

    def dontRunMe(self, arg):
        assert 0, "shouldn't have been run!"

    def remote_doItLater(self):
        """
        Return a L{Deferred} to be fired on client side. When fired,
        C{self.runMe} is called.
        """
        d = Deferred()
        d.addCallbacks(self.runMe, self.dontRunMe)
        self.d = d
        return d


class Observer(pb.Referenceable):
    notified = 0
    obj = None

    def remote_notify(self, other, obj):
        self.obj = obj
        self.notified = self.notified + 1
        other.callRemote("unobserve", self)


class NewStyleCopy(pb.Copyable, pb.RemoteCopy):
    def __init__(self, s):
        self.s = s


pb.setUnjellyableForClass(NewStyleCopy, NewStyleCopy)


class NewStyleCopy2(pb.Copyable, pb.RemoteCopy):
    allocated = 0
    initialized = 0
    value = 1

    def __new__(self):
        NewStyleCopy2.allocated += 1
        inst = object.__new__(self)
        inst.value = 2
        return inst

    def __init__(self):
        NewStyleCopy2.initialized += 1


pb.setUnjellyableForClass(NewStyleCopy2, NewStyleCopy2)


class NewStyleCacheCopy(pb.Cacheable, pb.RemoteCache):
    def getStateToCacheAndObserveFor(self, perspective, observer):
        return self.__dict__


pb.setUnjellyableForClass(NewStyleCacheCopy, NewStyleCacheCopy)


class Echoer(pb.Root):
    def remote_echo(self, st):
        return st

    def remote_echoWithKeywords(self, st, **kw):
        return (st, kw)


class CachedReturner(pb.Root):
    def __init__(self, cache):
        self.cache = cache

    def remote_giveMeCache(self, st):
        return self.cache


class NewStyleTests(unittest.SynchronousTestCase):
    def setUp(self):
        """
        Create a pb server using L{Echoer} protocol and connect a client to it.
        """
        self.serverFactory = pb.PBServerFactory(Echoer())
        clientFactory = pb.PBClientFactory()
        client, self.server, self.pump = connectServerAndClient(
            test=self, clientFactory=clientFactory, serverFactory=self.serverFactory
        )
        self.ref = self.successResultOf(clientFactory.getRootObject())

    def tearDown(self):
        """
        Close client and server connections, reset values of L{NewStyleCopy2}
        class variables.
        """
        NewStyleCopy2.allocated = 0
        NewStyleCopy2.initialized = 0
        NewStyleCopy2.value = 1

    def test_newStyle(self):
        """
        Create a new style object, send it over the wire, and check the result.
        """
        orig = NewStyleCopy("value")
        d = self.ref.callRemote("echo", orig)
        self.pump.flush()

        def cb(res):
            self.assertIsInstance(res, NewStyleCopy)
            self.assertEqual(res.s, "value")
            self.assertFalse(res is orig)  # no cheating :)

        d.addCallback(cb)
        return d

    def test_alloc(self):
        """
        Send a new style object and check the number of allocations.
        """
        orig = NewStyleCopy2()
        self.assertEqual(NewStyleCopy2.allocated, 1)
        self.assertEqual(NewStyleCopy2.initialized, 1)
        d = self.ref.callRemote("echo", orig)
        self.pump.flush()

        def cb(res):
            # Receiving the response creates a third one on the way back
            self.assertIsInstance(res, NewStyleCopy2)
            self.assertEqual(res.value, 2)
            self.assertEqual(NewStyleCopy2.allocated, 3)
            self.assertEqual(NewStyleCopy2.initialized, 1)
            self.assertIsNot(res, orig)  # No cheating :)

        # Sending the object creates a second one on the far side
        d.addCallback(cb)
        return d

    def test_newStyleWithKeywords(self):
        """
        Create a new style object with keywords,
        send it over the wire, and check the result.
        """
        orig = NewStyleCopy("value1")
        d = self.ref.callRemote(
            "echoWithKeywords", orig, keyword1="one", keyword2="two"
        )
        self.pump.flush()

        def cb(res):
            self.assertIsInstance(res, tuple)
            self.assertIsInstance(res[0], NewStyleCopy)
            self.assertIsInstance(res[1], dict)
            self.assertEqual(res[0].s, "value1")
            self.assertIsNot(res[0], orig)
            self.assertEqual(res[1], {"keyword1": "one", "keyword2": "two"})

        d.addCallback(cb)
        return d


class ConnectionNotifyServerFactory(pb.PBServerFactory):
    """
    A server factory which stores the last connection and fires a
    L{Deferred} on connection made. This factory can handle only one
    client connection.

    @ivar protocolInstance: the last protocol instance.
    @type protocolInstance: C{pb.Broker}

    @ivar connectionMade: the deferred fired upon connection.
    @type connectionMade: C{Deferred}
    """

    protocolInstance = None

    def __init__(self, root):
        """
        Initialize the factory.
        """
        pb.PBServerFactory.__init__(self, root)
        self.connectionMade = Deferred()

    def clientConnectionMade(self, protocol):
        """
        Store the protocol and fire the connection deferred.
        """
        self.protocolInstance = protocol
        d, self.connectionMade = self.connectionMade, None
        if d is not None:
            d.callback(None)


class NewStyleCachedTests(unittest.TestCase):
    def setUp(self):
        """
        Create a pb server using L{CachedReturner} protocol and connect a
        client to it.
        """
        self.orig = NewStyleCacheCopy()
        self.orig.s = "value"
        self.server = reactor.listenTCP(
            0, ConnectionNotifyServerFactory(CachedReturner(self.orig))
        )
        clientFactory = pb.PBClientFactory()
        reactor.connectTCP("localhost", self.server.getHost().port, clientFactory)

        def gotRoot(ref):
            self.ref = ref

        d1 = clientFactory.getRootObject().addCallback(gotRoot)
        d2 = self.server.factory.connectionMade
        return gatherResults([d1, d2])

    def tearDown(self):
        """
        Close client and server connections.
        """
        self.server.factory.protocolInstance.transport.loseConnection()
        self.ref.broker.transport.loseConnection()
        return self.server.stopListening()

    def test_newStyleCache(self):
        """
        A new-style cacheable object can be retrieved and re-retrieved over a
        single connection.  The value of an attribute of the cacheable can be
        accessed on the receiving side.
        """
        d = self.ref.callRemote("giveMeCache", self.orig)

        def cb(res, again):
            self.assertIsInstance(res, NewStyleCacheCopy)
            self.assertEqual("value", res.s)
            # no cheating :)
            self.assertIsNot(self.orig, res)

            if again:
                # Save a reference so it stays alive for the rest of this test
                self.res = res
                # And ask for it again to exercise the special re-jelly logic in
                # Cacheable.
                return self.ref.callRemote("giveMeCache", self.orig)

        d.addCallback(cb, True)
        d.addCallback(cb, False)
        return d


class BrokerTests(unittest.TestCase):
    thunkResult = None

    def tearDown(self):
        try:
            # from RemotePublished.getFileName
            os.unlink("None-None-TESTING.pub")
        except OSError:
            pass

    def thunkErrorBad(self, error):
        self.fail(f"This should cause a return value, not {error}")

    def thunkResultGood(self, result):
        self.thunkResult = result

    def thunkErrorGood(self, tb):
        pass

    def thunkResultBad(self, result):
        self.fail(f"This should cause an error, not {result}")

    def test_reference(self):
        c, s, pump = connectedServerAndClient(test=self)

        class X(pb.Referenceable):
            def remote_catch(self, arg):
                self.caught = arg

        class Y(pb.Referenceable):
            def remote_throw(self, a, b):
                a.callRemote("catch", b)

        s.setNameForLocal("y", Y())
        y = c.remoteForName("y")
        x = X()
        z = X()
        y.callRemote("throw", x, z)
        pump.pump()
        pump.pump()
        pump.pump()
        self.assertIs(x.caught, z, "X should have caught Z")

        # make sure references to remote methods are equals
        self.assertEqual(y.remoteMethod("throw"), y.remoteMethod("throw"))

    def test_result(self):
        c, s, pump = connectedServerAndClient(test=self)
        for x, y in (c, s), (s, c):
            # test reflexivity
            foo = SimpleRemote()
            x.setNameForLocal("foo", foo)
            bar = y.remoteForName("foo")
            self.expectedThunkResult = 8
            bar.callRemote("thunk", self.expectedThunkResult - 1).addCallbacks(
                self.thunkResultGood, self.thunkErrorBad
            )
            # Send question.
            pump.pump()
            # Send response.
            pump.pump()
            # Shouldn't require any more pumping than that...
            self.assertEqual(
                self.thunkResult, self.expectedThunkResult, "result wasn't received."
            )

    def refcountResult(self, result):
        self.nestedRemote = result

    def test_tooManyRefs(self):
        l = []
        e = []
        c, s, pump = connectedServerAndClient(test=self)
        foo = NestedRemote()
        s.setNameForLocal("foo", foo)
        x = c.remoteForName("foo")
        for igno in range(pb.MAX_BROKER_REFS + 10):
            if s.transport.closed or c.transport.closed:
                break
            x.callRemote("getSimple").addCallbacks(l.append, e.append)
            pump.pump()
        expected = pb.MAX_BROKER_REFS - 1
        self.assertTrue(s.transport.closed, "transport was not closed")
        self.assertEqual(len(l), expected, f"expected {expected} got {len(l)}")

    def test_copy(self):
        c, s, pump = connectedServerAndClient(test=self)
        foo = NestedCopy()
        s.setNameForLocal("foo", foo)
        x = c.remoteForName("foo")
        x.callRemote("getCopy").addCallbacks(self.thunkResultGood, self.thunkErrorBad)
        pump.pump()
        pump.pump()
        self.assertEqual(self.thunkResult.x, 1)
        self.assertEqual(self.thunkResult.y["Hello"], "World")
        self.assertEqual(self.thunkResult.z[0], "test")

    def test_observe(self):
        c, s, pump = connectedServerAndClient(test=self)

        # this is really testing the comparison between remote objects, to make
        # sure that you can *UN*observe when you have an observer architecture.
        a = Observable()
        b = Observer()
        s.setNameForLocal("a", a)
        ra = c.remoteForName("a")
        ra.callRemote("observe", b)
        pump.pump()
        a.notify(1)
        pump.pump()
        pump.pump()
        a.notify(10)
        pump.pump()
        pump.pump()
        self.assertIsNotNone(b.obj, "didn't notify")
        self.assertEqual(b.obj, 1, "notified too much")

    def test_defer(self):
        c, s, pump = connectedServerAndClient(test=self)
        d = DeferredRemote()
        s.setNameForLocal("d", d)
        e = c.remoteForName("d")
        pump.pump()
        pump.pump()
        results = []
        e.callRemote("doItLater").addCallback(results.append)
        pump.pump()
        pump.pump()
        self.assertFalse(d.run, "Deferred method run too early.")
        d.d.callback(5)
        self.assertEqual(d.run, 5, "Deferred method run too late.")
        pump.pump()
        pump.pump()
        self.assertEqual(results[0], 6, "Incorrect result.")

    def test_refcount(self):
        c, s, pump = connectedServerAndClient(test=self)
        foo = NestedRemote()
        s.setNameForLocal("foo", foo)
        bar = c.remoteForName("foo")
        bar.callRemote("getSimple").addCallbacks(
            self.refcountResult, self.thunkErrorBad
        )

        # send question
        pump.pump()
        # send response
        pump.pump()

        # delving into internal structures here, because GC is sort of
        # inherently internal.
        rluid = self.nestedRemote.luid
        self.assertIn(rluid, s.localObjects)
        del self.nestedRemote
        # nudge the gc
        if sys.hexversion >= 0x2000000:
            gc.collect()
        # try to nudge the GC even if we can't really
        pump.pump()
        pump.pump()
        pump.pump()
        self.assertNotIn(rluid, s.localObjects)

    def test_cache(self):
        c, s, pump = connectedServerAndClient(test=self)
        obj = NestedCache()
        obj2 = NestedComplicatedCache()
        vcc = obj2.c
        s.setNameForLocal("obj", obj)
        s.setNameForLocal("xxx", obj2)
        o2 = c.remoteForName("obj")
        o3 = c.remoteForName("xxx")
        coll = []
        o2.callRemote("getCache").addCallback(coll.append).addErrback(coll.append)
        o2.callRemote("getCache").addCallback(coll.append).addErrback(coll.append)
        complex = []
        o3.callRemote("getCache").addCallback(complex.append)
        o3.callRemote("getCache").addCallback(complex.append)
        pump.flush()
        # `worst things first'
        self.assertEqual(complex[0].x, 1)
        self.assertEqual(complex[0].y, 2)
        self.assertEqual(complex[0].foo, 3)

        vcc.setFoo4()
        pump.flush()
        self.assertEqual(complex[0].foo, 4)
        self.assertEqual(len(coll), 2)
        cp = coll[0][0]
        self.assertIdentical(
            cp.checkMethod().__self__, cp, "potential refcounting issue"
        )
        self.assertIdentical(cp.checkSelf(), cp, "other potential refcounting issue")
        col2 = []
        o2.callRemote("putCache", cp).addCallback(col2.append)
        pump.flush()
        # The objects were the same (testing lcache identity)
        self.assertTrue(col2[0])
        # test equality of references to methods
        self.assertEqual(o2.remoteMethod("getCache"), o2.remoteMethod("getCache"))

        # now, refcounting (similar to testRefCount)
        luid = cp.luid
        baroqueLuid = complex[0].luid
        self.assertIn(luid, s.remotelyCachedObjects, "remote cache doesn't have it")
        del coll
        del cp
        pump.flush()
        del complex
        del col2
        # extra nudge...
        pump.flush()
        # del vcc.observer
        # nudge the gc
        if sys.hexversion >= 0x2000000:
            gc.collect()
        # try to nudge the GC even if we can't really
        pump.flush()
        # The GC is done with it.
        self.assertNotIn(luid, s.remotelyCachedObjects, "Server still had it after GC")
        self.assertNotIn(luid, c.locallyCachedObjects, "Client still had it after GC")
        self.assertNotIn(
            baroqueLuid, s.remotelyCachedObjects, "Server still had complex after GC"
        )
        self.assertNotIn(
            baroqueLuid, c.locallyCachedObjects, "Client still had complex after GC"
        )
        self.assertIsNone(vcc.observer, "observer was not removed")

    def test_publishable(self):
        try:
            os.unlink("None-None-TESTING.pub")  # from RemotePublished.getFileName
        except OSError:
            pass  # Sometimes it's not there.
        c, s, pump = connectedServerAndClient(test=self)
        foo = GetPublisher()
        # foo.pub.timestamp = 1.0
        s.setNameForLocal("foo", foo)
        bar = c.remoteForName("foo")
        accum = []
        bar.callRemote("getPub").addCallbacks(accum.append, self.thunkErrorBad)
        pump.flush()
        obj = accum.pop()
        self.assertEqual(obj.activateCalled, 1)
        self.assertEqual(obj.isActivated, 1)
        self.assertEqual(obj.yayIGotPublished, 1)
        # timestamp's dirty, we don't have a cache file
        self.assertEqual(obj._wasCleanWhenLoaded, 0)
        c, s, pump = connectedServerAndClient(test=self)
        s.setNameForLocal("foo", foo)
        bar = c.remoteForName("foo")
        bar.callRemote("getPub").addCallbacks(accum.append, self.thunkErrorBad)
        pump.flush()
        obj = accum.pop()
        # timestamp's clean, our cache file is up-to-date
        self.assertEqual(obj._wasCleanWhenLoaded, 1)

    def gotCopy(self, val):
        self.thunkResult = val.id

    def test_factoryCopy(self):
        c, s, pump = connectedServerAndClient(test=self)
        ID = 99
        obj = NestedCopy()
        s.setNameForLocal("foo", obj)
        x = c.remoteForName("foo")
        x.callRemote("getFactory", ID).addCallbacks(self.gotCopy, self.thunkResultBad)
        pump.pump()
        pump.pump()
        pump.pump()
        self.assertEqual(
            self.thunkResult,
            ID,
            f"ID not correct on factory object {self.thunkResult}",
        )


bigString = b"helloworld" * 50

callbackArgs = None
callbackKeyword = None


def finishedCallback(*args, **kw):
    global callbackArgs, callbackKeyword
    callbackArgs = args
    callbackKeyword = kw


class Pagerizer(pb.Referenceable):
    def __init__(self, callback, *args, **kw):
        self.callback, self.args, self.kw = callback, args, kw

    def remote_getPages(self, collector):
        util.StringPager(
            collector, bigString, 100, self.callback, *self.args, **self.kw
        )
        self.args = self.kw = None


class FilePagerizer(pb.Referenceable):
    pager = None

    def __init__(self, filename, callback, *args, **kw):
        self.filename = filename
        self.callback, self.args, self.kw = callback, args, kw

    def remote_getPages(self, collector):
        self.pager = util.FilePager(
            collector, open(self.filename, "rb"), self.callback, *self.args, **self.kw
        )
        self.args = self.kw = None


class PagingTests(unittest.TestCase):
    """
    Test pb objects sending data by pages.
    """

    def setUp(self):
        """
        Create a file used to test L{util.FilePager}.
        """
        self.filename = self.mktemp()
        with open(self.filename, "wb") as f:
            f.write(bigString)

    def test_pagingWithCallback(self):
        """
        Test L{util.StringPager}, passing a callback to fire when all pages
        are sent.
        """
        c, s, pump = connectedServerAndClient(test=self)
        s.setNameForLocal("foo", Pagerizer(finishedCallback, "hello", value=10))
        x = c.remoteForName("foo")
        l = []
        util.getAllPages(x, "getPages").addCallback(l.append)
        while not l:
            pump.pump()
        self.assertEqual(
            b"".join(l[0]), bigString, "Pages received not equal to pages sent!"
        )
        self.assertEqual(callbackArgs, ("hello",), "Completed callback not invoked")
        self.assertEqual(
            callbackKeyword, {"value": 10}, "Completed callback not invoked"
        )

    def test_pagingWithoutCallback(self):
        """
        Test L{util.StringPager} without a callback.
        """
        c, s, pump = connectedServerAndClient(test=self)
        s.setNameForLocal("foo", Pagerizer(None))
        x = c.remoteForName("foo")
        l = []
        util.getAllPages(x, "getPages").addCallback(l.append)
        while not l:
            pump.pump()
        self.assertEqual(
            b"".join(l[0]), bigString, "Pages received not equal to pages sent!"
        )

    def test_emptyFilePaging(self):
        """
        Test L{util.FilePager}, sending an empty file.
        """
        filenameEmpty = self.mktemp()
        open(filenameEmpty, "w").close()
        c, s, pump = connectedServerAndClient(test=self)
        pagerizer = FilePagerizer(filenameEmpty, None)
        s.setNameForLocal("bar", pagerizer)
        x = c.remoteForName("bar")
        l = []
        util.getAllPages(x, "getPages").addCallback(l.append)
        ttl = 10
        while not l and ttl > 0:
            pump.pump()
            ttl -= 1
        if not ttl:
            self.fail("getAllPages timed out")
        self.assertEqual(b"".join(l[0]), b"", "Pages received not equal to pages sent!")

    def test_filePagingWithCallback(self):
        """
        Test L{util.FilePager}, passing a callback to fire when all pages
        are sent, and verify that the pager doesn't keep chunks in memory.
        """
        c, s, pump = connectedServerAndClient(test=self)
        pagerizer = FilePagerizer(self.filename, finishedCallback, "frodo", value=9)
        s.setNameForLocal("bar", pagerizer)
        x = c.remoteForName("bar")
        l = []
        util.getAllPages(x, "getPages").addCallback(l.append)
        while not l:
            pump.pump()
        self.assertEqual(
            b"".join(l[0]), bigString, "Pages received not equal to pages sent!"
        )
        self.assertEqual(callbackArgs, ("frodo",), "Completed callback not invoked")
        self.assertEqual(
            callbackKeyword, {"value": 9}, "Completed callback not invoked"
        )
        self.assertEqual(pagerizer.pager.chunks, [])

    def test_filePagingWithoutCallback(self):
        """
        Test L{util.FilePager} without a callback.
        """
        c, s, pump = connectedServerAndClient(test=self)
        pagerizer = FilePagerizer(self.filename, None)
        s.setNameForLocal("bar", pagerizer)
        x = c.remoteForName("bar")
        l = []
        util.getAllPages(x, "getPages").addCallback(l.append)
        while not l:
            pump.pump()
        self.assertEqual(
            b"".join(l[0]), bigString, "Pages received not equal to pages sent!"
        )
        self.assertEqual(pagerizer.pager.chunks, [])


class DumbPublishable(publish.Publishable):
    def getStateToPublish(self):
        return {"yayIGotPublished": 1}


class DumbPub(publish.RemotePublished):
    def activated(self):
        self.activateCalled = 1


class GetPublisher(pb.Referenceable):
    def __init__(self):
        self.pub = DumbPublishable("TESTING")

    def remote_getPub(self):
        return self.pub


pb.setUnjellyableForClass(DumbPublishable, DumbPub)


class DisconnectionTests(unittest.TestCase):
    """
    Test disconnection callbacks.
    """

    def error(self, *args):
        raise RuntimeError(f"I shouldn't have been called: {args}")

    def gotDisconnected(self):
        """
        Called on broker disconnect.
        """
        self.gotCallback = 1

    def objectDisconnected(self, o):
        """
        Called on RemoteReference disconnect.
        """
        self.assertEqual(o, self.remoteObject)
        self.objectCallback = 1

    def test_badSerialization(self):
        c, s, pump = connectedServerAndClient(test=self)
        pump.pump()
        s.setNameForLocal("o", BadCopySet())
        g = c.remoteForName("o")
        l = []
        g.callRemote("setBadCopy", BadCopyable()).addErrback(l.append)
        pump.flush()
        self.assertEqual(len(l), 1)

    def test_disconnection(self):
        c, s, pump = connectedServerAndClient(test=self)
        pump.pump()
        s.setNameForLocal("o", SimpleRemote())

        # get a client reference to server object
        r = c.remoteForName("o")
        pump.pump()
        pump.pump()
        pump.pump()

        # register and then unregister disconnect callbacks
        # making sure they get unregistered
        c.notifyOnDisconnect(self.error)
        self.assertIn(self.error, c.disconnects)
        c.dontNotifyOnDisconnect(self.error)
        self.assertNotIn(self.error, c.disconnects)

        r.notifyOnDisconnect(self.error)
        self.assertIn(r._disconnected, c.disconnects)
        self.assertIn(self.error, r.disconnectCallbacks)
        r.dontNotifyOnDisconnect(self.error)
        self.assertNotIn(r._disconnected, c.disconnects)
        self.assertNotIn(self.error, r.disconnectCallbacks)

        # register disconnect callbacks
        c.notifyOnDisconnect(self.gotDisconnected)
        r.notifyOnDisconnect(self.objectDisconnected)
        self.remoteObject = r

        # disconnect
        c.connectionLost(failure.Failure(main.CONNECTION_DONE))
        self.assertTrue(self.gotCallback)
        self.assertTrue(self.objectCallback)


class FreakOut(Exception):
    pass


class BadCopyable(pb.Copyable):
    def getStateToCopyFor(self, p):
        raise FreakOut()


class BadCopySet(pb.Referenceable):
    def remote_setBadCopy(self, bc):
        return None


class LocalRemoteTest(util.LocalAsRemote):
    reportAllTracebacks = 0

    def sync_add1(self, x):
        return x + 1

    def async_add(self, x=0, y=1):
        return x + y

    def async_fail(self):
        raise RuntimeError()


@implementer(pb.IPerspective)
class MyPerspective(pb.Avatar):
    """
    @ivar loggedIn: set to C{True} when the avatar is logged in.
    @type loggedIn: C{bool}

    @ivar loggedOut: set to C{True} when the avatar is logged out.
    @type loggedOut: C{bool}
    """

    loggedIn = loggedOut = False

    def __init__(self, avatarId):
        self.avatarId = avatarId

    def perspective_getAvatarId(self):
        """
        Return the avatar identifier which was used to access this avatar.
        """
        return self.avatarId

    def perspective_getViewPoint(self):
        return MyView()

    def perspective_add(self, a, b):
        """
        Add the given objects and return the result.  This is a method
        unavailable on L{Echoer}, so it can only be invoked by authenticated
        users who received their avatar from L{TestRealm}.
        """
        return a + b

    def logout(self):
        self.loggedOut = True


class TestRealm:
    """
    A realm which repeatedly gives out a single instance of L{MyPerspective}
    for non-anonymous logins and which gives out a new instance of L{Echoer}
    for each anonymous login.

    @ivar lastPerspective: The L{MyPerspective} most recently created and
        returned from C{requestAvatar}.

    @ivar perspectiveFactory: A one-argument callable which will be used to
        create avatars to be returned from C{requestAvatar}.
    """

    perspectiveFactory = MyPerspective

    lastPerspective = None

    def requestAvatar(self, avatarId, mind, interface):
        """
        Verify that the mind and interface supplied have the expected values
        (this should really be done somewhere else, like inside a test method)
        and return an avatar appropriate for the given identifier.
        """
        assert interface == pb.IPerspective
        assert mind == "BRAINS!"
        if avatarId is checkers.ANONYMOUS:
            return pb.IPerspective, Echoer(), lambda: None
        else:
            self.lastPerspective = self.perspectiveFactory(avatarId)
            self.lastPerspective.loggedIn = True
            return (pb.IPerspective, self.lastPerspective, self.lastPerspective.logout)


class MyView(pb.Viewable):
    def view_check(self, user):
        return isinstance(user, MyPerspective)


class LeakyRealm(TestRealm):
    """
    A realm which hangs onto a reference to the mind object in its logout
    function.
    """

    def __init__(self, mindEater):
        """
        Create a L{LeakyRealm}.

        @param mindEater: a callable that will be called with the C{mind}
        object when it is available
        """
        self._mindEater = mindEater

    def requestAvatar(self, avatarId, mind, interface):
        self._mindEater(mind)
        persp = self.perspectiveFactory(avatarId)
        return (pb.IPerspective, persp, lambda: (mind, persp.logout()))


class NewCredLeakTests(unittest.TestCase):
    """
    Tests to try to trigger memory leaks.
    """

    def test_logoutLeak(self):
        """
        The server does not leak a reference when the client disconnects
        suddenly, even if the cred logout function forms a reference cycle with
        the perspective.
        """
        # keep a weak reference to the mind object, which we can verify later
        # evaluates to None, thereby ensuring the reference leak is fixed.
        self.mindRef = None

        def setMindRef(mind):
            self.mindRef = weakref.ref(mind)

        clientBroker, serverBroker, pump = connectedServerAndClient(
            test=self, realm=LeakyRealm(setMindRef)
        )

        # log in from the client
        connectionBroken = []
        root = clientBroker.remoteForName("root")
        d = root.callRemote("login", b"guest")

        def cbResponse(x):
            challenge, challenger = x
            mind = SimpleRemote()
            return challenger.callRemote(
                "respond", pb.respond(challenge, b"guest"), mind
            )

        d.addCallback(cbResponse)

        def connectionLost(_):
            pump.stop()  # don't try to pump data anymore - it won't work
            connectionBroken.append(1)
            serverBroker.connectionLost(failure.Failure(RuntimeError("boom")))

        d.addCallback(connectionLost)

        # flush out the response and connectionLost
        pump.flush()
        self.assertEqual(connectionBroken, [1])

        # and check for lingering references - requestAvatar sets mindRef
        # to a weakref to the mind; this object should be gc'd, and thus
        # the ref should return None
        gc.collect()
        self.assertIsNone(self.mindRef())


class NewCredTests(unittest.TestCase):
    """
    Tests related to the L{twisted.cred} support in PB.
    """

    def setUp(self):
        """
        Create a portal with no checkers and wrap it around a simple test
        realm.  Set up a PB server on a TCP port which serves perspectives
        using that portal.
        """
        self.realm = TestRealm()
        self.portal = portal.Portal(self.realm)
        self.serverFactory = ConnectionNotifyServerFactory(self.portal)
        self.clientFactory = pb.PBClientFactory()

    def establishClientAndServer(self, _ignored=None):
        """
        Connect a client obtained from C{clientFactory} and a server
        obtained from the current server factory via an L{IOPump},
        then assign them to the appropriate instance variables

        @ivar clientFactory: the broker client factory
        @ivar clientFactory: L{pb.PBClientFactory} instance

        @ivar client: the client broker
        @type client: L{pb.Broker}

        @ivar server: the server broker
        @type server: L{pb.Broker}

        @ivar pump: the IOPump connecting the client and server
        @type pump: L{IOPump}

        @ivar connector: A connector whose connect method recreates
            the above instance variables
        @type connector: L{twisted.internet.base.IConnector}
        """
        self.client, self.server, self.pump = connectServerAndClient(
            self, self.clientFactory, self.serverFactory
        )

        self.connectorState = _ReconnectingFakeConnectorState()
        self.connector = _ReconnectingFakeConnector(
            address.IPv4Address("TCP", "127.0.0.1", 4321), self.connectorState
        )
        self.connectorState.notifyOnConnect().addCallback(self.establishClientAndServer)

    def completeClientLostConnection(
        self, reason=failure.Failure(main.CONNECTION_DONE)
    ):
        """
        Asserts that the client broker's transport was closed and then
        mimics the event loop by calling the broker's connectionLost
        callback with C{reason}, followed by C{self.clientFactory}'s
        C{clientConnectionLost}

        @param reason: (optional) the reason to pass to the client
            broker's connectionLost callback
        @type reason: L{Failure}
        """
        self.assertTrue(self.client.transport.closed)
        # simulate the reactor calling back the client's
        # connectionLost after the loseConnection implied by
        # clientFactory.disconnect
        self.client.connectionLost(reason)
        self.clientFactory.clientConnectionLost(self.connector, reason)

    def test_getRootObject(self):
        """
        Assert that L{PBClientFactory.getRootObject}'s Deferred fires with
        a L{RemoteReference}, and that disconnecting it runs its
        disconnection callbacks.
        """
        self.establishClientAndServer()
        rootObjDeferred = self.clientFactory.getRootObject()

        def gotRootObject(rootObj):
            self.assertIsInstance(rootObj, pb.RemoteReference)
            return rootObj

        def disconnect(rootObj):
            disconnectedDeferred = Deferred()
            rootObj.notifyOnDisconnect(disconnectedDeferred.callback)
            self.clientFactory.disconnect()

            self.completeClientLostConnection()

            return disconnectedDeferred

        rootObjDeferred.addCallback(gotRootObject)
        rootObjDeferred.addCallback(disconnect)

        return rootObjDeferred

    def test_deadReferenceError(self):
        """
        Test that when a connection is lost, calling a method on a
        RemoteReference obtained from it raises L{DeadReferenceError}.
        """
        self.establishClientAndServer()
        rootObjDeferred = self.clientFactory.getRootObject()

        def gotRootObject(rootObj):
            disconnectedDeferred = Deferred()
            rootObj.notifyOnDisconnect(disconnectedDeferred.callback)

            def lostConnection(ign):
                self.assertRaises(pb.DeadReferenceError, rootObj.callRemote, "method")

            disconnectedDeferred.addCallback(lostConnection)
            self.clientFactory.disconnect()

            self.completeClientLostConnection()

            return disconnectedDeferred

        return rootObjDeferred.addCallback(gotRootObject)

    def test_clientConnectionLost(self):
        """
        Test that if the L{reconnecting} flag is passed with a True value then
        a remote call made from a disconnection notification callback gets a
        result successfully.
        """

        class ReconnectOnce(pb.PBClientFactory):
            reconnectedAlready = False

            def clientConnectionLost(self, connector, reason):
                reconnecting = not self.reconnectedAlready
                self.reconnectedAlready = True
                result = pb.PBClientFactory.clientConnectionLost(
                    self, connector, reason, reconnecting
                )
                if reconnecting:
                    connector.connect()
                return result

        self.clientFactory = ReconnectOnce()
        self.establishClientAndServer()

        rootObjDeferred = self.clientFactory.getRootObject()

        def gotRootObject(rootObj):
            self.assertIsInstance(rootObj, pb.RemoteReference)

            d = Deferred()
            rootObj.notifyOnDisconnect(d.callback)
            # request a disconnection
            self.clientFactory.disconnect()
            self.completeClientLostConnection()

            def disconnected(ign):
                d = self.clientFactory.getRootObject()

                def gotAnotherRootObject(anotherRootObj):
                    self.assertIsInstance(anotherRootObj, pb.RemoteReference)
                    d = Deferred()
                    anotherRootObj.notifyOnDisconnect(d.callback)
                    self.clientFactory.disconnect()
                    self.completeClientLostConnection()
                    return d

                return d.addCallback(gotAnotherRootObject)

            return d.addCallback(disconnected)

        return rootObjDeferred.addCallback(gotRootObject)

    def test_immediateClose(self):
        """
        Test that if a Broker loses its connection without receiving any bytes,
        it doesn't raise any exceptions or log any errors.
        """
        self.establishClientAndServer()
        serverProto = self.serverFactory.buildProtocol(("127.0.0.1", 12345))
        serverProto.makeConnection(protocol.FileWrapper(StringIO()))
        serverProto.connectionLost(failure.Failure(main.CONNECTION_DONE))

    def test_loginConnectionRefused(self):
        """
        L{PBClientFactory.login} returns a L{Deferred} which is errbacked
        with the L{ConnectionRefusedError} if the underlying connection is
        refused.
        """
        clientFactory = pb.PBClientFactory()
        loginDeferred = clientFactory.login(
            credentials.UsernamePassword(b"foo", b"bar")
        )
        clientFactory.clientConnectionFailed(
            None,
            failure.Failure(
                ConnectionRefusedError("Test simulated refused connection")
            ),
        )
        return self.assertFailure(loginDeferred, ConnectionRefusedError)

    def test_loginLogout(self):
        """
        Test that login can be performed with IUsernamePassword credentials and
        that when the connection is dropped the avatar is logged out.
        """
        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(user=b"pass")
        )
        creds = credentials.UsernamePassword(b"user", b"pass")

        # NOTE: real code probably won't need anything where we have the
        # "BRAINS!" argument, passing None is fine. We just do it here to
        # test that it is being passed. It is used to give additional info to
        # the realm to aid perspective creation, if you don't need that,
        # ignore it.
        mind = "BRAINS!"

        loginCompleted = Deferred()

        d = self.clientFactory.login(creds, mind)

        def cbLogin(perspective):
            self.assertTrue(self.realm.lastPerspective.loggedIn)
            self.assertIsInstance(perspective, pb.RemoteReference)
            return loginCompleted

        def cbDisconnect(ignored):
            self.clientFactory.disconnect()
            self.completeClientLostConnection()

        d.addCallback(cbLogin)
        d.addCallback(cbDisconnect)

        def cbLogout(ignored):
            self.assertTrue(self.realm.lastPerspective.loggedOut)

        d.addCallback(cbLogout)

        self.establishClientAndServer()
        self.pump.flush()
        # The perspective passed to cbLogin has gone out of scope.
        # Ensure its __del__ runs...
        gc.collect()
        # ...and send its decref message to the server
        self.pump.flush()
        # Now allow the client to disconnect.
        loginCompleted.callback(None)
        return d

    def test_logoutAfterDecref(self):
        """
        If a L{RemoteReference} to an L{IPerspective} avatar is decrefed and
        there remain no other references to the avatar on the server, the
        avatar is garbage collected and the logout method called.
        """
        loggedOut = Deferred()

        class EventPerspective(pb.Avatar):
            """
            An avatar which fires a Deferred when it is logged out.
            """

            def __init__(self, avatarId):
                pass

            def logout(self):
                loggedOut.callback(None)

        self.realm.perspectiveFactory = EventPerspective

        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(foo=b"bar")
        )

        d = self.clientFactory.login(
            credentials.UsernamePassword(b"foo", b"bar"), "BRAINS!"
        )

        def cbLoggedIn(avatar):
            # Just wait for the logout to happen, as it should since the
            # reference to the avatar will shortly no longer exists.
            return loggedOut

        d.addCallback(cbLoggedIn)

        def cbLoggedOut(ignored):
            # Verify that the server broker's _localCleanup dict isn't growing
            # without bound.
            self.assertEqual(self.serverFactory.protocolInstance._localCleanup, {})

        d.addCallback(cbLoggedOut)

        self.establishClientAndServer()

        # complete authentication
        self.pump.flush()
        # _PortalAuthChallenger and our Avatar should be dead by now;
        # force a collection to trigger their __del__s
        gc.collect()
        # push their decref messages through
        self.pump.flush()
        return d

    def test_concurrentLogin(self):
        """
        Two different correct login attempts can be made on the same root
        object at the same time and produce two different resulting avatars.
        """
        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(foo=b"bar", baz=b"quux")
        )

        firstLogin = self.clientFactory.login(
            credentials.UsernamePassword(b"foo", b"bar"), "BRAINS!"
        )
        secondLogin = self.clientFactory.login(
            credentials.UsernamePassword(b"baz", b"quux"), "BRAINS!"
        )
        d = gatherResults([firstLogin, secondLogin])

        def cbLoggedIn(result):
            (first, second) = result
            return gatherResults(
                [first.callRemote("getAvatarId"), second.callRemote("getAvatarId")]
            )

        d.addCallback(cbLoggedIn)

        def cbAvatarIds(x):
            first, second = x
            self.assertEqual(first, b"foo")
            self.assertEqual(second, b"baz")

        d.addCallback(cbAvatarIds)

        self.establishClientAndServer()
        self.pump.flush()

        return d

    def test_badUsernamePasswordLogin(self):
        """
        Test that a login attempt with an invalid user or invalid password
        fails in the appropriate way.
        """
        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(user=b"pass")
        )

        firstLogin = self.clientFactory.login(
            credentials.UsernamePassword(b"nosuchuser", b"pass")
        )
        secondLogin = self.clientFactory.login(
            credentials.UsernamePassword(b"user", b"wrongpass")
        )

        self.assertFailure(firstLogin, UnauthorizedLogin)
        self.assertFailure(secondLogin, UnauthorizedLogin)
        d = gatherResults([firstLogin, secondLogin])

        def cleanup(ignore):
            errors = self.flushLoggedErrors(UnauthorizedLogin)
            self.assertEqual(len(errors), 2)

        d.addCallback(cleanup)

        self.establishClientAndServer()
        self.pump.flush()

        return d

    def test_anonymousLogin(self):
        """
        Verify that a PB server using a portal configured with a checker which
        allows IAnonymous credentials can be logged into using IAnonymous
        credentials.
        """
        self.portal.registerChecker(checkers.AllowAnonymousAccess())
        d = self.clientFactory.login(credentials.Anonymous(), "BRAINS!")

        def cbLoggedIn(perspective):
            return perspective.callRemote("echo", 123)

        d.addCallback(cbLoggedIn)

        d.addCallback(self.assertEqual, 123)

        self.establishClientAndServer()
        self.pump.flush()
        return d

    def test_anonymousLoginNotPermitted(self):
        """
        Verify that without an anonymous checker set up, anonymous login is
        rejected.
        """
        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(user="pass")
        )
        d = self.clientFactory.login(credentials.Anonymous(), "BRAINS!")
        self.assertFailure(d, UnhandledCredentials)

        def cleanup(ignore):
            errors = self.flushLoggedErrors(UnhandledCredentials)
            self.assertEqual(len(errors), 1)

        d.addCallback(cleanup)

        self.establishClientAndServer()
        self.pump.flush()

        return d

    def test_anonymousLoginWithMultipleCheckers(self):
        """
        Like L{test_anonymousLogin} but against a portal with a checker for
        both IAnonymous and IUsernamePassword.
        """
        self.portal.registerChecker(checkers.AllowAnonymousAccess())
        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(user=b"pass")
        )
        d = self.clientFactory.login(credentials.Anonymous(), "BRAINS!")

        def cbLogin(perspective):
            return perspective.callRemote("echo", 123)

        d.addCallback(cbLogin)

        d.addCallback(self.assertEqual, 123)

        self.establishClientAndServer()
        self.pump.flush()

        return d

    def test_authenticatedLoginWithMultipleCheckers(self):
        """
        Like L{test_anonymousLoginWithMultipleCheckers} but check that
        username/password authentication works.
        """
        self.portal.registerChecker(checkers.AllowAnonymousAccess())
        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(user=b"pass")
        )
        d = self.clientFactory.login(
            credentials.UsernamePassword(b"user", b"pass"), "BRAINS!"
        )

        def cbLogin(perspective):
            return perspective.callRemote("add", 100, 23)

        d.addCallback(cbLogin)

        d.addCallback(self.assertEqual, 123)

        self.establishClientAndServer()
        self.pump.flush()

        return d

    def test_view(self):
        """
        Verify that a viewpoint can be retrieved after authenticating with
        cred.
        """
        self.portal.registerChecker(
            checkers.InMemoryUsernamePasswordDatabaseDontUse(user=b"pass")
        )
        d = self.clientFactory.login(
            credentials.UsernamePassword(b"user", b"pass"), "BRAINS!"
        )

        def cbLogin(perspective):
            return perspective.callRemote("getViewPoint")

        d.addCallback(cbLogin)

        def cbView(viewpoint):
            return viewpoint.callRemote("check")

        d.addCallback(cbView)

        d.addCallback(self.assertTrue)

        self.establishClientAndServer()
        self.pump.flush()

        return d


@implementer(pb.IPerspective)
class NonSubclassingPerspective:
    def __init__(self, avatarId):
        pass

    # IPerspective implementation
    def perspectiveMessageReceived(self, broker, message, args, kwargs):
        args = broker.unserialize(args, self)
        kwargs = broker.unserialize(kwargs, self)
        return broker.serialize((message, args, kwargs))

    # Methods required by TestRealm
    def logout(self):
        self.loggedOut = True


class NSPTests(unittest.TestCase):
    """
    Tests for authentication against a realm where the L{IPerspective}
    implementation is not a subclass of L{Avatar}.
    """

    def setUp(self):
        self.realm = TestRealm()
        self.realm.perspectiveFactory = NonSubclassingPerspective
        self.portal = portal.Portal(self.realm)
        self.checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        self.checker.addUser(b"user", b"pass")
        self.portal.registerChecker(self.checker)
        self.factory = WrappingFactory(pb.PBServerFactory(self.portal))
        self.port = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
        self.addCleanup(self.port.stopListening)
        self.portno = self.port.getHost().port

    def test_NSP(self):
        """
        An L{IPerspective} implementation which does not subclass
        L{Avatar} can expose remote methods for the client to call.
        """
        factory = pb.PBClientFactory()
        d = factory.login(credentials.UsernamePassword(b"user", b"pass"), "BRAINS!")
        reactor.connectTCP("127.0.0.1", self.portno, factory)
        d.addCallback(lambda p: p.callRemote("ANYTHING", "here", bar="baz"))
        d.addCallback(self.assertEqual, ("ANYTHING", ("here",), {"bar": "baz"}))

        def cleanup(ignored):
            factory.disconnect()
            for p in self.factory.protocols:
                p.transport.loseConnection()

        d.addCallback(cleanup)
        return d


class IForwarded(Interface):
    """
    Interface used for testing L{util.LocalAsyncForwarder}.
    """

    def forwardMe():
        """
        Simple synchronous method.
        """

    def forwardDeferred():
        """
        Simple asynchronous method.
        """


@implementer(IForwarded)
class Forwarded:
    """
    Test implementation of L{IForwarded}.

    @ivar forwarded: set if C{forwardMe} is called.
    @type forwarded: C{bool}
    @ivar unforwarded: set if C{dontForwardMe} is called.
    @type unforwarded: C{bool}
    """

    forwarded = False
    unforwarded = False

    def forwardMe(self):
        """
        Set a local flag to test afterwards.
        """
        self.forwarded = True

    def dontForwardMe(self):
        """
        Set a local flag to test afterwards. This should not be called as it's
        not in the interface.
        """
        self.unforwarded = True

    def forwardDeferred(self):
        """
        Asynchronously return C{True}.
        """
        return succeed(True)


class SpreadUtilTests(unittest.TestCase):
    """
    Tests for L{twisted.spread.util}.
    """

    def test_sync(self):
        """
        Call a synchronous method of a L{util.LocalAsRemote} object and check
        the result.
        """
        o = LocalRemoteTest()
        self.assertEqual(o.callRemote("add1", 2), 3)

    def test_async(self):
        """
        Call an asynchronous method of a L{util.LocalAsRemote} object and check
        the result.
        """
        o = LocalRemoteTest()
        o = LocalRemoteTest()
        d = o.callRemote("add", 2, y=4)
        self.assertIsInstance(d, Deferred)
        d.addCallback(self.assertEqual, 6)
        return d

    def test_asyncFail(self):
        """
        Test an asynchronous failure on a remote method call.
        """
        o = LocalRemoteTest()
        d = o.callRemote("fail")

        def eb(f):
            self.assertIsInstance(f, failure.Failure)
            f.trap(RuntimeError)

        d.addCallbacks(lambda res: self.fail("supposed to fail"), eb)
        return d

    def test_remoteMethod(self):
        """
        Test the C{remoteMethod} facility of L{util.LocalAsRemote}.
        """
        o = LocalRemoteTest()
        m = o.remoteMethod("add1")
        self.assertEqual(m(3), 4)

    def test_localAsyncForwarder(self):
        """
        Test a call to L{util.LocalAsyncForwarder} using L{Forwarded} local
        object.
        """
        f = Forwarded()
        lf = util.LocalAsyncForwarder(f, IForwarded)
        lf.callRemote("forwardMe")
        self.assertTrue(f.forwarded)
        lf.callRemote("dontForwardMe")
        self.assertFalse(f.unforwarded)
        rr = lf.callRemote("forwardDeferred")
        l = []
        rr.addCallback(l.append)
        self.assertEqual(l[0], 1)


class PBWithSecurityOptionsTests(unittest.TestCase):
    """
    Test security customization.
    """

    def test_clientDefaultSecurityOptions(self):
        """
        By default, client broker should use C{jelly.globalSecurity} as
        security settings.
        """
        factory = pb.PBClientFactory()
        broker = factory.buildProtocol(None)
        self.assertIs(broker.security, jelly.globalSecurity)

    def test_serverDefaultSecurityOptions(self):
        """
        By default, server broker should use C{jelly.globalSecurity} as
        security settings.
        """
        factory = pb.PBServerFactory(Echoer())
        broker = factory.buildProtocol(None)
        self.assertIs(broker.security, jelly.globalSecurity)

    def test_clientSecurityCustomization(self):
        """
        Check that the security settings are passed from the client factory to
        the broker object.
        """
        security = jelly.SecurityOptions()
        factory = pb.PBClientFactory(security=security)
        broker = factory.buildProtocol(None)
        self.assertIs(broker.security, security)

    def test_serverSecurityCustomization(self):
        """
        Check that the security settings are passed from the server factory to
        the broker object.
        """
        security = jelly.SecurityOptions()
        factory = pb.PBServerFactory(Echoer(), security=security)
        broker = factory.buildProtocol(None)
        self.assertIs(broker.security, security)
