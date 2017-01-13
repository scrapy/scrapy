# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test the memcache client protocol.
"""

from __future__ import absolute_import, division

from twisted.internet.error import ConnectionDone

from twisted.protocols.memcache import MemCacheProtocol, NoSuchCommand
from twisted.protocols.memcache import ClientError, ServerError

from twisted.trial.unittest import TestCase
from twisted.test.proto_helpers import StringTransportWithDisconnection
from twisted.internet.task import Clock
from twisted.internet.defer import Deferred, gatherResults, TimeoutError
from twisted.internet.defer import DeferredList



class CommandMixin:
    """
    Setup and tests for basic invocation of L{MemCacheProtocol} commands.
    """

    def _test(self, d, send, recv, result):
        """
        Helper test method to test the resulting C{Deferred} of a
        L{MemCacheProtocol} command.
        """
        raise NotImplementedError()


    def test_get(self):
        """
        L{MemCacheProtocol.get} returns a L{Deferred} which is called back with
        the value and the flag associated with the given key if the server
        returns a successful result.
        """
        return self._test(
            self.proto.get(b"foo"), b"get foo\r\n",
            b"VALUE foo 0 3\r\nbar\r\nEND\r\n", (0, b"bar"))


    def test_emptyGet(self):
        """
        Test getting a non-available key: it succeeds but return L{None} as
        value and C{0} as flag.
        """
        return self._test(
            self.proto.get(b"foo"), b"get foo\r\n",
            b"END\r\n", (0, None))


    def test_getMultiple(self):
        """
        L{MemCacheProtocol.getMultiple} returns a L{Deferred} which is called
        back with a dictionary of flag, value for each given key.
        """
        return self._test(
            self.proto.getMultiple([b'foo', b'cow']),
            b"get foo cow\r\n",
            b"VALUE foo 0 3\r\nbar\r\nVALUE cow 0 7\r\nchicken\r\nEND\r\n",
            {b'cow': (0, b'chicken'), b'foo': (0, b'bar')})


    def test_getMultipleWithEmpty(self):
        """
        When L{MemCacheProtocol.getMultiple} is called with non-available keys,
        the corresponding tuples are (0, None).
        """
        return self._test(
            self.proto.getMultiple([b'foo', b'cow']),
            b"get foo cow\r\n",
            b"VALUE cow 1 3\r\nbar\r\nEND\r\n",
            {b'cow': (1, b'bar'), b'foo': (0, None)})


    def test_set(self):
        """
        L{MemCacheProtocol.set} returns a L{Deferred} which is called back with
        C{True} when the operation succeeds.
        """
        return self._test(
            self.proto.set(b"foo", b"bar"),
            b"set foo 0 0 3\r\nbar\r\n", b"STORED\r\n", True)


    def test_add(self):
        """
        L{MemCacheProtocol.add} returns a L{Deferred} which is called back with
        C{True} when the operation succeeds.
        """
        return self._test(
            self.proto.add(b"foo", b"bar"),
            b"add foo 0 0 3\r\nbar\r\n", b"STORED\r\n", True)


    def test_replace(self):
        """
        L{MemCacheProtocol.replace} returns a L{Deferred} which is called back
        with C{True} when the operation succeeds.
        """
        return self._test(
            self.proto.replace(b"foo", b"bar"),
            b"replace foo 0 0 3\r\nbar\r\n", b"STORED\r\n", True)


    def test_errorAdd(self):
        """
        Test an erroneous add: if a L{MemCacheProtocol.add} is called but the
        key already exists on the server, it returns a B{NOT STORED} answer,
        which calls back the resulting L{Deferred} with C{False}.
        """
        return self._test(
            self.proto.add(b"foo", b"bar"),
            b"add foo 0 0 3\r\nbar\r\n", b"NOT STORED\r\n", False)


    def test_errorReplace(self):
        """
        Test an erroneous replace: if a L{MemCacheProtocol.replace} is called
        but the key doesn't exist on the server, it returns a B{NOT STORED}
        answer, which calls back the resulting L{Deferred} with C{False}.
        """
        return self._test(
            self.proto.replace(b"foo", b"bar"),
            b"replace foo 0 0 3\r\nbar\r\n", b"NOT STORED\r\n", False)


    def test_delete(self):
        """
        L{MemCacheProtocol.delete} returns a L{Deferred} which is called back
        with C{True} when the server notifies a success.
        """
        return self._test(
            self.proto.delete(b"bar"), b"delete bar\r\n", b"DELETED\r\n", True)


    def test_errorDelete(self):
        """
        Test an error during a delete: if key doesn't exist on the server, it
        returns a B{NOT FOUND} answer which calls back the resulting
        L{Deferred} with C{False}.
        """
        return self._test(
            self.proto.delete(b"bar"),
            b"delete bar\r\n", b"NOT FOUND\r\n", False)


    def test_increment(self):
        """
        Test incrementing a variable: L{MemCacheProtocol.increment} returns a
        L{Deferred} which is called back with the incremented value of the
        given key.
        """
        return self._test(
            self.proto.increment(b"foo"), b"incr foo 1\r\n", b"4\r\n", 4)


    def test_decrement(self):
        """
        Test decrementing a variable: L{MemCacheProtocol.decrement} returns a
        L{Deferred} which is called back with the decremented value of the
        given key.
        """
        return self._test(
            self.proto.decrement(b"foo"), b"decr foo 1\r\n", b"5\r\n", 5)


    def test_incrementVal(self):
        """
        L{MemCacheProtocol.increment} takes an optional argument C{value} which
        replaces the default value of 1 when specified.
        """
        return self._test(
            self.proto.increment(b"foo", 8), b"incr foo 8\r\n", b"4\r\n", 4)


    def test_decrementVal(self):
        """
        L{MemCacheProtocol.decrement} takes an optional argument C{value} which
        replaces the default value of 1 when specified.
        """
        return self._test(
            self.proto.decrement(b"foo", 3), b"decr foo 3\r\n", b"5\r\n", 5)


    def test_stats(self):
        """
        Test retrieving server statistics via the L{MemCacheProtocol.stats}
        command: it parses the data sent by the server and calls back the
        resulting L{Deferred} with a dictionary of the received statistics.
        """
        return self._test(
            self.proto.stats(), b"stats\r\n",
            b"STAT foo bar\r\nSTAT egg spam\r\nEND\r\n",
            {b"foo": b"bar", b"egg": b"spam"})


    def test_statsWithArgument(self):
        """
        L{MemCacheProtocol.stats} takes an optional C{bytes} argument which,
        if specified, is sent along with the I{STAT} command.  The I{STAT}
        responses from the server are parsed as key/value pairs and returned
        as a C{dict} (as in the case where the argument is not specified).
        """
        return self._test(
            self.proto.stats(b"blah"), b"stats blah\r\n",
            b"STAT foo bar\r\nSTAT egg spam\r\nEND\r\n",
            {b"foo": b"bar", b"egg": b"spam"})


    def test_version(self):
        """
        Test version retrieval via the L{MemCacheProtocol.version} command: it
        returns a L{Deferred} which is called back with the version sent by the
        server.
        """
        return self._test(
            self.proto.version(), b"version\r\n", b"VERSION 1.1\r\n", b"1.1")


    def test_flushAll(self):
        """
        L{MemCacheProtocol.flushAll} returns a L{Deferred} which is called back
        with C{True} if the server acknowledges success.
        """
        return self._test(
            self.proto.flushAll(), b"flush_all\r\n", b"OK\r\n", True)



class MemCacheTests(CommandMixin, TestCase):
    """
    Test client protocol class L{MemCacheProtocol}.
    """

    def setUp(self):
        """
        Create a memcache client, connect it to a string protocol, and make it
        use a deterministic clock.
        """
        self.proto = MemCacheProtocol()
        self.clock = Clock()
        self.proto.callLater = self.clock.callLater
        self.transport = StringTransportWithDisconnection()
        self.transport.protocol = self.proto
        self.proto.makeConnection(self.transport)


    def _test(self, d, send, recv, result):
        """
        Implementation of C{_test} which checks that the command sends C{send}
        data, and that upon reception of C{recv} the result is C{result}.

        @param d: the resulting deferred from the memcache command.
        @type d: C{Deferred}

        @param send: the expected data to be sent.
        @type send: C{bytes}

        @param recv: the data to simulate as reception.
        @type recv: C{bytes}

        @param result: the expected result.
        @type result: C{any}
        """
        def cb(res):
            self.assertEqual(res, result)
        self.assertEqual(self.transport.value(), send)
        d.addCallback(cb)
        self.proto.dataReceived(recv)
        return d


    def test_invalidGetResponse(self):
        """
        If the value returned doesn't match the expected key of the current
        C{get} command, an error is raised in L{MemCacheProtocol.dataReceived}.
        """
        self.proto.get(b"foo")
        self.assertRaises(
            RuntimeError, self.proto.dataReceived,
            b"VALUE bar 0 7\r\nspamegg\r\nEND\r\n")


    def test_invalidMultipleGetResponse(self):
        """
        If the value returned doesn't match one the expected keys of the
        current multiple C{get} command, an error is raised error in
        L{MemCacheProtocol.dataReceived}.
        """
        self.proto.getMultiple([b"foo", b"bar"])
        self.assertRaises(
            RuntimeError, self.proto.dataReceived,
            b"VALUE egg 0 7\r\nspamegg\r\nEND\r\n")


    def test_invalidEndResponse(self):
        """
        If an END is received in response to an operation that isn't C{get},
        C{gets}, or C{stats}, an error is raised in
        L{MemCacheProtocol.dataReceived}.
        """
        self.proto.set(b"key", b"value")
        self.assertRaises(
            RuntimeError, self.proto.dataReceived,
            b"END\r\n")


    def test_timeOut(self):
        """
        Test the timeout on outgoing requests: when timeout is detected, all
        current commands fail with a L{TimeoutError}, and the connection is
        closed.
        """
        d1 = self.proto.get(b"foo")
        d2 = self.proto.get(b"bar")
        d3 = Deferred()
        self.proto.connectionLost = d3.callback

        self.clock.advance(self.proto.persistentTimeOut)
        self.assertFailure(d1, TimeoutError)
        self.assertFailure(d2, TimeoutError)

        def checkMessage(error):
            self.assertEqual(str(error), "Connection timeout")

        d1.addCallback(checkMessage)
        self.assertFailure(d3, ConnectionDone)
        return gatherResults([d1, d2, d3])


    def test_timeoutRemoved(self):
        """
        When a request gets a response, no pending timeout call remains around.
        """
        d = self.proto.get(b"foo")

        self.clock.advance(self.proto.persistentTimeOut - 1)
        self.proto.dataReceived(b"VALUE foo 0 3\r\nbar\r\nEND\r\n")

        def check(result):
            self.assertEqual(result, (0, b"bar"))
            self.assertEqual(len(self.clock.calls), 0)
        d.addCallback(check)
        return d


    def test_timeOutRaw(self):
        """
        Test the timeout when raw mode was started: the timeout is not reset
        until all the data has been received, so we can have a L{TimeoutError}
        when waiting for raw data.
        """
        d1 = self.proto.get(b"foo")
        d2 = Deferred()
        self.proto.connectionLost = d2.callback

        self.proto.dataReceived(b"VALUE foo 0 10\r\n12345")
        self.clock.advance(self.proto.persistentTimeOut)
        self.assertFailure(d1, TimeoutError)
        self.assertFailure(d2, ConnectionDone)
        return gatherResults([d1, d2])


    def test_timeOutStat(self):
        """
        Test the timeout when stat command has started: the timeout is not
        reset until the final B{END} is received.
        """
        d1 = self.proto.stats()
        d2 = Deferred()
        self.proto.connectionLost = d2.callback

        self.proto.dataReceived(b"STAT foo bar\r\n")
        self.clock.advance(self.proto.persistentTimeOut)
        self.assertFailure(d1, TimeoutError)
        self.assertFailure(d2, ConnectionDone)
        return gatherResults([d1, d2])


    def test_timeoutPipelining(self):
        """
        When two requests are sent, a timeout call remains around for the
        second request, and its timeout time is correct.
        """
        d1 = self.proto.get(b"foo")
        d2 = self.proto.get(b"bar")
        d3 = Deferred()
        self.proto.connectionLost = d3.callback

        self.clock.advance(self.proto.persistentTimeOut - 1)
        self.proto.dataReceived(b"VALUE foo 0 3\r\nbar\r\nEND\r\n")

        def check(result):
            self.assertEqual(result, (0, b"bar"))
            self.assertEqual(len(self.clock.calls), 1)
            for i in range(self.proto.persistentTimeOut):
                self.clock.advance(1)
            return self.assertFailure(d2, TimeoutError).addCallback(checkTime)

        def checkTime(ignored):
            # Check that the timeout happened C{self.proto.persistentTimeOut}
            # after the last response
            self.assertEqual(
                self.clock.seconds(), 2 * self.proto.persistentTimeOut - 1)

        d1.addCallback(check)
        self.assertFailure(d3, ConnectionDone)
        return d1


    def test_timeoutNotReset(self):
        """
        Check that timeout is not resetted for every command, but keep the
        timeout from the first command without response.
        """
        d1 = self.proto.get(b"foo")
        d3 = Deferred()
        self.proto.connectionLost = d3.callback

        self.clock.advance(self.proto.persistentTimeOut - 1)
        d2 = self.proto.get(b"bar")
        self.clock.advance(1)
        self.assertFailure(d1, TimeoutError)
        self.assertFailure(d2, TimeoutError)
        self.assertFailure(d3, ConnectionDone)
        return gatherResults([d1, d2, d3])


    def test_timeoutCleanDeferreds(self):
        """
        C{timeoutConnection} cleans the list of commands that it fires with
        C{TimeoutError}: C{connectionLost} doesn't try to fire them again, but
        sets the disconnected state so that future commands fail with a
        C{RuntimeError}.
        """
        d1 = self.proto.get(b"foo")
        self.clock.advance(self.proto.persistentTimeOut)
        self.assertFailure(d1, TimeoutError)
        d2 = self.proto.get(b"bar")
        self.assertFailure(d2, RuntimeError)
        return gatherResults([d1, d2])


    def test_connectionLost(self):
        """
        When disconnection occurs while commands are still outstanding, the
        commands fail.
        """
        d1 = self.proto.get(b"foo")
        d2 = self.proto.get(b"bar")
        self.transport.loseConnection()
        done = DeferredList([d1, d2], consumeErrors=True)

        def checkFailures(results):
            for success, result in results:
                self.assertFalse(success)
                result.trap(ConnectionDone)

        return done.addCallback(checkFailures)


    def test_tooLongKey(self):
        """
        An error is raised when trying to use a too long key: the called
        command returns a L{Deferred} which fails with a L{ClientError}.
        """
        d1 = self.assertFailure(
            self.proto.set(b"a" * 500, b"bar"), ClientError)
        d2 = self.assertFailure(self.proto.increment(b"a" * 500), ClientError)
        d3 = self.assertFailure(self.proto.get(b"a" * 500), ClientError)
        d4 = self.assertFailure(
            self.proto.append(b"a" * 500, b"bar"), ClientError)
        d5 = self.assertFailure(
            self.proto.prepend(b"a" * 500, b"bar"), ClientError)
        d6 = self.assertFailure(
            self.proto.getMultiple([b"foo", b"a" * 500]), ClientError)
        return gatherResults([d1, d2, d3, d4, d5, d6])


    def test_invalidCommand(self):
        """
        When an unknown command is sent directly (not through public API), the
        server answers with an B{ERROR} token, and the command fails with
        L{NoSuchCommand}.
        """
        d = self.proto._set(b"egg", b"foo", b"bar", 0, 0, b"")
        self.assertEqual(self.transport.value(), b"egg foo 0 0 3\r\nbar\r\n")
        self.assertFailure(d, NoSuchCommand)
        self.proto.dataReceived(b"ERROR\r\n")
        return d


    def test_clientError(self):
        """
        Test the L{ClientError} error: when the server sends a B{CLIENT_ERROR}
        token, the originating command fails with L{ClientError}, and the error
        contains the text sent by the server.
        """
        a = b"eggspamm"
        d = self.proto.set(b"foo", a)
        self.assertEqual(self.transport.value(),
                         b"set foo 0 0 8\r\neggspamm\r\n")
        self.assertFailure(d, ClientError)

        def check(err):
            self.assertEqual(str(err), repr(b"We don't like egg and spam"))

        d.addCallback(check)
        self.proto.dataReceived(b"CLIENT_ERROR We don't like egg and spam\r\n")
        return d


    def test_serverError(self):
        """
        Test the L{ServerError} error: when the server sends a B{SERVER_ERROR}
        token, the originating command fails with L{ServerError}, and the error
        contains the text sent by the server.
        """
        a = b"eggspamm"
        d = self.proto.set(b"foo", a)
        self.assertEqual(self.transport.value(),
                         b"set foo 0 0 8\r\neggspamm\r\n")
        self.assertFailure(d, ServerError)

        def check(err):
            self.assertEqual(str(err), repr(b"zomg"))

        d.addCallback(check)
        self.proto.dataReceived(b"SERVER_ERROR zomg\r\n")
        return d


    def test_unicodeKey(self):
        """
        Using a non-string key as argument to commands raises an error.
        """
        d1 = self.assertFailure(self.proto.set(u"foo", b"bar"), ClientError)
        d2 = self.assertFailure(self.proto.increment(u"egg"), ClientError)
        d3 = self.assertFailure(self.proto.get(1), ClientError)
        d4 = self.assertFailure(self.proto.delete(u"bar"), ClientError)
        d5 = self.assertFailure(self.proto.append(u"foo", b"bar"), ClientError)
        d6 = self.assertFailure(
            self.proto.prepend(u"foo", b"bar"), ClientError)
        d7 = self.assertFailure(
            self.proto.getMultiple([b"egg", 1]), ClientError)
        return gatherResults([d1, d2, d3, d4, d5, d6, d7])


    def test_unicodeValue(self):
        """
        Using a non-string value raises an error.
        """
        return self.assertFailure(self.proto.set(b"foo", u"bar"), ClientError)


    def test_pipelining(self):
        """
        Multiple requests can be sent subsequently to the server, and the
        protocol orders the responses correctly and dispatch to the
        corresponding client command.
        """
        d1 = self.proto.get(b"foo")
        d1.addCallback(self.assertEqual, (0, b"bar"))
        d2 = self.proto.set(b"bar", b"spamspamspam")
        d2.addCallback(self.assertEqual, True)
        d3 = self.proto.get(b"egg")
        d3.addCallback(self.assertEqual, (0, b"spam"))
        self.assertEqual(
            self.transport.value(),
            b"get foo\r\nset bar 0 0 12\r\nspamspamspam\r\nget egg\r\n")
        self.proto.dataReceived(b"VALUE foo 0 3\r\nbar\r\nEND\r\n"
                                b"STORED\r\n"
                                b"VALUE egg 0 4\r\nspam\r\nEND\r\n")
        return gatherResults([d1, d2, d3])


    def test_getInChunks(self):
        """
        If the value retrieved by a C{get} arrive in chunks, the protocol
        is able to reconstruct it and to produce the good value.
        """
        d = self.proto.get(b"foo")
        d.addCallback(self.assertEqual, (0, b"0123456789"))
        self.assertEqual(self.transport.value(), b"get foo\r\n")
        self.proto.dataReceived(b"VALUE foo 0 10\r\n0123456")
        self.proto.dataReceived(b"789")
        self.proto.dataReceived(b"\r\nEND")
        self.proto.dataReceived(b"\r\n")
        return d


    def test_append(self):
        """
        L{MemCacheProtocol.append} behaves like a L{MemCacheProtocol.set}
        method: it returns a L{Deferred} which is called back with C{True} when
        the operation succeeds.
        """
        return self._test(
            self.proto.append(b"foo", b"bar"),
            b"append foo 0 0 3\r\nbar\r\n", b"STORED\r\n", True)


    def test_prepend(self):
        """
        L{MemCacheProtocol.prepend} behaves like a L{MemCacheProtocol.set}
        method: it returns a L{Deferred} which is called back with C{True} when
        the operation succeeds.
        """
        return self._test(
            self.proto.prepend(b"foo", b"bar"),
            b"prepend foo 0 0 3\r\nbar\r\n", b"STORED\r\n", True)


    def test_gets(self):
        """
        L{MemCacheProtocol.get} handles an additional cas result when
        C{withIdentifier} is C{True} and forward it in the resulting
        L{Deferred}.
        """
        return self._test(
            self.proto.get(b"foo", True), b"gets foo\r\n",
            b"VALUE foo 0 3 1234\r\nbar\r\nEND\r\n", (0, b"1234", b"bar"))


    def test_emptyGets(self):
        """
        Test getting a non-available key with gets: it succeeds but return
        L{None} as value, C{0} as flag and an empty cas value.
        """
        return self._test(
            self.proto.get(b"foo", True), b"gets foo\r\n",
            b"END\r\n", (0, b"", None))


    def test_getsMultiple(self):
        """
        L{MemCacheProtocol.getMultiple} handles an additional cas field in the
        returned tuples if C{withIdentifier} is C{True}.
        """
        return self._test(
            self.proto.getMultiple([b"foo", b"bar"], True),
            b"gets foo bar\r\n",
            b"VALUE foo 0 3 1234\r\negg\r\n"
            b"VALUE bar 0 4 2345\r\nspam\r\nEND\r\n",
            {b'bar': (0, b'2345', b'spam'), b'foo': (0, b'1234', b'egg')})


    def test_getsMultipleIterableKeys(self):
        """
        L{MemCacheProtocol.getMultiple} accepts any iterable of keys.
        """
        return self._test(
            self.proto.getMultiple(iter([b"foo", b"bar"]), True),
            b"gets foo bar\r\n",
            b"VALUE foo 0 3 1234\r\negg\r\n"
            b"VALUE bar 0 4 2345\r\nspam\r\nEND\r\n",
            {b'bar': (0, b'2345', b'spam'), b'foo': (0, b'1234', b'egg')})


    def test_getsMultipleWithEmpty(self):
        """
        When getting a non-available key with L{MemCacheProtocol.getMultiple}
        when C{withIdentifier} is C{True}, the other keys are retrieved
        correctly, and the non-available key gets a tuple of C{0} as flag,
        L{None} as value, and an empty cas value.
        """
        return self._test(
            self.proto.getMultiple([b"foo", b"bar"], True),
            b"gets foo bar\r\n",
            b"VALUE foo 0 3 1234\r\negg\r\nEND\r\n",
            {b'bar': (0, b'', None), b'foo': (0, b'1234', b'egg')})


    def test_checkAndSet(self):
        """
        L{MemCacheProtocol.checkAndSet} passes an additional cas identifier
        that the server handles to check if the data has to be updated.
        """
        return self._test(
            self.proto.checkAndSet(b"foo", b"bar", cas=b"1234"),
            b"cas foo 0 0 3 1234\r\nbar\r\n", b"STORED\r\n", True)


    def test_casUnknowKey(self):
        """
        When L{MemCacheProtocol.checkAndSet} response is C{EXISTS}, the
        resulting L{Deferred} fires with C{False}.
        """
        return self._test(
            self.proto.checkAndSet(b"foo", b"bar", cas=b"1234"),
            b"cas foo 0 0 3 1234\r\nbar\r\n", b"EXISTS\r\n", False)



class CommandFailureTests(CommandMixin, TestCase):
    """
    Tests for correct failure of commands on a disconnected
    L{MemCacheProtocol}.
    """

    def setUp(self):
        """
        Create a disconnected memcache client, using a deterministic clock.
        """
        self.proto = MemCacheProtocol()
        self.clock = Clock()
        self.proto.callLater = self.clock.callLater
        self.transport = StringTransportWithDisconnection()
        self.transport.protocol = self.proto
        self.proto.makeConnection(self.transport)
        self.transport.loseConnection()


    def _test(self, d, send, recv, result):
        """
        Implementation of C{_test} which checks that the command fails with
        C{RuntimeError} because the transport is disconnected. All the
        parameters except C{d} are ignored.
        """
        return self.assertFailure(d, RuntimeError)
