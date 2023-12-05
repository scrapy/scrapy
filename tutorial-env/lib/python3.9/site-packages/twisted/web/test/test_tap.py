# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.tap}.
"""


import os
import stat
from unittest import skipIf

from twisted.internet import endpoints, reactor
from twisted.internet.interfaces import IReactorUNIX
from twisted.python.filepath import FilePath
from twisted.python.reflect import requireModule
from twisted.python.threadpool import ThreadPool
from twisted.python.usage import UsageError
from twisted.spread.pb import PBServerFactory
from twisted.trial.unittest import TestCase
from twisted.web import demo
from twisted.web.distrib import ResourcePublisher, UserDirectory
from twisted.web.script import PythonScript
from twisted.web.server import Site
from twisted.web.static import Data, File
from twisted.web.tap import (
    Options,
    _AddHeadersResource,
    makePersonalServerFactory,
    makeService,
)
from twisted.web.test.requesthelper import DummyRequest
from twisted.web.twcgi import CGIScript
from twisted.web.wsgi import WSGIResource

application = object()


class ServiceTests(TestCase):
    """
    Tests for the service creation APIs in L{twisted.web.tap}.
    """

    def _pathOption(self):
        """
        Helper for the I{--path} tests which creates a directory and creates
        an L{Options} object which uses that directory as its static
        filesystem root.

        @return: A two-tuple of a L{FilePath} referring to the directory and
            the value associated with the C{'root'} key in the L{Options}
            instance after parsing a I{--path} option.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        options = Options()
        options.parseOptions(["--path", path.path])
        root = options["root"]
        return path, root

    def test_path(self):
        """
        The I{--path} option causes L{Options} to create a root resource
        which serves responses from the specified path.
        """
        path, root = self._pathOption()
        self.assertIsInstance(root, File)
        self.assertEqual(root.path, path.path)

    @skipIf(
        not IReactorUNIX.providedBy(reactor),
        "The reactor does not support UNIX domain sockets",
    )
    def test_pathServer(self):
        """
        The I{--path} option to L{makeService} causes it to return a service
        which will listen on the server address given by the I{--port} option.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        port = self.mktemp()
        options = Options()
        options.parseOptions(["--port", "unix:" + port, "--path", path.path])
        service = makeService(options)
        service.startService()
        self.addCleanup(service.stopService)
        self.assertIsInstance(service.services[0].factory.resource, File)
        self.assertEqual(service.services[0].factory.resource.path, path.path)
        self.assertTrue(os.path.exists(port))
        self.assertTrue(stat.S_ISSOCK(os.stat(port).st_mode))

    def test_cgiProcessor(self):
        """
        The I{--path} option creates a root resource which serves a
        L{CGIScript} instance for any child with the C{".cgi"} extension.
        """
        path, root = self._pathOption()
        path.child("foo.cgi").setContent(b"")
        self.assertIsInstance(root.getChild("foo.cgi", None), CGIScript)

    def test_epyProcessor(self):
        """
        The I{--path} option creates a root resource which serves a
        L{PythonScript} instance for any child with the C{".epy"} extension.
        """
        path, root = self._pathOption()
        path.child("foo.epy").setContent(b"")
        self.assertIsInstance(root.getChild("foo.epy", None), PythonScript)

    def test_rpyProcessor(self):
        """
        The I{--path} option creates a root resource which serves the
        C{resource} global defined by the Python source in any child with
        the C{".rpy"} extension.
        """
        path, root = self._pathOption()
        path.child("foo.rpy").setContent(
            b"from twisted.web.static import Data\n"
            b"resource = Data('content', 'major/minor')\n"
        )
        child = root.getChild("foo.rpy", None)
        self.assertIsInstance(child, Data)
        self.assertEqual(child.data, "content")
        self.assertEqual(child.type, "major/minor")

    def test_makePersonalServerFactory(self):
        """
        L{makePersonalServerFactory} returns a PB server factory which has
        as its root object a L{ResourcePublisher}.
        """
        # The fact that this pile of objects can actually be used somehow is
        # verified by twisted.web.test.test_distrib.
        site = Site(Data(b"foo bar", "text/plain"))
        serverFactory = makePersonalServerFactory(site)
        self.assertIsInstance(serverFactory, PBServerFactory)
        self.assertIsInstance(serverFactory.root, ResourcePublisher)
        self.assertIdentical(serverFactory.root.site, site)

    @skipIf(
        not IReactorUNIX.providedBy(reactor),
        "The reactor does not support UNIX domain sockets",
    )
    def test_personalServer(self):
        """
        The I{--personal} option to L{makeService} causes it to return a
        service which will listen on the server address given by the I{--port}
        option.
        """
        port = self.mktemp()
        options = Options()
        options.parseOptions(["--port", "unix:" + port, "--personal"])
        service = makeService(options)
        service.startService()
        self.addCleanup(service.stopService)
        self.assertTrue(os.path.exists(port))
        self.assertTrue(stat.S_ISSOCK(os.stat(port).st_mode))

    @skipIf(
        not IReactorUNIX.providedBy(reactor),
        "The reactor does not support UNIX domain sockets",
    )
    def test_defaultPersonalPath(self):
        """
        If the I{--port} option not specified but the I{--personal} option is,
        L{Options} defaults the port to C{UserDirectory.userSocketName} in the
        user's home directory.
        """
        options = Options()
        options.parseOptions(["--personal"])
        path = os.path.expanduser(os.path.join("~", UserDirectory.userSocketName))
        self.assertEqual(options["ports"][0], f"unix:{path}")

    def test_defaultPort(self):
        """
        If the I{--port} option is not specified, L{Options} defaults the port
        to C{8080}.
        """
        options = Options()
        options.parseOptions([])
        self.assertEqual(
            endpoints._parseServer(options["ports"][0], None)[:2], ("TCP", (8080, None))
        )

    def test_twoPorts(self):
        """
        If the I{--http} option is given twice, there are two listeners
        """
        options = Options()
        options.parseOptions(["--listen", "tcp:8001", "--listen", "tcp:8002"])
        self.assertIn("8001", options["ports"][0])
        self.assertIn("8002", options["ports"][1])

    def test_wsgi(self):
        """
        The I{--wsgi} option takes the fully-qualifed Python name of a WSGI
        application object and creates a L{WSGIResource} at the root which
        serves that application.
        """
        options = Options()
        options.parseOptions(["--wsgi", __name__ + ".application"])
        root = options["root"]
        self.assertTrue(root, WSGIResource)
        self.assertIdentical(root._reactor, reactor)
        self.assertTrue(isinstance(root._threadpool, ThreadPool))
        self.assertIdentical(root._application, application)

        # The threadpool should start and stop with the reactor.
        self.assertFalse(root._threadpool.started)
        reactor.fireSystemEvent("startup")
        self.assertTrue(root._threadpool.started)
        self.assertFalse(root._threadpool.joined)
        reactor.fireSystemEvent("shutdown")
        self.assertTrue(root._threadpool.joined)

    def test_invalidApplication(self):
        """
        If I{--wsgi} is given an invalid name, L{Options.parseOptions}
        raises L{UsageError}.
        """
        options = Options()
        for name in [__name__ + ".nosuchthing", "foo."]:
            exc = self.assertRaises(UsageError, options.parseOptions, ["--wsgi", name])
            self.assertEqual(str(exc), f"No such WSGI application: {name!r}")

    @skipIf(requireModule("OpenSSL.SSL") is not None, "SSL module is available.")
    def test_HTTPSFailureOnMissingSSL(self):
        """
        An L{UsageError} is raised when C{https} is requested but there is no
        support for SSL.
        """
        options = Options()

        exception = self.assertRaises(UsageError, options.parseOptions, ["--https=443"])

        self.assertEqual("SSL support not installed", exception.args[0])

    @skipIf(requireModule("OpenSSL.SSL") is None, "SSL module is not available.")
    def test_HTTPSAcceptedOnAvailableSSL(self):
        """
        When SSL support is present, it accepts the --https option.
        """
        options = Options()

        options.parseOptions(["--https=443"])

        self.assertIn("ssl", options["ports"][0])
        self.assertIn("443", options["ports"][0])

    def test_add_header_parsing(self):
        """
        When --add-header is specific, the value is parsed.
        """
        options = Options()
        options.parseOptions(["--add-header", "K1: V1", "--add-header", "K2: V2"])
        self.assertEqual(options["extraHeaders"], [("K1", "V1"), ("K2", "V2")])

    def test_add_header_resource(self):
        """
        When --add-header is specified, the resource is a composition that adds
        headers.
        """
        options = Options()
        options.parseOptions(["--add-header", "K1: V1", "--add-header", "K2: V2"])
        service = makeService(options)
        resource = service.services[0].factory.resource
        self.assertIsInstance(resource, _AddHeadersResource)
        self.assertEqual(resource._headers, [("K1", "V1"), ("K2", "V2")])
        self.assertIsInstance(resource._originalResource, demo.Test)

    def test_noTracebacksDeprecation(self):
        """
        Passing --notracebacks is deprecated.
        """
        options = Options()
        options.parseOptions(["--notracebacks"])
        makeService(options)

        warnings = self.flushWarnings([self.test_noTracebacksDeprecation])
        self.assertEqual(warnings[0]["category"], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"], "--notracebacks was deprecated in Twisted 19.7.0"
        )
        self.assertEqual(len(warnings), 1)

    def test_displayTracebacks(self):
        """
        Passing --display-tracebacks will enable traceback rendering on the
        generated Site.
        """
        options = Options()
        options.parseOptions(["--display-tracebacks"])
        service = makeService(options)
        self.assertTrue(service.services[0].factory.displayTracebacks)

    def test_displayTracebacksNotGiven(self):
        """
        Not passing --display-tracebacks will leave traceback rendering on the
        generated Site off.
        """
        options = Options()
        options.parseOptions([])
        service = makeService(options)
        self.assertFalse(service.services[0].factory.displayTracebacks)


class AddHeadersResourceTests(TestCase):
    def test_getChildWithDefault(self):
        """
        When getChildWithDefault is invoked, it adds the headers to the
        response.
        """
        resource = _AddHeadersResource(
            demo.Test(), [("K1", "V1"), ("K2", "V2"), ("K1", "V3")]
        )
        request = DummyRequest([])
        resource.getChildWithDefault("", request)
        self.assertEqual(request.responseHeaders.getRawHeaders("K1"), ["V1", "V3"])
        self.assertEqual(request.responseHeaders.getRawHeaders("K2"), ["V2"])
