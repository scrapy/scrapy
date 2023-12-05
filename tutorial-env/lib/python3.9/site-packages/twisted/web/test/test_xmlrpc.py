# -*- test-case-name: twisted.web.test.test_xmlrpc -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for  XML-RPC support in L{twisted.web.xmlrpc}.
"""


import datetime
from io import BytesIO, StringIO
from unittest import skipIf

from twisted.internet import defer, reactor
from twisted.internet.error import ConnectionDone
from twisted.logger import (
    FilteringLogObserver,
    LogLevel,
    LogLevelFilterPredicate,
    globalLogPublisher,
)
from twisted.python import failure
from twisted.python.compat import nativeString, networkString
from twisted.python.reflect import namedModule
from twisted.test.proto_helpers import EventLoggingObserver, MemoryReactor
from twisted.trial import unittest
from twisted.web import client, http, server, static, xmlrpc
from twisted.web.test.test_web import DummyRequest
from twisted.web.xmlrpc import (
    XMLRPC,
    QueryFactory,
    addIntrospection,
    payloadTemplate,
    withRequest,
    xmlrpclib,
)

try:
    namedModule("twisted.internet.ssl")
except ImportError:
    sslSkip = True
else:
    sslSkip = False


class AsyncXMLRPCTests(unittest.TestCase):
    """
    Tests for L{XMLRPC}'s support of Deferreds.
    """

    def setUp(self):
        self.request = DummyRequest([""])
        self.request.method = "POST"
        self.request.content = StringIO(
            payloadTemplate % ("async", xmlrpclib.dumps(()))
        )

        result = self.result = defer.Deferred()

        class AsyncResource(XMLRPC):
            def xmlrpc_async(self):
                return result

        self.resource = AsyncResource()

    def test_deferredResponse(self):
        """
        If an L{XMLRPC} C{xmlrpc_*} method returns a L{defer.Deferred}, the
        response to the request is the result of that L{defer.Deferred}.
        """
        self.resource.render(self.request)
        self.assertEqual(self.request.written, [])

        self.result.callback("result")

        resp = xmlrpclib.loads(b"".join(self.request.written))
        self.assertEqual(resp, (("result",), None))
        self.assertEqual(self.request.finished, 1)

    def test_interruptedDeferredResponse(self):
        """
        While waiting for the L{Deferred} returned by an L{XMLRPC} C{xmlrpc_*}
        method to fire, the connection the request was issued over may close.
        If this happens, neither C{write} nor C{finish} is called on the
        request.
        """
        self.resource.render(self.request)
        self.request.processingFailed(failure.Failure(ConnectionDone("Simulated")))
        self.result.callback("result")
        self.assertEqual(self.request.written, [])
        self.assertEqual(self.request.finished, 0)


class TestRuntimeError(RuntimeError):
    pass


class TestValueError(ValueError):
    pass


class Test(XMLRPC):

    # If you add xmlrpc_ methods to this class, go change test_listMethods
    # below.

    FAILURE = 666
    NOT_FOUND = 23
    SESSION_EXPIRED = 42

    def xmlrpc_echo(self, arg):
        return arg

    # the doc string is part of the test
    def xmlrpc_add(self, a, b):
        """
        This function add two numbers.
        """
        return a + b

    xmlrpc_add.signature = [  # type: ignore[attr-defined]
        ["int", "int", "int"],
        ["double", "double", "double"],
    ]

    # the doc string is part of the test
    def xmlrpc_pair(self, string, num):
        """
        This function puts the two arguments in an array.
        """
        return [string, num]

    xmlrpc_pair.signature = [["array", "string", "int"]]  # type: ignore[attr-defined]

    # the doc string is part of the test
    def xmlrpc_defer(self, x):
        """Help for defer."""
        return defer.succeed(x)

    def xmlrpc_deferFail(self):
        return defer.fail(TestValueError())

    # don't add a doc string, it's part of the test
    def xmlrpc_fail(self):
        raise TestRuntimeError

    def xmlrpc_fault(self):
        return xmlrpc.Fault(12, "hello")

    def xmlrpc_deferFault(self):
        return defer.fail(xmlrpc.Fault(17, "hi"))

    def xmlrpc_snowman(self, payload):
        """
        Used to test that we can pass Unicode.
        """
        snowman = "\u2603"
        if snowman != payload:
            return xmlrpc.Fault(13, "Payload not unicode snowman")
        return snowman

    def xmlrpc_complex(self):
        return {"a": ["b", "c", 12, []], "D": "foo"}

    def xmlrpc_dict(self, map, key):
        return map[key]

    xmlrpc_dict.help = "Help for dict."  # type: ignore[attr-defined]

    @withRequest
    def xmlrpc_withRequest(self, request, other):
        """
        A method decorated with L{withRequest} which can be called by
        a test to verify that the request object really is passed as
        an argument.
        """
        return (
            # as a proof that request is a request
            request.method
            +
            # plus proof other arguments are still passed along
            " "
            + other
        )

    def lookupProcedure(self, procedurePath):
        try:
            return XMLRPC.lookupProcedure(self, procedurePath)
        except xmlrpc.NoSuchFunction:
            if procedurePath.startswith("SESSION"):
                raise xmlrpc.Fault(
                    self.SESSION_EXPIRED, "Session non-existent/expired."
                )
            else:
                raise


class TestLookupProcedure(XMLRPC):
    """
    This is a resource which customizes procedure lookup to be used by the tests
    of support for this customization.
    """

    def echo(self, x):
        return x

    def lookupProcedure(self, procedureName):
        """
        Lookup a procedure from a fixed set of choices, either I{echo} or
        I{system.listeMethods}.
        """
        if procedureName == "echo":
            return self.echo
        raise xmlrpc.NoSuchFunction(
            self.NOT_FOUND, f"procedure {procedureName} not found"
        )


class TestListProcedures(XMLRPC):
    """
    This is a resource which customizes procedure enumeration to be used by the
    tests of support for this customization.
    """

    def listProcedures(self):
        """
        Return a list of a single method this resource will claim to support.
        """
        return ["foo"]


class TestAuthHeader(Test):
    """
    This is used to get the header info so that we can test
    authentication.
    """

    def __init__(self):
        Test.__init__(self)
        self.request = None

    def render(self, request):
        self.request = request
        return Test.render(self, request)

    def xmlrpc_authinfo(self):
        return self.request.getUser(), self.request.getPassword()


class TestQueryProtocol(xmlrpc.QueryProtocol):
    """
    QueryProtocol for tests that saves headers received and sent,
    inside the factory.
    """

    def connectionMade(self):
        self.factory.transport = self.transport
        xmlrpc.QueryProtocol.connectionMade(self)

    def handleHeader(self, key, val):
        self.factory.headers[key.lower()] = val

    def sendHeader(self, key, val):
        """
        Keep sent headers so we can inspect them later.
        """
        self.factory.sent_headers[key.lower()] = val
        xmlrpc.QueryProtocol.sendHeader(self, key, val)


class TestQueryFactory(xmlrpc.QueryFactory):
    """
    QueryFactory using L{TestQueryProtocol} for saving headers.
    """

    protocol = TestQueryProtocol

    def __init__(self, *args, **kwargs):
        self.headers = {}
        self.sent_headers = {}
        xmlrpc.QueryFactory.__init__(self, *args, **kwargs)


class TestQueryFactoryCancel(xmlrpc.QueryFactory):
    """
    QueryFactory that saves a reference to the
    L{twisted.internet.interfaces.IConnector} to test connection lost.
    """

    def startedConnecting(self, connector):
        self.connector = connector


class XMLRPCTests(unittest.TestCase):
    def setUp(self):
        self.p = reactor.listenTCP(0, server.Site(Test()), interface="127.0.0.1")
        self.port = self.p.getHost().port
        self.factories = []

    def tearDown(self):
        self.factories = []
        return self.p.stopListening()

    def queryFactory(self, *args, **kwargs):
        """
        Specific queryFactory for proxy that uses our custom
        L{TestQueryFactory}, and save factories.
        """
        factory = TestQueryFactory(*args, **kwargs)
        self.factories.append(factory)
        return factory

    def proxy(self, factory=None):
        """
        Return a new xmlrpc.Proxy for the test site created in
        setUp(), using the given factory as the queryFactory, or
        self.queryFactory if no factory is provided.
        """
        p = xmlrpc.Proxy(networkString("http://127.0.0.1:%d/" % self.port))
        if factory is None:
            p.queryFactory = self.queryFactory
        else:
            p.queryFactory = factory
        return p

    def test_results(self):
        inputOutput = [
            ("add", (2, 3), 5),
            ("defer", ("a",), "a"),
            ("dict", ({"a": 1}, "a"), 1),
            ("pair", ("a", 1), ["a", 1]),
            ("snowman", ("\u2603"), "\u2603"),
            ("complex", (), {"a": ["b", "c", 12, []], "D": "foo"}),
        ]

        dl = []
        for meth, args, outp in inputOutput:
            d = self.proxy().callRemote(meth, *args)
            d.addCallback(self.assertEqual, outp)
            dl.append(d)
        return defer.DeferredList(dl, fireOnOneErrback=True)

    def test_headers(self):
        """
        Verify that headers sent from the client side and the ones we
        get back from the server side are correct.

        """
        d = self.proxy().callRemote("snowman", "\u2603")

        def check_server_headers(ing):
            self.assertEqual(
                self.factories[0].headers[b"content-type"], b"text/xml; charset=utf-8"
            )
            self.assertEqual(self.factories[0].headers[b"content-length"], b"129")

        def check_client_headers(ign):
            self.assertEqual(
                self.factories[0].sent_headers[b"user-agent"], b"Twisted/XMLRPClib"
            )
            self.assertEqual(
                self.factories[0].sent_headers[b"content-type"],
                b"text/xml; charset=utf-8",
            )
            self.assertEqual(self.factories[0].sent_headers[b"content-length"], b"155")

        d.addCallback(check_server_headers)
        d.addCallback(check_client_headers)
        return d

    def test_errors(self):
        """
        Verify that for each way a method exposed via XML-RPC can fail, the
        correct 'Content-type' header is set in the response and that the
        client-side Deferred is errbacked with an appropriate C{Fault}
        instance.
        """
        logObserver = EventLoggingObserver()
        filtered = FilteringLogObserver(
            logObserver, [LogLevelFilterPredicate(defaultLogLevel=LogLevel.critical)]
        )
        globalLogPublisher.addObserver(filtered)
        self.addCleanup(lambda: globalLogPublisher.removeObserver(filtered))
        dl = []
        for code, methodName in [
            (666, "fail"),
            (666, "deferFail"),
            (12, "fault"),
            (23, "noSuchMethod"),
            (17, "deferFault"),
            (42, "SESSION_TEST"),
        ]:
            d = self.proxy().callRemote(methodName)
            d = self.assertFailure(d, xmlrpc.Fault)
            d.addCallback(lambda exc, code=code: self.assertEqual(exc.faultCode, code))
            dl.append(d)
        d = defer.DeferredList(dl, fireOnOneErrback=True)

        def cb(ign):
            for factory in self.factories:
                self.assertEqual(
                    factory.headers[b"content-type"], b"text/xml; charset=utf-8"
                )
            self.assertEquals(2, len(logObserver))
            f1 = logObserver[0]["log_failure"].value
            f2 = logObserver[1]["log_failure"].value

            if isinstance(f1, TestValueError):
                self.assertIsInstance(f2, TestRuntimeError)
            else:
                self.assertIsInstance(f1, TestRuntimeError)
                self.assertIsInstance(f2, TestValueError)

            self.flushLoggedErrors(TestRuntimeError, TestValueError)

        d.addCallback(cb)
        return d

    def test_cancel(self):
        """
        A deferred from the Proxy can be cancelled, disconnecting
        the L{twisted.internet.interfaces.IConnector}.
        """

        def factory(*args, **kw):
            factory.f = TestQueryFactoryCancel(*args, **kw)
            return factory.f

        d = self.proxy(factory).callRemote("add", 2, 3)
        self.assertNotEqual(factory.f.connector.state, "disconnected")
        d.cancel()
        self.assertEqual(factory.f.connector.state, "disconnected")
        d = self.assertFailure(d, defer.CancelledError)
        return d

    def test_errorGet(self):
        """
        A classic GET on the xml server should return a NOT_ALLOWED.
        """
        agent = client.Agent(reactor)
        d = agent.request(b"GET", networkString("http://127.0.0.1:%d/" % (self.port,)))

        def checkResponse(response):
            self.assertEqual(response.code, http.NOT_ALLOWED)

        d.addCallback(checkResponse)
        return d

    def test_errorXMLContent(self):
        """
        Test that an invalid XML input returns an L{xmlrpc.Fault}.
        """
        agent = client.Agent(reactor)
        d = agent.request(
            uri=networkString("http://127.0.0.1:%d/" % (self.port,)),
            method=b"POST",
            bodyProducer=client.FileBodyProducer(BytesIO(b"foo")),
        )
        d.addCallback(client.readBody)

        def cb(result):
            self.assertRaises(xmlrpc.Fault, xmlrpclib.loads, result)

        d.addCallback(cb)
        return d

    def test_datetimeRoundtrip(self):

        """
        If an L{xmlrpclib.DateTime} is passed as an argument to an XML-RPC
        call and then returned by the server unmodified, the result should
        be equal to the original object.
        """
        when = xmlrpclib.DateTime()
        d = self.proxy().callRemote("echo", when)
        d.addCallback(self.assertEqual, when)
        return d

    def test_doubleEncodingError(self):
        """
        If it is not possible to encode a response to the request (for example,
        because L{xmlrpclib.dumps} raises an exception when encoding a
        L{Fault}) the exception which prevents the response from being
        generated is logged and the request object is finished anyway.
        """
        logObserver = EventLoggingObserver()
        filtered = FilteringLogObserver(
            logObserver, [LogLevelFilterPredicate(defaultLogLevel=LogLevel.critical)]
        )
        globalLogPublisher.addObserver(filtered)
        self.addCleanup(lambda: globalLogPublisher.removeObserver(filtered))
        d = self.proxy().callRemote("echo", "")

        # *Now* break xmlrpclib.dumps.  Hopefully the client already used it.
        def fakeDumps(*args, **kwargs):
            raise RuntimeError("Cannot encode anything at all!")

        self.patch(xmlrpclib, "dumps", fakeDumps)

        # It doesn't matter how it fails, so long as it does.  Also, it happens
        # to fail with an implementation detail exception right now, not
        # something suitable as part of a public interface.
        d = self.assertFailure(d, Exception)

        def cbFailed(ignored):
            # The fakeDumps exception should have been logged.
            self.assertEquals(1, len(logObserver))
            self.assertIsInstance(logObserver[0]["log_failure"].value, RuntimeError)
            self.assertEqual(len(self.flushLoggedErrors(RuntimeError)), 1)

        d.addCallback(cbFailed)
        return d

    def test_closeConnectionAfterRequest(self):
        """
        The connection to the web server is closed when the request is done.
        """
        d = self.proxy().callRemote("echo", "")

        def responseDone(ignored):
            [factory] = self.factories
            self.assertFalse(factory.transport.connected)
            self.assertTrue(factory.transport.disconnected)

        return d.addCallback(responseDone)

    def test_tcpTimeout(self):
        """
        For I{HTTP} URIs, L{xmlrpc.Proxy.callRemote} passes the value it
        received for the C{connectTimeout} parameter as the C{timeout} argument
        to the underlying connectTCP call.
        """
        reactor = MemoryReactor()
        proxy = xmlrpc.Proxy(
            b"http://127.0.0.1:69", connectTimeout=2.0, reactor=reactor
        )
        proxy.callRemote("someMethod")
        self.assertEqual(reactor.tcpClients[0][3], 2.0)

    @skipIf(sslSkip, "OpenSSL not present")
    def test_sslTimeout(self):
        """
        For I{HTTPS} URIs, L{xmlrpc.Proxy.callRemote} passes the value it
        received for the C{connectTimeout} parameter as the C{timeout} argument
        to the underlying connectSSL call.
        """
        reactor = MemoryReactor()
        proxy = xmlrpc.Proxy(
            b"https://127.0.0.1:69", connectTimeout=3.0, reactor=reactor
        )
        proxy.callRemote("someMethod")
        self.assertEqual(reactor.sslClients[0][4], 3.0)


class XMLRPCProxyWithoutSlashTests(XMLRPCTests):
    """
    Test with proxy that doesn't add a slash.
    """

    def proxy(self, factory=None):
        p = xmlrpc.Proxy(networkString("http://127.0.0.1:%d" % self.port))
        if factory is None:
            p.queryFactory = self.queryFactory
        else:
            p.queryFactory = factory
        return p


class XMLRPCPublicLookupProcedureTests(unittest.TestCase):
    """
    Tests for L{XMLRPC}'s support of subclasses which override
    C{lookupProcedure} and C{listProcedures}.
    """

    def createServer(self, resource):
        self.p = reactor.listenTCP(0, server.Site(resource), interface="127.0.0.1")
        self.addCleanup(self.p.stopListening)
        self.port = self.p.getHost().port
        self.proxy = xmlrpc.Proxy(networkString("http://127.0.0.1:%d" % self.port))

    def test_lookupProcedure(self):
        """
        A subclass of L{XMLRPC} can override C{lookupProcedure} to find
        procedures that are not defined using a C{xmlrpc_}-prefixed method name.
        """
        self.createServer(TestLookupProcedure())
        what = "hello"
        d = self.proxy.callRemote("echo", what)
        d.addCallback(self.assertEqual, what)
        return d

    def test_errors(self):
        """
        A subclass of L{XMLRPC} can override C{lookupProcedure} to raise
        L{NoSuchFunction} to indicate that a requested method is not available
        to be called, signalling a fault to the XML-RPC client.
        """
        self.createServer(TestLookupProcedure())
        d = self.proxy.callRemote("xxxx", "hello")
        d = self.assertFailure(d, xmlrpc.Fault)
        return d

    def test_listMethods(self):
        """
        A subclass of L{XMLRPC} can override C{listProcedures} to define
        Overriding listProcedures should prevent introspection from being
        broken.
        """
        resource = TestListProcedures()
        addIntrospection(resource)
        self.createServer(resource)
        d = self.proxy.callRemote("system.listMethods")

        def listed(procedures):
            # The list will also include other introspection procedures added by
            # addIntrospection.  We just want to see "foo" from our customized
            # listProcedures.
            self.assertIn("foo", procedures)

        d.addCallback(listed)
        return d


class SerializationConfigMixin:
    """
    Mixin which defines a couple tests which should pass when a particular flag
    is passed to L{XMLRPC}.

    These are not meant to be exhaustive serialization tests, since L{xmlrpclib}
    does all of the actual serialization work.  They are just meant to exercise
    a few codepaths to make sure we are calling into xmlrpclib correctly.

    @ivar flagName: A C{str} giving the name of the flag which must be passed to
        L{XMLRPC} to allow the tests to pass.  Subclasses should set this.

    @ivar value: A value which the specified flag will allow the serialization
        of.  Subclasses should set this.
    """

    def setUp(self):
        """
        Create a new XML-RPC server with C{allowNone} set to C{True}.
        """
        kwargs = {self.flagName: True}
        self.p = reactor.listenTCP(
            0, server.Site(Test(**kwargs)), interface="127.0.0.1"
        )
        self.addCleanup(self.p.stopListening)
        self.port = self.p.getHost().port
        self.proxy = xmlrpc.Proxy(
            networkString("http://127.0.0.1:%d/" % (self.port,)), **kwargs
        )

    def test_roundtripValue(self):
        """
        C{self.value} can be round-tripped over an XMLRPC method call/response.
        """
        d = self.proxy.callRemote("defer", self.value)
        d.addCallback(self.assertEqual, self.value)
        return d

    def test_roundtripNestedValue(self):
        """
        A C{dict} which contains C{self.value} can be round-tripped over an
        XMLRPC method call/response.
        """
        d = self.proxy.callRemote("defer", {"a": self.value})
        d.addCallback(self.assertEqual, {"a": self.value})
        return d


class XMLRPCAllowNoneTests(SerializationConfigMixin, unittest.TestCase):
    """
    Tests for passing L{None} when the C{allowNone} flag is set.
    """

    flagName = "allowNone"
    value = None


class XMLRPCUseDateTimeTests(SerializationConfigMixin, unittest.TestCase):
    """
    Tests for passing a C{datetime.datetime} instance when the C{useDateTime}
    flag is set.
    """

    flagName = "useDateTime"
    value = datetime.datetime(2000, 12, 28, 3, 45, 59)


class XMLRPCAuthenticatedTests(XMLRPCTests):
    """
    Test with authenticated proxy. We run this with the same input/output as
    above.
    """

    user = b"username"
    password = b"asecret"

    def setUp(self):
        self.p = reactor.listenTCP(
            0, server.Site(TestAuthHeader()), interface="127.0.0.1"
        )
        self.port = self.p.getHost().port
        self.factories = []

    def test_authInfoInURL(self):
        url = "http://%s:%s@127.0.0.1:%d/" % (
            nativeString(self.user),
            nativeString(self.password),
            self.port,
        )
        p = xmlrpc.Proxy(networkString(url))
        d = p.callRemote("authinfo")
        d.addCallback(self.assertEqual, [self.user, self.password])
        return d

    def test_explicitAuthInfo(self):
        p = xmlrpc.Proxy(
            networkString("http://127.0.0.1:%d/" % (self.port,)),
            self.user,
            self.password,
        )
        d = p.callRemote("authinfo")
        d.addCallback(self.assertEqual, [self.user, self.password])
        return d

    def test_longPassword(self):
        """
        C{QueryProtocol} uses the C{base64.b64encode} function to encode user
        name and password in the I{Authorization} header, so that it doesn't
        embed new lines when using long inputs.
        """
        longPassword = self.password * 40
        p = xmlrpc.Proxy(
            networkString("http://127.0.0.1:%d/" % (self.port,)),
            self.user,
            longPassword,
        )
        d = p.callRemote("authinfo")
        d.addCallback(self.assertEqual, [self.user, longPassword])
        return d

    def test_explicitAuthInfoOverride(self):
        p = xmlrpc.Proxy(
            networkString("http://wrong:info@127.0.0.1:%d/" % (self.port,)),
            self.user,
            self.password,
        )
        d = p.callRemote("authinfo")
        d.addCallback(self.assertEqual, [self.user, self.password])
        return d


class XMLRPCIntrospectionTests(XMLRPCTests):
    def setUp(self):
        xmlrpc = Test()
        addIntrospection(xmlrpc)
        self.p = reactor.listenTCP(0, server.Site(xmlrpc), interface="127.0.0.1")
        self.port = self.p.getHost().port
        self.factories = []

    def test_listMethods(self):
        def cbMethods(meths):
            meths.sort()
            self.assertEqual(
                meths,
                [
                    "add",
                    "complex",
                    "defer",
                    "deferFail",
                    "deferFault",
                    "dict",
                    "echo",
                    "fail",
                    "fault",
                    "pair",
                    "snowman",
                    "system.listMethods",
                    "system.methodHelp",
                    "system.methodSignature",
                    "withRequest",
                ],
            )

        d = self.proxy().callRemote("system.listMethods")
        d.addCallback(cbMethods)
        return d

    def test_methodHelp(self):
        inputOutputs = [
            ("defer", "Help for defer."),
            ("fail", ""),
            ("dict", "Help for dict."),
        ]

        dl = []
        for meth, expected in inputOutputs:
            d = self.proxy().callRemote("system.methodHelp", meth)
            d.addCallback(self.assertEqual, expected)
            dl.append(d)
        return defer.DeferredList(dl, fireOnOneErrback=True)

    def test_methodSignature(self):
        inputOutputs = [
            ("defer", ""),
            ("add", [["int", "int", "int"], ["double", "double", "double"]]),
            ("pair", [["array", "string", "int"]]),
        ]

        dl = []
        for meth, expected in inputOutputs:
            d = self.proxy().callRemote("system.methodSignature", meth)
            d.addCallback(self.assertEqual, expected)
            dl.append(d)
        return defer.DeferredList(dl, fireOnOneErrback=True)


class XMLRPCClientErrorHandlingTests(unittest.TestCase):
    """
    Test error handling on the xmlrpc client.
    """

    def setUp(self):
        self.resource = static.Data(
            b"This text is not a valid XML-RPC response.", b"text/plain"
        )
        self.resource.isLeaf = True

        self.port = reactor.listenTCP(
            0, server.Site(self.resource), interface="127.0.0.1"
        )

    def tearDown(self):
        return self.port.stopListening()

    def test_erroneousResponse(self):
        """
        Test that calling the xmlrpc client on a static http server raises
        an exception.
        """
        proxy = xmlrpc.Proxy(
            networkString("http://127.0.0.1:%d/" % (self.port.getHost().port,))
        )
        return self.assertFailure(proxy.callRemote("someMethod"), ValueError)


class QueryFactoryParseResponseTests(unittest.TestCase):
    """
    Test the behaviour of L{QueryFactory.parseResponse}.
    """

    def setUp(self):
        # The QueryFactory that we are testing. We don't care about any
        # of the constructor parameters.
        self.queryFactory = QueryFactory(
            path=None,
            host=None,
            method="POST",
            user=None,
            password=None,
            allowNone=False,
            args=(),
        )
        # An XML-RPC response that will parse without raising an error.
        self.goodContents = xmlrpclib.dumps(("",))
        # An 'XML-RPC response' that will raise a parsing error.
        self.badContents = "invalid xml"
        # A dummy 'reason' to pass to clientConnectionLost. We don't care
        # what it is.
        self.reason = failure.Failure(ConnectionDone())

    def test_parseResponseCallbackSafety(self):
        """
        We can safely call L{QueryFactory.clientConnectionLost} as a callback
        of L{QueryFactory.parseResponse}.
        """
        d = self.queryFactory.deferred
        # The failure mode is that this callback raises an AlreadyCalled
        # error. We have to add it now so that it gets called synchronously
        # and triggers the race condition.
        d.addCallback(self.queryFactory.clientConnectionLost, self.reason)
        self.queryFactory.parseResponse(self.goodContents)
        return d

    def test_parseResponseErrbackSafety(self):
        """
        We can safely call L{QueryFactory.clientConnectionLost} as an errback
        of L{QueryFactory.parseResponse}.
        """
        d = self.queryFactory.deferred
        # The failure mode is that this callback raises an AlreadyCalled
        # error. We have to add it now so that it gets called synchronously
        # and triggers the race condition.
        d.addErrback(self.queryFactory.clientConnectionLost, self.reason)
        self.queryFactory.parseResponse(self.badContents)
        return d

    def test_badStatusErrbackSafety(self):
        """
        We can safely call L{QueryFactory.clientConnectionLost} as an errback
        of L{QueryFactory.badStatus}.
        """
        d = self.queryFactory.deferred
        # The failure mode is that this callback raises an AlreadyCalled
        # error. We have to add it now so that it gets called synchronously
        # and triggers the race condition.
        d.addErrback(self.queryFactory.clientConnectionLost, self.reason)
        self.queryFactory.badStatus("status", "message")
        return d

    def test_parseResponseWithoutData(self):
        """
        Some server can send a response without any data:
        L{QueryFactory.parseResponse} should catch the error and call the
        result errback.
        """
        content = """
<methodResponse>
 <params>
  <param>
  </param>
 </params>
</methodResponse>"""
        d = self.queryFactory.deferred
        self.queryFactory.parseResponse(content)
        return self.assertFailure(d, IndexError)


class XMLRPCWithRequestTests(unittest.TestCase):
    def setUp(self):
        self.resource = Test()

    def test_withRequest(self):
        """
        When an XML-RPC method is called and the implementation is
        decorated with L{withRequest}, the request object is passed as
        the first argument.
        """
        request = DummyRequest("/RPC2")
        request.method = "POST"
        request.content = StringIO(xmlrpclib.dumps(("foo",), "withRequest"))

        def valid(n, request):
            data = xmlrpclib.loads(request.written[0])
            self.assertEqual(data, (("POST foo",), None))

        d = request.notifyFinish().addCallback(valid, request)
        self.resource.render_POST(request)
        return d
