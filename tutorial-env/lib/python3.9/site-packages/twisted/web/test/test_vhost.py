# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.vhost}.
"""


from twisted.internet.defer import gatherResults
from twisted.trial.unittest import TestCase
from twisted.web.http import NOT_FOUND
from twisted.web.resource import NoResource
from twisted.web.server import Site
from twisted.web.static import Data
from twisted.web.test._util import _render
from twisted.web.test.test_web import DummyRequest
from twisted.web.vhost import NameVirtualHost, VHostMonsterResource, _HostResource


class HostResourceTests(TestCase):
    """
    Tests for L{_HostResource}.
    """

    def test_getChild(self):
        """
        L{_HostResource.getChild} returns the proper I{Resource} for the vhost
        embedded in the URL.  Verify that returning the proper I{Resource}
        required changing the I{Host} in the header.
        """
        bazroot = Data(b"root data", "")
        bazuri = Data(b"uri data", "")
        baztest = Data(b"test data", "")
        bazuri.putChild(b"test", baztest)
        bazroot.putChild(b"uri", bazuri)
        hr = _HostResource()

        root = NameVirtualHost()
        root.default = Data(b"default data", "")
        root.addHost(b"baz.com", bazroot)

        request = DummyRequest([b"uri", b"test"])
        request.prepath = [b"bar", b"http", b"baz.com"]
        request.site = Site(root)
        request.isSecure = lambda: False
        request.host = b""

        step = hr.getChild(b"baz.com", request)  # Consumes rest of path
        self.assertIsInstance(step, Data)

        request = DummyRequest([b"uri", b"test"])
        step = root.getChild(b"uri", request)
        self.assertIsInstance(step, NoResource)


class NameVirtualHostTests(TestCase):
    """
    Tests for L{NameVirtualHost}.
    """

    def test_renderWithoutHost(self):
        """
        L{NameVirtualHost.render} returns the result of rendering the
        instance's C{default} if it is not L{None} and there is no I{Host}
        header in the request.
        """
        virtualHostResource = NameVirtualHost()
        virtualHostResource.default = Data(b"correct result", "")
        request = DummyRequest([b""])
        self.assertEqual(virtualHostResource.render(request), b"correct result")

    def test_renderWithoutHostNoDefault(self):
        """
        L{NameVirtualHost.render} returns a response with a status of I{NOT
        FOUND} if the instance's C{default} is L{None} and there is no I{Host}
        header in the request.
        """
        virtualHostResource = NameVirtualHost()
        request = DummyRequest([b""])
        d = _render(virtualHostResource, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, NOT_FOUND)

        d.addCallback(cbRendered)
        return d

    def test_renderWithHost(self):
        """
        L{NameVirtualHost.render} returns the result of rendering the resource
        which is the value in the instance's C{host} dictionary corresponding
        to the key indicated by the value of the I{Host} header in the request.
        """
        virtualHostResource = NameVirtualHost()
        virtualHostResource.addHost(b"example.org", Data(b"winner", ""))

        request = DummyRequest([b""])
        request.requestHeaders.addRawHeader(b"host", b"example.org")
        d = _render(virtualHostResource, request)

        def cbRendered(ignored, request):
            self.assertEqual(b"".join(request.written), b"winner")

        d.addCallback(cbRendered, request)

        # The port portion of the Host header should not be considered.
        requestWithPort = DummyRequest([b""])
        requestWithPort.requestHeaders.addRawHeader(b"host", b"example.org:8000")
        dWithPort = _render(virtualHostResource, requestWithPort)

        def cbRendered(ignored, requestWithPort):
            self.assertEqual(b"".join(requestWithPort.written), b"winner")

        dWithPort.addCallback(cbRendered, requestWithPort)

        return gatherResults([d, dWithPort])

    def test_renderWithUnknownHost(self):
        """
        L{NameVirtualHost.render} returns the result of rendering the
        instance's C{default} if it is not L{None} and there is no host
        matching the value of the I{Host} header in the request.
        """
        virtualHostResource = NameVirtualHost()
        virtualHostResource.default = Data(b"correct data", "")
        request = DummyRequest([b""])
        request.requestHeaders.addRawHeader(b"host", b"example.com")
        d = _render(virtualHostResource, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"correct data")

        d.addCallback(cbRendered)
        return d

    def test_renderWithUnknownHostNoDefault(self):
        """
        L{NameVirtualHost.render} returns a response with a status of I{NOT
        FOUND} if the instance's C{default} is L{None} and there is no host
        matching the value of the I{Host} header in the request.
        """
        virtualHostResource = NameVirtualHost()
        request = DummyRequest([b""])
        request.requestHeaders.addRawHeader(b"host", b"example.com")
        d = _render(virtualHostResource, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, NOT_FOUND)

        d.addCallback(cbRendered)
        return d

    async def test_renderWithHTMLHost(self):
        """
        L{NameVirtualHost.render} doesn't echo unescaped HTML when present in
        the I{Host} header.
        """
        virtualHostResource = NameVirtualHost()
        request = DummyRequest([b""])
        request.requestHeaders.addRawHeader(b"host", b"<b>example</b>.com")

        await _render(virtualHostResource, request)

        self.assertNotIn(b"<b>", b"".join(request.written))

    def test_getChild(self):
        """
        L{NameVirtualHost.getChild} returns correct I{Resource} based off
        the header and modifies I{Request} to ensure proper prepath and
        postpath are set.
        """
        virtualHostResource = NameVirtualHost()
        leafResource = Data(b"leaf data", "")
        leafResource.isLeaf = True
        normResource = Data(b"norm data", "")
        virtualHostResource.addHost(b"leaf.example.org", leafResource)
        virtualHostResource.addHost(b"norm.example.org", normResource)

        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"host", b"norm.example.org")
        request.prepath = [b""]

        self.assertIsInstance(virtualHostResource.getChild(b"", request), NoResource)
        self.assertEqual(request.prepath, [b""])
        self.assertEqual(request.postpath, [])

        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"host", b"leaf.example.org")
        request.prepath = [b""]

        self.assertIsInstance(virtualHostResource.getChild(b"", request), Data)
        self.assertEqual(request.prepath, [])
        self.assertEqual(request.postpath, [b""])


class VHostMonsterResourceTests(TestCase):
    """
    Tests for L{VHostMonsterResource}.
    """

    def test_getChild(self):
        """
        L{VHostMonsterResource.getChild} returns I{_HostResource} and modifies
        I{Request} with correct L{Request.isSecure}.
        """
        vhm = VHostMonsterResource()
        request = DummyRequest([])
        self.assertIsInstance(vhm.getChild(b"http", request), _HostResource)
        self.assertFalse(request.isSecure())

        request = DummyRequest([])
        self.assertIsInstance(vhm.getChild(b"https", request), _HostResource)
        self.assertTrue(request.isSecure())
