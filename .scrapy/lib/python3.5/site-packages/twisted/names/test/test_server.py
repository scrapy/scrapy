# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.names.server}.
"""
from __future__ import division, absolute_import

from zope.interface.verify import verifyClass

from twisted.internet import defer
from twisted.internet.interfaces import IProtocolFactory
from twisted.names import dns, error, resolve, server
from twisted.python import failure, log
from twisted.trial import unittest



class RaisedArguments(Exception):
    """
    An exception containing the arguments raised by L{raiser}.
    """
    def __init__(self, args, kwargs):
        self.args = args
        self.kwargs = kwargs



def raiser(*args, **kwargs):
    """
    Raise a L{RaisedArguments} exception containing the supplied arguments.

    Used as a fake when testing the call signatures of  methods and functions.
    """
    raise RaisedArguments(args, kwargs)



class NoResponseDNSServerFactory(server.DNSServerFactory):
    """
    A L{server.DNSServerFactory} subclass which does not attempt to reply to any
    received messages.

    Used for testing logged messages in C{messageReceived} without having to
    fake or patch the preceding code which attempts to deliver a response
    message.
    """
    def allowQuery(self, message, protocol, address):
        """
        Deny all queries.

        @param message: See L{server.DNSServerFactory.allowQuery}
        @param protocol: See L{server.DNSServerFactory.allowQuery}
        @param address: See L{server.DNSServerFactory.allowQuery}

        @return: L{False}
        @rtype: L{bool}
        """
        return False


    def sendReply(self, protocol, message, address):
        """
        A noop send reply.

        @param protocol: See L{server.DNSServerFactory.sendReply}
        @param message: See L{server.DNSServerFactory.sendReply}
        @param address: See L{server.DNSServerFactory.sendReply}
        """



class RaisingDNSServerFactory(server.DNSServerFactory):
    """
    A L{server.DNSServerFactory} subclass whose methods raise an exception
    containing the supplied arguments.

    Used for stopping L{messageReceived} and testing the arguments supplied to
    L{allowQuery}.
    """

    class AllowQueryArguments(Exception):
        """
        Contains positional and keyword arguments in C{args}.
        """

    def allowQuery(self, *args, **kwargs):
        """
        Raise the arguments supplied to L{allowQuery}.

        @param args: Positional arguments which will be recorded in the raised
            exception.
        @type args: L{tuple}

        @param kwargs: Keyword args which will be recorded in the raised
            exception.
        @type kwargs: L{dict}
        """
        raise self.AllowQueryArguments(args, kwargs)



class RaisingProtocol(object):
    """
    A partial fake L{IProtocol} whose methods raise an exception containing the
    supplied arguments.
    """
    class WriteMessageArguments(Exception):
        """
        Contains positional and keyword arguments in C{args}.
        """

    def writeMessage(self, *args, **kwargs):
        """
        Raises the supplied arguments.

        @param args: Positional arguments
        @type args: L{tuple}

        @param kwargs: Keyword args
        @type kwargs: L{dict}
        """
        raise self.WriteMessageArguments(args, kwargs)



class NoopProtocol(object):
    """
    A partial fake L{dns.DNSProtocolMixin} with a noop L{writeMessage} method.
    """
    def writeMessage(self, *args, **kwargs):
        """
        A noop version of L{dns.DNSProtocolMixin.writeMessage}.

        @param args: Positional arguments
        @type args: L{tuple}

        @param kwargs: Keyword args
        @type kwargs: L{dict}
        """



class RaisingResolver(object):
    """
    A partial fake L{IResolver} whose methods raise an exception containing the
    supplied arguments.
    """
    class QueryArguments(Exception):
        """
        Contains positional and keyword arguments in C{args}.
        """


    def query(self, *args, **kwargs):
        """
        Raises the supplied arguments.

        @param args: Positional arguments
        @type args: L{tuple}

        @param kwargs: Keyword args
        @type kwargs: L{dict}
        """
        raise self.QueryArguments(args, kwargs)



class RaisingCache(object):
    """
    A partial fake L{twisted.names.cache.Cache} whose methods raise an exception
    containing the supplied arguments.
    """
    class CacheResultArguments(Exception):
        """
        Contains positional and keyword arguments in C{args}.
        """


    def cacheResult(self, *args, **kwargs):
        """
        Raises the supplied arguments.

        @param args: Positional arguments
        @type args: L{tuple}

        @param kwargs: Keyword args
        @type kwargs: L{dict}
        """
        raise self.CacheResultArguments(args, kwargs)



def assertLogMessage(testCase, expectedMessages, callable, *args, **kwargs):
    """
    Assert that the callable logs the expected messages when called.

    XXX: Put this somewhere where it can be re-used elsewhere. See #6677.

    @param testCase: The test case controlling the test which triggers the
        logged messages and on which assertions will be called.
    @type testCase: L{unittest.SynchronousTestCase}

    @param expectedMessages: A L{list} of the expected log messages
    @type expectedMessages: L{list}

    @param callable: The function which is expected to produce the
        C{expectedMessages} when called.
    @type callable: L{callable}

    @param args: Positional arguments to be passed to C{callable}.
    @type args: L{list}

    @param kwargs: Keyword arguments to be passed to C{callable}.
    @type kwargs: L{dict}
    """
    loggedMessages = []
    log.addObserver(loggedMessages.append)
    testCase.addCleanup(log.removeObserver, loggedMessages.append)

    callable(*args, **kwargs)

    testCase.assertEqual(
        [m['message'][0] for m in loggedMessages],
        expectedMessages)



class DNSServerFactoryTests(unittest.TestCase):
    """
    Tests for L{server.DNSServerFactory}.
    """
    def test_resolverType(self):
        """
        L{server.DNSServerFactory.resolver} is a L{resolve.ResolverChain}
        instance
        """
        self.assertIsInstance(
            server.DNSServerFactory().resolver,
            resolve.ResolverChain)


    def test_resolverDefaultEmpty(self):
        """
        L{server.DNSServerFactory.resolver} is an empty L{resolve.ResolverChain}
        by default.
        """
        self.assertEqual(
            server.DNSServerFactory().resolver.resolvers,
            [])


    def test_authorities(self):
        """
        L{server.DNSServerFactory.__init__} accepts an C{authorities}
        argument. The value of this argument is a list and is used to extend the
        C{resolver} L{resolve.ResolverChain}.
        """
        dummyResolver = object()
        self.assertEqual(
            server.DNSServerFactory(
                authorities=[dummyResolver]).resolver.resolvers,
            [dummyResolver])


    def test_caches(self):
        """
        L{server.DNSServerFactory.__init__} accepts a C{caches} argument. The
        value of this argument is a list and is used to extend the C{resolver}
        L{resolve.ResolverChain}.
        """
        dummyResolver = object()
        self.assertEqual(
            server.DNSServerFactory(
                caches=[dummyResolver]).resolver.resolvers,
            [dummyResolver])


    def test_clients(self):
        """
        L{server.DNSServerFactory.__init__} accepts a C{clients} argument. The
        value of this argument is a list and is used to extend the C{resolver}
        L{resolve.ResolverChain}.
        """
        dummyResolver = object()
        self.assertEqual(
            server.DNSServerFactory(
                clients=[dummyResolver]).resolver.resolvers,
            [dummyResolver])


    def test_resolverOrder(self):
        """
        L{server.DNSServerFactory.resolver} contains an ordered list of
        authorities, caches and clients.
        """
        # Use classes here so that we can see meaningful names in test results
        class DummyAuthority(object):
            pass

        class DummyCache(object):
            pass

        class DummyClient(object):
            pass

        self.assertEqual(
            server.DNSServerFactory(
                authorities=[DummyAuthority],
                caches=[DummyCache],
                clients=[DummyClient]).resolver.resolvers,
            [DummyAuthority, DummyCache, DummyClient])


    def test_cacheDefault(self):
        """
        L{server.DNSServerFactory.cache} is L{None} by default.
        """
        self.assertIsNone(server.DNSServerFactory().cache)


    def test_cacheOverride(self):
        """
        L{server.DNSServerFactory.__init__} assigns the last object in the
        C{caches} list to L{server.DNSServerFactory.cache}.
        """
        dummyResolver = object()
        self.assertEqual(
            server.DNSServerFactory(caches=[object(), dummyResolver]).cache,
            dummyResolver)


    def test_canRecurseDefault(self):
        """
        L{server.DNSServerFactory.canRecurse} is a flag indicating that this
        server is capable of performing recursive DNS lookups. It defaults to
        L{False}.
        """
        self.assertFalse(server.DNSServerFactory().canRecurse)


    def test_canRecurseOverride(self):
        """
        L{server.DNSServerFactory.__init__} sets C{canRecurse} to L{True} if it
        is supplied with C{clients}.
        """
        self.assertEqual(
            server.DNSServerFactory(clients=[None]).canRecurse, True)


    def test_verboseDefault(self):
        """
        L{server.DNSServerFactory.verbose} defaults to L{False}.
        """
        self.assertFalse(server.DNSServerFactory().verbose)


    def test_verboseOverride(self):
        """
        L{server.DNSServerFactory.__init__} accepts a C{verbose} argument which
        overrides L{server.DNSServerFactory.verbose}.
        """
        self.assertTrue(server.DNSServerFactory(verbose=True).verbose)


    def test_interface(self):
        """
        L{server.DNSServerFactory} implements L{IProtocolFactory}.
        """
        self.assertTrue(verifyClass(IProtocolFactory, server.DNSServerFactory))


    def test_defaultProtocol(self):
        """
        L{server.DNSServerFactory.protocol} defaults to L{dns.DNSProtocol}.
        """
        self.assertIs(server.DNSServerFactory.protocol, dns.DNSProtocol)


    def test_buildProtocolProtocolOverride(self):
        """
        L{server.DNSServerFactory.buildProtocol} builds a protocol by calling
        L{server.DNSServerFactory.protocol} with its self as a positional
        argument.
        """
        class FakeProtocol(object):
            factory = None
            args = None
            kwargs = None

        stubProtocol = FakeProtocol()

        def fakeProtocolFactory(*args, **kwargs):
            stubProtocol.args = args
            stubProtocol.kwargs = kwargs
            return stubProtocol

        f = server.DNSServerFactory()
        f.protocol = fakeProtocolFactory
        p = f.buildProtocol(addr=None)

        self.assertEqual(
            (stubProtocol, (f,), {}),
            (p, p.args, p.kwargs)
        )


    def test_verboseLogQuiet(self):
        """
        L{server.DNSServerFactory._verboseLog} does not log messages unless
        C{verbose > 0}.
        """
        f = server.DNSServerFactory()
        assertLogMessage(
            self,
            [],
            f._verboseLog,
            'Foo Bar'
        )


    def test_verboseLogVerbose(self):
        """
        L{server.DNSServerFactory._verboseLog} logs a message if C{verbose > 0}.
        """
        f = server.DNSServerFactory(verbose=1)
        assertLogMessage(
            self,
            ['Foo Bar'],
            f._verboseLog,
            'Foo Bar'
        )


    def test_messageReceivedLoggingNoQuery(self):
        """
        L{server.DNSServerFactory.messageReceived} logs about an empty query if
        the message had no queries and C{verbose} is C{>0}.
        """
        m = dns.Message()
        f = NoResponseDNSServerFactory(verbose=1)

        assertLogMessage(
            self,
            ["Empty query from ('192.0.2.100', 53)"],
            f.messageReceived,
            message=m, proto=None, address=('192.0.2.100', 53))


    def test_messageReceivedLogging1(self):
        """
        L{server.DNSServerFactory.messageReceived} logs the query types of all
        queries in the message if C{verbose} is set to C{1}.
        """
        m = dns.Message()
        m.addQuery(name='example.com', type=dns.MX)
        m.addQuery(name='example.com', type=dns.AAAA)
        f = NoResponseDNSServerFactory(verbose=1)

        assertLogMessage(
            self,
            ["MX AAAA query from ('192.0.2.100', 53)"],
            f.messageReceived,
            message=m, proto=None, address=('192.0.2.100', 53))


    def test_messageReceivedLogging2(self):
        """
        L{server.DNSServerFactory.messageReceived} logs the repr of all queries
        in the message if C{verbose} is set to C{2}.
        """
        m = dns.Message()
        m.addQuery(name='example.com', type=dns.MX)
        m.addQuery(name='example.com', type=dns.AAAA)
        f = NoResponseDNSServerFactory(verbose=2)

        assertLogMessage(
            self,
            ["<Query example.com MX IN> "
             "<Query example.com AAAA IN> query from ('192.0.2.100', 53)"],
            f.messageReceived,
            message=m, proto=None, address=('192.0.2.100', 53))


    def test_messageReceivedTimestamp(self):
        """
        L{server.DNSServerFactory.messageReceived} assigns a unix timestamp to
        the received message.
        """
        m = dns.Message()
        f = NoResponseDNSServerFactory()
        t = object()
        self.patch(server.time, 'time', lambda: t)
        f.messageReceived(message=m, proto=None, address=None)

        self.assertEqual(m.timeReceived, t)


    def test_messageReceivedAllowQuery(self):
        """
        L{server.DNSServerFactory.messageReceived} passes all messages to
        L{server.DNSServerFactory.allowQuery} along with the receiving protocol
        and origin address.
        """
        message = dns.Message()
        dummyProtocol = object()
        dummyAddress = object()

        f = RaisingDNSServerFactory()
        e = self.assertRaises(
            RaisingDNSServerFactory.AllowQueryArguments,
            f.messageReceived,
            message=message, proto=dummyProtocol, address=dummyAddress)
        args, kwargs = e.args
        self.assertEqual(args, (message, dummyProtocol, dummyAddress))
        self.assertEqual(kwargs, {})


    def test_allowQueryFalse(self):
        """
        If C{allowQuery} returns C{False},
        L{server.DNSServerFactory.messageReceived} calls L{server.sendReply}
        with a message whose C{rCode} is L{dns.EREFUSED}.
        """
        class SendReplyException(Exception):
            pass

        class RaisingDNSServerFactory(server.DNSServerFactory):
            def allowQuery(self, *args, **kwargs):
                return False

            def sendReply(self, *args, **kwargs):
                raise SendReplyException(args, kwargs)

        f = RaisingDNSServerFactory()
        e = self.assertRaises(
            SendReplyException,
            f.messageReceived,
            message=dns.Message(), proto=None, address=None)
        (proto, message, address), kwargs = e.args

        self.assertEqual(message.rCode, dns.EREFUSED)


    def _messageReceivedTest(self, methodName, message):
        """
        Assert that the named method is called with the given message when it is
        passed to L{DNSServerFactory.messageReceived}.

        @param methodName: The name of the method which is expected to be
            called.
        @type methodName: L{str}

        @param message: The message which is expected to be passed to the
            C{methodName} method.
        @type message: L{dns.Message}
        """
        # Make it appear to have some queries so that
        # DNSServerFactory.allowQuery allows it.
        message.queries = [None]

        receivedMessages = []
        def fakeHandler(message, protocol, address):
            receivedMessages.append((message, protocol, address))

        protocol = NoopProtocol()
        factory = server.DNSServerFactory(None)
        setattr(factory, methodName, fakeHandler)
        factory.messageReceived(message, protocol)
        self.assertEqual(receivedMessages, [(message, protocol, None)])


    def test_queryMessageReceived(self):
        """
        L{DNSServerFactory.messageReceived} passes messages with an opcode of
        C{OP_QUERY} on to L{DNSServerFactory.handleQuery}.
        """
        self._messageReceivedTest(
            'handleQuery', dns.Message(opCode=dns.OP_QUERY))


    def test_inverseQueryMessageReceived(self):
        """
        L{DNSServerFactory.messageReceived} passes messages with an opcode of
        C{OP_INVERSE} on to L{DNSServerFactory.handleInverseQuery}.
        """
        self._messageReceivedTest(
            'handleInverseQuery', dns.Message(opCode=dns.OP_INVERSE))


    def test_statusMessageReceived(self):
        """
        L{DNSServerFactory.messageReceived} passes messages with an opcode of
        C{OP_STATUS} on to L{DNSServerFactory.handleStatus}.
        """
        self._messageReceivedTest(
            'handleStatus', dns.Message(opCode=dns.OP_STATUS))


    def test_notifyMessageReceived(self):
        """
        L{DNSServerFactory.messageReceived} passes messages with an opcode of
        C{OP_NOTIFY} on to L{DNSServerFactory.handleNotify}.
        """
        self._messageReceivedTest(
            'handleNotify', dns.Message(opCode=dns.OP_NOTIFY))


    def test_updateMessageReceived(self):
        """
        L{DNSServerFactory.messageReceived} passes messages with an opcode of
        C{OP_UPDATE} on to L{DNSServerFactory.handleOther}.

        This may change if the implementation ever covers update messages.
        """
        self._messageReceivedTest(
            'handleOther', dns.Message(opCode=dns.OP_UPDATE))


    def test_connectionTracking(self):
        """
        The C{connectionMade} and C{connectionLost} methods of
        L{DNSServerFactory} cooperate to keep track of all L{DNSProtocol}
        objects created by a factory which are connected.
        """
        protoA, protoB = object(), object()
        factory = server.DNSServerFactory()
        factory.connectionMade(protoA)
        self.assertEqual(factory.connections, [protoA])
        factory.connectionMade(protoB)
        self.assertEqual(factory.connections, [protoA, protoB])
        factory.connectionLost(protoA)
        self.assertEqual(factory.connections, [protoB])
        factory.connectionLost(protoB)
        self.assertEqual(factory.connections, [])


    def test_handleQuery(self):
        """
        L{server.DNSServerFactory.handleQuery} takes the first query from the
        supplied message and dispatches it to
        L{server.DNSServerFactory.resolver.query}.
        """
        m = dns.Message()
        m.addQuery(b'one.example.com')
        m.addQuery(b'two.example.com')
        f = server.DNSServerFactory()
        f.resolver = RaisingResolver()

        e = self.assertRaises(
            RaisingResolver.QueryArguments,
            f.handleQuery,
            message=m, protocol=NoopProtocol(), address=None)
        (query,), kwargs = e.args
        self.assertEqual(query, m.queries[0])


    def test_handleQueryCallback(self):
        """
        L{server.DNSServerFactory.handleQuery} adds
        L{server.DNSServerFactory.resolver.gotResolverResponse} as a callback to
        the deferred returned by L{server.DNSServerFactory.resolver.query}. It
        is called with the query response, the original protocol, message and
        origin address.
        """
        f = server.DNSServerFactory()

        d = defer.Deferred()
        class FakeResolver(object):
            def query(self, *args, **kwargs):
                return d
        f.resolver = FakeResolver()

        gotResolverResponseArgs = []
        def fakeGotResolverResponse(*args, **kwargs):
            gotResolverResponseArgs.append((args, kwargs))
        f.gotResolverResponse = fakeGotResolverResponse

        m = dns.Message()
        m.addQuery(b'one.example.com')
        stubProtocol = NoopProtocol()
        dummyAddress = object()

        f.handleQuery(message=m, protocol=stubProtocol, address=dummyAddress)

        dummyResponse = object()
        d.callback(dummyResponse)

        self.assertEqual(
            gotResolverResponseArgs,
            [((dummyResponse, stubProtocol, m, dummyAddress), {})])


    def test_handleQueryErrback(self):
        """
        L{server.DNSServerFactory.handleQuery} adds
        L{server.DNSServerFactory.resolver.gotResolverError} as an errback to
        the deferred returned by L{server.DNSServerFactory.resolver.query}. It
        is called with the query failure, the original protocol, message and
        origin address.
        """
        f = server.DNSServerFactory()

        d = defer.Deferred()
        class FakeResolver(object):
            def query(self, *args, **kwargs):
                return d
        f.resolver = FakeResolver()

        gotResolverErrorArgs = []
        def fakeGotResolverError(*args, **kwargs):
            gotResolverErrorArgs.append((args, kwargs))
        f.gotResolverError = fakeGotResolverError

        m = dns.Message()
        m.addQuery(b'one.example.com')
        stubProtocol = NoopProtocol()
        dummyAddress = object()

        f.handleQuery(message=m, protocol=stubProtocol, address=dummyAddress)

        stubFailure = failure.Failure(Exception())
        d.errback(stubFailure)

        self.assertEqual(
            gotResolverErrorArgs,
            [((stubFailure, stubProtocol, m, dummyAddress), {})])


    def test_gotResolverResponse(self):
        """
        L{server.DNSServerFactory.gotResolverResponse} accepts a tuple of
        resource record lists and triggers a response message containing those
        resource record lists.
        """
        f = server.DNSServerFactory()
        answers = []
        authority = []
        additional = []
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.gotResolverResponse,
            (answers, authority, additional),
            protocol=RaisingProtocol(), message=dns.Message(), address=None)
        (message,), kwargs = e.args

        self.assertIs(message.answers, answers)
        self.assertIs(message.authority, authority)
        self.assertIs(message.additional, additional)


    def test_gotResolverResponseCallsResponseFromMessage(self):
        """
        L{server.DNSServerFactory.gotResolverResponse} calls
        L{server.DNSServerFactory._responseFromMessage} to generate a response.
        """
        factory = NoResponseDNSServerFactory()
        factory._responseFromMessage = raiser

        request = dns.Message()
        request.timeReceived = 1

        e = self.assertRaises(
            RaisedArguments,
            factory.gotResolverResponse,
            ([], [], []),
            protocol=None, message=request, address=None
        )
        self.assertEqual(
            ((), dict(message=request, rCode=dns.OK,
                      answers=[], authority=[], additional=[])),
            (e.args, e.kwargs)
        )


    def test_responseFromMessageNewMessage(self):
        """
        L{server.DNSServerFactory._responseFromMessage} generates a response
        message which is a copy of the request message.
        """
        factory = server.DNSServerFactory()
        request = dns.Message(answer=False, recAv=False)
        response = factory._responseFromMessage(message=request),

        self.assertIsNot(request, response)


    def test_responseFromMessageRecursionAvailable(self):
        """
        L{server.DNSServerFactory._responseFromMessage} generates a response
        message whose C{recAV} attribute is L{True} if
        L{server.DNSServerFactory.canRecurse} is L{True}.
        """
        factory = server.DNSServerFactory()
        factory.canRecurse = True
        response1 = factory._responseFromMessage(
            message=dns.Message(recAv=False))
        factory.canRecurse = False
        response2 = factory._responseFromMessage(
            message=dns.Message(recAv=True))
        self.assertEqual(
            (True, False),
            (response1.recAv, response2.recAv))


    def test_responseFromMessageTimeReceived(self):
        """
        L{server.DNSServerFactory._responseFromMessage} generates a response
        message whose C{timeReceived} attribute has the same value as that found
        on the request.
        """
        factory = server.DNSServerFactory()
        request = dns.Message()
        request.timeReceived = 1234
        response = factory._responseFromMessage(message=request)

        self.assertEqual(request.timeReceived, response.timeReceived)


    def test_responseFromMessageMaxSize(self):
        """
        L{server.DNSServerFactory._responseFromMessage} generates a response
        message whose C{maxSize} attribute has the same value as that found
        on the request.
        """
        factory = server.DNSServerFactory()
        request = dns.Message()
        request.maxSize = 0
        response = factory._responseFromMessage(message=request)

        self.assertEqual(request.maxSize, response.maxSize)


    def test_messageFactory(self):
        """
        L{server.DNSServerFactory} has a C{_messageFactory} attribute which is
        L{dns.Message} by default.
        """
        self.assertIs(dns.Message, server.DNSServerFactory._messageFactory)


    def test_responseFromMessageCallsMessageFactory(self):
        """
        L{server.DNSServerFactory._responseFromMessage} calls
        C{dns._responseFromMessage} to generate a response
        message from the request message. It supplies the request message and
        other keyword arguments which should be passed to the response message
        initialiser.
        """
        factory = server.DNSServerFactory()
        self.patch(dns, '_responseFromMessage', raiser)

        request = dns.Message()
        e = self.assertRaises(
            RaisedArguments,
            factory._responseFromMessage,
            message=request, rCode=dns.OK
        )
        self.assertEqual(
            ((), dict(responseConstructor=factory._messageFactory,
                      message=request, rCode=dns.OK, recAv=factory.canRecurse,
                      auth=False)),
            (e.args, e.kwargs)
        )


    def test_responseFromMessageAuthoritativeMessage(self):
        """
        L{server.DNSServerFactory._responseFromMessage} marks the response
        message as authoritative if any of the answer records are authoritative.
        """
        factory = server.DNSServerFactory()
        response1 = factory._responseFromMessage(
            message=dns.Message(), answers=[dns.RRHeader(auth=True)])
        response2 = factory._responseFromMessage(
            message=dns.Message(), answers=[dns.RRHeader(auth=False)])
        self.assertEqual(
            (True, False),
            (response1.auth, response2.auth),
        )


    def test_gotResolverResponseLogging(self):
        """
        L{server.DNSServerFactory.gotResolverResponse} logs the total number of
        records in the response if C{verbose > 0}.
        """
        f = NoResponseDNSServerFactory(verbose=1)
        answers = [dns.RRHeader()]
        authority = [dns.RRHeader()]
        additional = [dns.RRHeader()]

        assertLogMessage(
            self,
            ["Lookup found 3 records"],
            f.gotResolverResponse,
            (answers, authority, additional),
            protocol=NoopProtocol(), message=dns.Message(), address=None)


    def test_gotResolverResponseCaching(self):
        """
        L{server.DNSServerFactory.gotResolverResponse} caches the response if at
        least one cache was provided in the constructor.
        """
        f = NoResponseDNSServerFactory(caches=[RaisingCache()])

        m = dns.Message()
        m.addQuery(b'example.com')
        expectedAnswers = [dns.RRHeader()]
        expectedAuthority = []
        expectedAdditional = []

        e = self.assertRaises(
            RaisingCache.CacheResultArguments,
            f.gotResolverResponse,
            (expectedAnswers, expectedAuthority, expectedAdditional),
            protocol=NoopProtocol(), message=m, address=None)
        (query, (answers, authority, additional)), kwargs = e.args

        self.assertEqual(query.name.name, b'example.com')
        self.assertIs(answers, expectedAnswers)
        self.assertIs(authority, expectedAuthority)
        self.assertIs(additional, expectedAdditional)


    def test_gotResolverErrorCallsResponseFromMessage(self):
        """
        L{server.DNSServerFactory.gotResolverError} calls
        L{server.DNSServerFactory._responseFromMessage} to generate a response.
        """
        factory = NoResponseDNSServerFactory()
        factory._responseFromMessage = raiser

        request = dns.Message()
        request.timeReceived = 1

        e = self.assertRaises(
            RaisedArguments,
            factory.gotResolverError,
            failure.Failure(error.DomainError()),
            protocol=None, message=request, address=None
        )
        self.assertEqual(
            ((), dict(message=request, rCode=dns.ENAME)),
            (e.args, e.kwargs)
        )


    def _assertMessageRcodeForError(self, responseError, expectedMessageCode):
        """
        L{server.DNSServerFactory.gotResolver} accepts a L{failure.Failure} and
        triggers a response message whose rCode corresponds to the DNS error
        contained in the C{Failure}.

        @param responseError: The L{Exception} instance which is expected to
            trigger C{expectedMessageCode} when it is supplied to
            C{gotResolverError}
        @type responseError: L{Exception}

        @param expectedMessageCode: The C{rCode} which is expected in the
            message returned by C{gotResolverError} in response to
            C{responseError}.
        @type expectedMessageCode: L{int}
        """
        f = server.DNSServerFactory()
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.gotResolverError,
            failure.Failure(responseError),
            protocol=RaisingProtocol(), message=dns.Message(), address=None)
        (message,), kwargs = e.args

        self.assertEqual(message.rCode, expectedMessageCode)


    def test_gotResolverErrorDomainError(self):
        """
        L{server.DNSServerFactory.gotResolver} triggers a response message with
        an C{rCode} of L{dns.ENAME} if supplied with a L{error.DomainError}.
        """
        self._assertMessageRcodeForError(error.DomainError(), dns.ENAME)


    def test_gotResolverErrorAuthoritativeDomainError(self):
        """
        L{server.DNSServerFactory.gotResolver} triggers a response message with
        an C{rCode} of L{dns.ENAME} if supplied with a
        L{error.AuthoritativeDomainError}.
        """
        self._assertMessageRcodeForError(
            error.AuthoritativeDomainError(), dns.ENAME)


    def test_gotResolverErrorOtherError(self):
        """
        L{server.DNSServerFactory.gotResolver} triggers a response message with
        an C{rCode} of L{dns.ESERVER} if supplied with another type of error and
        logs the error.
        """
        self._assertMessageRcodeForError(KeyError(), dns.ESERVER)
        e = self.flushLoggedErrors(KeyError)
        self.assertEqual(len(e), 1)


    def test_gotResolverErrorLogging(self):
        """
        L{server.DNSServerFactory.gotResolver} logs a message if C{verbose > 0}.
        """
        f = NoResponseDNSServerFactory(verbose=1)
        assertLogMessage(
            self,
            ["Lookup failed"],
            f.gotResolverError,
            failure.Failure(error.DomainError()),
            protocol=NoopProtocol(), message=dns.Message(), address=None)


    def test_gotResolverErrorResetsResponseAttributes(self):
        """
        L{server.DNSServerFactory.gotResolverError} does not allow request
        attributes to leak into the response ie it sends a response with AD, CD
        set to 0 and empty response record sections.
        """
        factory = server.DNSServerFactory()
        responses = []
        factory.sendReply = (
            lambda protocol, response, address: responses.append(response)
        )
        request = dns.Message(authenticData=True, checkingDisabled=True)
        request.answers = [object(), object()]
        request.authority = [object(), object()]
        request.additional = [object(), object()]
        factory.gotResolverError(
            failure.Failure(error.DomainError()),
            protocol=None, message=request, address=None
        )

        self.assertEqual([dns.Message(rCode=3, answer=True)], responses)


    def test_gotResolverResponseResetsResponseAttributes(self):
        """
        L{server.DNSServerFactory.gotResolverResponse} does not allow request
        attributes to leak into the response ie it sends a response with AD, CD
        set to 0 and none of the records in the request answer sections are
        copied to the response.
        """
        factory = server.DNSServerFactory()
        responses = []
        factory.sendReply = (
            lambda protocol, response, address: responses.append(response)
        )
        request = dns.Message(authenticData=True, checkingDisabled=True)
        request.answers = [object(), object()]
        request.authority = [object(), object()]
        request.additional = [object(), object()]

        factory.gotResolverResponse(
            ([], [], []),
            protocol=None, message=request, address=None
        )

        self.assertEqual([dns.Message(rCode=0, answer=True)], responses)


    def test_sendReplyWithAddress(self):
        """
        If L{server.DNSServerFactory.sendReply} is supplied with a protocol
        *and* an address tuple it will supply that address to
        C{protocol.writeMessage}.
        """
        m = dns.Message()
        dummyAddress = object()
        f = server.DNSServerFactory()
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.sendReply,
            protocol=RaisingProtocol(),
            message=m,
            address=dummyAddress)
        args, kwargs = e.args
        self.assertEqual(args, (m, dummyAddress))
        self.assertEqual(kwargs, {})


    def test_sendReplyWithoutAddress(self):
        """
        If L{server.DNSServerFactory.sendReply} is supplied with a protocol but
        no address tuple it will supply only a message to
        C{protocol.writeMessage}.
        """
        m = dns.Message()
        f = server.DNSServerFactory()
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.sendReply,
            protocol=RaisingProtocol(),
            message=m,
            address=None)
        args, kwargs = e.args
        self.assertEqual(args, (m,))
        self.assertEqual(kwargs, {})


    def test_sendReplyLoggingNoAnswers(self):
        """
        If L{server.DNSServerFactory.sendReply} logs a "no answers" message if
        the supplied message has no answers.
        """
        self.patch(server.time, 'time', lambda: 2)
        m = dns.Message()
        m.timeReceived = 1
        f = server.DNSServerFactory(verbose=2)
        assertLogMessage(
            self,
            ["Replying with no answers", "Processed query in 1.000 seconds"],
            f.sendReply,
            protocol=NoopProtocol(),
            message=m,
            address=None)


    def test_sendReplyLoggingWithAnswers(self):
        """
        If L{server.DNSServerFactory.sendReply} logs a message for answers,
        authority, additional if the supplied a message has records in any of
        those sections.
        """
        self.patch(server.time, 'time', lambda: 2)
        m = dns.Message()
        m.answers.append(dns.RRHeader(payload=dns.Record_A('127.0.0.1')))
        m.authority.append(dns.RRHeader(payload=dns.Record_A('127.0.0.1')))
        m.additional.append(dns.RRHeader(payload=dns.Record_A('127.0.0.1')))
        m.timeReceived = 1
        f = server.DNSServerFactory(verbose=2)
        assertLogMessage(
            self,
            ['Answers are <A address=127.0.0.1 ttl=None>',
             'Authority is <A address=127.0.0.1 ttl=None>',
             'Additional is <A address=127.0.0.1 ttl=None>',
             'Processed query in 1.000 seconds'],
            f.sendReply,
            protocol=NoopProtocol(),
            message=m,
            address=None)


    def test_handleInverseQuery(self):
        """
        L{server.DNSServerFactory.handleInverseQuery} triggers the sending of a
        response message with C{rCode} set to L{dns.ENOTIMP}.
        """
        f = server.DNSServerFactory()
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.handleInverseQuery,
            message=dns.Message(), protocol=RaisingProtocol(), address=None)
        (message,), kwargs = e.args

        self.assertEqual(message.rCode, dns.ENOTIMP)


    def test_handleInverseQueryLogging(self):
        """
        L{server.DNSServerFactory.handleInverseQuery} logs the message origin
        address if C{verbose > 0}.
        """
        f = NoResponseDNSServerFactory(verbose=1)
        assertLogMessage(
            self,
            ["Inverse query from ('::1', 53)"],
            f.handleInverseQuery,
            message=dns.Message(),
            protocol=NoopProtocol(),
            address=('::1', 53))


    def test_handleStatus(self):
        """
        L{server.DNSServerFactory.handleStatus} triggers the sending of a
        response message with C{rCode} set to L{dns.ENOTIMP}.
        """
        f = server.DNSServerFactory()
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.handleStatus,
            message=dns.Message(), protocol=RaisingProtocol(), address=None)
        (message,), kwargs = e.args

        self.assertEqual(message.rCode, dns.ENOTIMP)


    def test_handleStatusLogging(self):
        """
        L{server.DNSServerFactory.handleStatus} logs the message origin address
        if C{verbose > 0}.
        """
        f = NoResponseDNSServerFactory(verbose=1)
        assertLogMessage(
            self,
            ["Status request from ('::1', 53)"],
            f.handleStatus,
            message=dns.Message(),
            protocol=NoopProtocol(),
            address=('::1', 53))


    def test_handleNotify(self):
        """
        L{server.DNSServerFactory.handleNotify} triggers the sending of a
        response message with C{rCode} set to L{dns.ENOTIMP}.
        """
        f = server.DNSServerFactory()
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.handleNotify,
            message=dns.Message(), protocol=RaisingProtocol(), address=None)
        (message,), kwargs = e.args

        self.assertEqual(message.rCode, dns.ENOTIMP)


    def test_handleNotifyLogging(self):
        """
        L{server.DNSServerFactory.handleNotify} logs the message origin address
        if C{verbose > 0}.
        """
        f = NoResponseDNSServerFactory(verbose=1)
        assertLogMessage(
            self,
            ["Notify message from ('::1', 53)"],
            f.handleNotify,
            message=dns.Message(),
            protocol=NoopProtocol(),
            address=('::1', 53))


    def test_handleOther(self):
        """
        L{server.DNSServerFactory.handleOther} triggers the sending of a
        response message with C{rCode} set to L{dns.ENOTIMP}.
        """
        f = server.DNSServerFactory()
        e = self.assertRaises(
            RaisingProtocol.WriteMessageArguments,
            f.handleOther,
            message=dns.Message(), protocol=RaisingProtocol(), address=None)
        (message,), kwargs = e.args

        self.assertEqual(message.rCode, dns.ENOTIMP)


    def test_handleOtherLogging(self):
        """
        L{server.DNSServerFactory.handleOther} logs the message origin address
        if C{verbose > 0}.
        """
        f = NoResponseDNSServerFactory(verbose=1)
        assertLogMessage(
            self,
            ["Unknown op code (0) from ('::1', 53)"],
            f.handleOther,
            message=dns.Message(),
            protocol=NoopProtocol(),
            address=('::1', 53))
