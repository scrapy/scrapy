# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.twcgi}.
"""

import json
import os
import sys
from io import BytesIO

from twisted.internet import address, error, interfaces, reactor
from twisted.internet.error import ConnectionLost
from twisted.python import failure, log, util
from twisted.trial import unittest
from twisted.web import client, http, http_headers, resource, server, twcgi
from twisted.web.http import INTERNAL_SERVER_ERROR, NOT_FOUND
from twisted.web.test._util import _render
from twisted.web.test.requesthelper import DummyChannel, DummyRequest

DUMMY_CGI = """\
print("Header: OK")
print("")
print("cgi output")
"""

DUAL_HEADER_CGI = """\
print("Header: spam")
print("Header: eggs")
print("")
print("cgi output")
"""

BROKEN_HEADER_CGI = """\
print("XYZ")
print("")
print("cgi output")
"""

SPECIAL_HEADER_CGI = """\
print("Server: monkeys")
print("Date: last year")
print("")
print("cgi output")
"""

READINPUT_CGI = """\
# This is an example of a correctly-written CGI script which reads a body
# from stdin, which only reads env['CONTENT_LENGTH'] bytes.

import os, sys

body_length = int(os.environ.get('CONTENT_LENGTH',0))
indata = sys.stdin.read(body_length)
print("Header: OK")
print("")
print("readinput ok")
"""

READALLINPUT_CGI = """\
# This is an example of the typical (incorrect) CGI script which expects
# the server to close stdin when the body of the request is complete.
# A correct CGI should only read env['CONTENT_LENGTH'] bytes.

import sys

indata = sys.stdin.read()
print("Header: OK")
print("")
print("readallinput ok")
"""

NO_DUPLICATE_CONTENT_TYPE_HEADER_CGI = """\
print("content-type: text/cgi-duplicate-test")
print("")
print("cgi output")
"""

HEADER_OUTPUT_CGI = """\
import json
import os
print("")
print("")
vals = {x:y for x,y in os.environ.items() if x.startswith("HTTP_")}
print(json.dumps(vals))
"""

URL_PARAMETER_CGI = """\
import cgi
fs = cgi.FieldStorage()
param = fs.getvalue("param")
print("Header: OK")
print("")
print(param)
"""


class PythonScript(twcgi.FilteredScript):
    filter = sys.executable


class _StartServerAndTearDownMixin:
    def startServer(self, cgi):
        root = resource.Resource()
        cgipath = util.sibpath(__file__, cgi)
        root.putChild(b"cgi", PythonScript(cgipath))
        site = server.Site(root)
        self.p = reactor.listenTCP(0, site)
        return self.p.getHost().port

    def tearDown(self):
        if getattr(self, "p", None):
            return self.p.stopListening()

    def writeCGI(self, source):
        cgiFilename = os.path.abspath(self.mktemp())
        with open(cgiFilename, "wt") as cgiFile:
            cgiFile.write(source)
        return cgiFilename


class CGITests(_StartServerAndTearDownMixin, unittest.TestCase):
    """
    Tests for L{twcgi.FilteredScript}.
    """

    if not interfaces.IReactorProcess.providedBy(reactor):
        skip = "CGI tests require a functional reactor.spawnProcess()"

    def test_CGI(self):
        cgiFilename = self.writeCGI(DUMMY_CGI)

        portnum = self.startServer(cgiFilename)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        d = client.Agent(reactor).request(b"GET", url)
        d.addCallback(client.readBody)
        d.addCallback(self._testCGI_1)
        return d

    def _testCGI_1(self, res):
        self.assertEqual(res, b"cgi output" + os.linesep.encode("ascii"))

    def test_protectedServerAndDate(self):
        """
        If the CGI script emits a I{Server} or I{Date} header, these are
        ignored.
        """
        cgiFilename = self.writeCGI(SPECIAL_HEADER_CGI)

        portnum = self.startServer(cgiFilename)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        agent = client.Agent(reactor)
        d = agent.request(b"GET", url)
        d.addCallback(discardBody)

        def checkResponse(response):
            self.assertNotIn("monkeys", response.headers.getRawHeaders("server"))
            self.assertNotIn("last year", response.headers.getRawHeaders("date"))

        d.addCallback(checkResponse)
        return d

    def test_noDuplicateContentTypeHeaders(self):
        """
        If the CGI script emits a I{content-type} header, make sure that the
        server doesn't add an additional (duplicate) one, as per ticket 4786.
        """
        cgiFilename = self.writeCGI(NO_DUPLICATE_CONTENT_TYPE_HEADER_CGI)

        portnum = self.startServer(cgiFilename)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        agent = client.Agent(reactor)
        d = agent.request(b"GET", url)
        d.addCallback(discardBody)

        def checkResponse(response):
            self.assertEqual(
                response.headers.getRawHeaders("content-type"),
                ["text/cgi-duplicate-test"],
            )
            return response

        d.addCallback(checkResponse)
        return d

    def test_noProxyPassthrough(self):
        """
        The CGI script is never called with the Proxy header passed through.
        """
        cgiFilename = self.writeCGI(HEADER_OUTPUT_CGI)

        portnum = self.startServer(cgiFilename)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")

        agent = client.Agent(reactor)

        headers = http_headers.Headers(
            {b"Proxy": [b"foo"], b"X-Innocent-Header": [b"bar"]}
        )
        d = agent.request(b"GET", url, headers=headers)

        def checkResponse(response):
            headers = json.loads(response.decode("ascii"))
            self.assertEqual(
                set(headers.keys()),
                {"HTTP_HOST", "HTTP_CONNECTION", "HTTP_X_INNOCENT_HEADER"},
            )

        d.addCallback(client.readBody)
        d.addCallback(checkResponse)
        return d

    def test_duplicateHeaderCGI(self):
        """
        If a CGI script emits two instances of the same header, both are sent
        in the response.
        """
        cgiFilename = self.writeCGI(DUAL_HEADER_CGI)

        portnum = self.startServer(cgiFilename)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        agent = client.Agent(reactor)
        d = agent.request(b"GET", url)
        d.addCallback(discardBody)

        def checkResponse(response):
            self.assertEqual(response.headers.getRawHeaders("header"), ["spam", "eggs"])

        d.addCallback(checkResponse)
        return d

    def test_malformedHeaderCGI(self):
        """
        Check for the error message in the duplicated header
        """
        cgiFilename = self.writeCGI(BROKEN_HEADER_CGI)

        portnum = self.startServer(cgiFilename)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        agent = client.Agent(reactor)
        d = agent.request(b"GET", url)
        d.addCallback(discardBody)
        loggedMessages = []

        def addMessage(eventDict):
            loggedMessages.append(log.textFromEventDict(eventDict))

        log.addObserver(addMessage)
        self.addCleanup(log.removeObserver, addMessage)

        def checkResponse(ignored):
            self.assertIn(
                "ignoring malformed CGI header: " + repr(b"XYZ"), loggedMessages
            )

        d.addCallback(checkResponse)
        return d

    def test_ReadEmptyInput(self):
        cgiFilename = os.path.abspath(self.mktemp())
        with open(cgiFilename, "wt") as cgiFile:
            cgiFile.write(READINPUT_CGI)

        portnum = self.startServer(cgiFilename)
        agent = client.Agent(reactor)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        d = agent.request(b"GET", url)
        d.addCallback(client.readBody)
        d.addCallback(self._test_ReadEmptyInput_1)
        return d

    test_ReadEmptyInput.timeout = 5  # type: ignore[attr-defined]

    def _test_ReadEmptyInput_1(self, res):
        expected = f"readinput ok{os.linesep}"
        expected = expected.encode("ascii")
        self.assertEqual(res, expected)

    def test_ReadInput(self):
        cgiFilename = os.path.abspath(self.mktemp())
        with open(cgiFilename, "wt") as cgiFile:
            cgiFile.write(READINPUT_CGI)

        portnum = self.startServer(cgiFilename)
        agent = client.Agent(reactor)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        d = agent.request(
            uri=url,
            method=b"POST",
            bodyProducer=client.FileBodyProducer(BytesIO(b"Here is your stdin")),
        )
        d.addCallback(client.readBody)
        d.addCallback(self._test_ReadInput_1)
        return d

    test_ReadInput.timeout = 5  # type: ignore[attr-defined]

    def _test_ReadInput_1(self, res):
        expected = f"readinput ok{os.linesep}"
        expected = expected.encode("ascii")
        self.assertEqual(res, expected)

    def test_ReadAllInput(self):
        cgiFilename = os.path.abspath(self.mktemp())
        with open(cgiFilename, "wt") as cgiFile:
            cgiFile.write(READALLINPUT_CGI)

        portnum = self.startServer(cgiFilename)
        url = "http://localhost:%d/cgi" % (portnum,)
        url = url.encode("ascii")
        d = client.Agent(reactor).request(
            uri=url,
            method=b"POST",
            bodyProducer=client.FileBodyProducer(BytesIO(b"Here is your stdin")),
        )
        d.addCallback(client.readBody)
        d.addCallback(self._test_ReadAllInput_1)
        return d

    test_ReadAllInput.timeout = 5  # type: ignore[attr-defined]

    def _test_ReadAllInput_1(self, res):
        expected = f"readallinput ok{os.linesep}"
        expected = expected.encode("ascii")
        self.assertEqual(res, expected)

    def test_useReactorArgument(self):
        """
        L{twcgi.FilteredScript.runProcess} uses the reactor passed as an
        argument to the constructor.
        """

        class FakeReactor:
            """
            A fake reactor recording whether spawnProcess is called.
            """

            called = False

            def spawnProcess(self, *args, **kwargs):
                """
                Set the C{called} flag to C{True} if C{spawnProcess} is called.

                @param args: Positional arguments.
                @param kwargs: Keyword arguments.
                """
                self.called = True

        fakeReactor = FakeReactor()
        request = DummyRequest(["a", "b"])
        request.client = address.IPv4Address("TCP", "127.0.0.1", 12345)
        resource = twcgi.FilteredScript("dummy-file", reactor=fakeReactor)
        _render(resource, request)

        self.assertTrue(fakeReactor.called)


class CGIScriptTests(_StartServerAndTearDownMixin, unittest.TestCase):
    """
    Tests for L{twcgi.CGIScript}.
    """

    def test_urlParameters(self):
        """
        If the CGI script is passed URL parameters, do not fall over,
        as per ticket 9887.
        """
        cgiFilename = self.writeCGI(URL_PARAMETER_CGI)
        portnum = self.startServer(cgiFilename)
        url = b"http://localhost:%d/cgi?param=1234" % (portnum,)
        agent = client.Agent(reactor)
        d = agent.request(b"GET", url)
        d.addCallback(client.readBody)
        d.addCallback(self._test_urlParameters_1)
        return d

    def _test_urlParameters_1(self, res):
        expected = f"1234{os.linesep}"
        expected = expected.encode("ascii")
        self.assertEqual(res, expected)

    def test_pathInfo(self):
        """
        L{twcgi.CGIScript.render} sets the process environment
        I{PATH_INFO} from the request path.
        """

        class FakeReactor:
            """
            A fake reactor recording the environment passed to spawnProcess.
            """

            def spawnProcess(self, process, filename, args, env, wdir):
                """
                Store the C{env} L{dict} to an instance attribute.

                @param process: Ignored
                @param filename: Ignored
                @param args: Ignored
                @param env: The environment L{dict} which will be stored
                @param wdir: Ignored
                """
                self.process_env = env

        _reactor = FakeReactor()
        resource = twcgi.CGIScript(self.mktemp(), reactor=_reactor)
        request = DummyRequest(["a", "b"])
        request.client = address.IPv4Address("TCP", "127.0.0.1", 12345)
        _render(resource, request)

        self.assertEqual(_reactor.process_env["PATH_INFO"], "/a/b")


class CGIDirectoryTests(unittest.TestCase):
    """
    Tests for L{twcgi.CGIDirectory}.
    """

    def test_render(self):
        """
        L{twcgi.CGIDirectory.render} sets the HTTP response code to I{NOT
        FOUND}.
        """
        resource = twcgi.CGIDirectory(self.mktemp())
        request = DummyRequest([""])
        d = _render(resource, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, NOT_FOUND)

        d.addCallback(cbRendered)
        return d

    def test_notFoundChild(self):
        """
        L{twcgi.CGIDirectory.getChild} returns a resource which renders an
        response with the HTTP I{NOT FOUND} status code if the indicated child
        does not exist as an entry in the directory used to initialized the
        L{twcgi.CGIDirectory}.
        """
        path = self.mktemp()
        os.makedirs(path)
        resource = twcgi.CGIDirectory(path)
        request = DummyRequest(["foo"])
        child = resource.getChild("foo", request)
        d = _render(child, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, NOT_FOUND)

        d.addCallback(cbRendered)
        return d


class CGIProcessProtocolTests(unittest.TestCase):
    """
    Tests for L{twcgi.CGIProcessProtocol}.
    """

    def test_prematureEndOfHeaders(self):
        """
        If the process communicating with L{CGIProcessProtocol} ends before
        finishing writing out headers, the response has I{INTERNAL SERVER
        ERROR} as its status code.
        """
        request = DummyRequest([""])
        protocol = twcgi.CGIProcessProtocol(request)
        protocol.processEnded(failure.Failure(error.ProcessTerminated()))
        self.assertEqual(request.responseCode, INTERNAL_SERVER_ERROR)

    def test_connectionLost(self):
        """
        Ensure that the CGI process ends cleanly when the request connection
        is lost.
        """
        d = DummyChannel()
        request = http.Request(d, True)
        protocol = twcgi.CGIProcessProtocol(request)
        request.connectionLost(failure.Failure(ConnectionLost("Connection done")))
        protocol.processEnded(failure.Failure(error.ProcessTerminated()))


def discardBody(response):
    """
    Discard the body of a HTTP response.

    @param response: The response.

    @return: The response.
    """
    return client.readBody(response).addCallback(lambda _: response)
