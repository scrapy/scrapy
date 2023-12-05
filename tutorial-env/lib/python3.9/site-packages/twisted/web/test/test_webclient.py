# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests L{twisted.web.client} helper APIs
"""


from urllib.parse import urlparse

from twisted.trial import unittest
from twisted.web import client


class URLJoinTests(unittest.TestCase):
    """
    Tests for L{client._urljoin}.
    """

    def test_noFragments(self):
        """
        L{client._urljoin} does not include a fragment identifier in the
        resulting URL if neither the base nor the new path include a fragment
        identifier.
        """
        self.assertEqual(
            client._urljoin(b"http://foo.com/bar", b"/quux"), b"http://foo.com/quux"
        )
        self.assertEqual(
            client._urljoin(b"http://foo.com/bar#", b"/quux"), b"http://foo.com/quux"
        )
        self.assertEqual(
            client._urljoin(b"http://foo.com/bar", b"/quux#"), b"http://foo.com/quux"
        )

    def test_preserveFragments(self):
        """
        L{client._urljoin} preserves the fragment identifier from either the
        new path or the base URL respectively, as specified in the HTTP 1.1 bis
        draft.

        @see: U{https://tools.ietf.org/html/draft-ietf-httpbis-p2-semantics-22#section-7.1.2}
        """
        self.assertEqual(
            client._urljoin(b"http://foo.com/bar#frag", b"/quux"),
            b"http://foo.com/quux#frag",
        )
        self.assertEqual(
            client._urljoin(b"http://foo.com/bar", b"/quux#frag2"),
            b"http://foo.com/quux#frag2",
        )
        self.assertEqual(
            client._urljoin(b"http://foo.com/bar#frag", b"/quux#frag2"),
            b"http://foo.com/quux#frag2",
        )


class URITests:
    """
    Abstract tests for L{twisted.web.client.URI}.

    Subclass this and L{unittest.TestCase}. Then provide a value for
    C{host} and C{uriHost}.

    @ivar host: A host specification for use in tests, must be L{bytes}.

    @ivar uriHost: The host specification in URI form, must be a L{bytes}. In
        most cases this is identical with C{host}. IPv6 address literals are an
        exception, according to RFC 3986 section 3.2.2, as they need to be
        enclosed in brackets. In this case this variable is different.
    """

    def makeURIString(self, template):
        """
        Replace the string "HOST" in C{template} with this test's host.

        Byte strings Python between (and including) versions 3.0 and 3.4
        cannot be formatted using C{%} or C{format} so this does a simple
        replace.

        @type template: L{bytes}
        @param template: A string containing "HOST".

        @rtype: L{bytes}
        @return: A string where "HOST" has been replaced by C{self.host}.
        """
        self.assertIsInstance(self.host, bytes)
        self.assertIsInstance(self.uriHost, bytes)
        self.assertIsInstance(template, bytes)
        self.assertIn(b"HOST", template)
        return template.replace(b"HOST", self.uriHost)

    def assertURIEquals(
        self, uri, scheme, netloc, host, port, path, params=b"", query=b"", fragment=b""
    ):
        """
        Assert that all of a L{client.URI}'s components match the expected
        values.

        @param uri: U{client.URI} instance whose attributes will be checked
            for equality.

        @type scheme: L{bytes}
        @param scheme: URI scheme specifier.

        @type netloc: L{bytes}
        @param netloc: Network location component.

        @type host: L{bytes}
        @param host: Host name.

        @type port: L{int}
        @param port: Port number.

        @type path: L{bytes}
        @param path: Hierarchical path.

        @type params: L{bytes}
        @param params: Parameters for last path segment, defaults to C{b''}.

        @type query: L{bytes}
        @param query: Query string, defaults to C{b''}.

        @type fragment: L{bytes}
        @param fragment: Fragment identifier, defaults to C{b''}.
        """
        self.assertEqual(
            (scheme, netloc, host, port, path, params, query, fragment),
            (
                uri.scheme,
                uri.netloc,
                uri.host,
                uri.port,
                uri.path,
                uri.params,
                uri.query,
                uri.fragment,
            ),
        )

    def test_parseDefaultPort(self):
        """
        L{client.URI.fromBytes} by default assumes port 80 for the I{http}
        scheme and 443 for the I{https} scheme.
        """
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST"))
        self.assertEqual(80, uri.port)
        # Weird (but commonly accepted) structure uses default port.
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST:"))
        self.assertEqual(80, uri.port)
        uri = client.URI.fromBytes(self.makeURIString(b"https://HOST"))
        self.assertEqual(443, uri.port)

    def test_parseCustomDefaultPort(self):
        """
        L{client.URI.fromBytes} accepts a C{defaultPort} parameter that
        overrides the normal default port logic.
        """
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST"), defaultPort=5144)
        self.assertEqual(5144, uri.port)
        uri = client.URI.fromBytes(
            self.makeURIString(b"https://HOST"), defaultPort=5144
        )
        self.assertEqual(5144, uri.port)

    def test_netlocHostPort(self):
        """
        Parsing a I{URI} splits the network location component into I{host} and
        I{port}.
        """
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST:5144"))
        self.assertEqual(5144, uri.port)
        self.assertEqual(self.host, uri.host)
        self.assertEqual(self.uriHost + b":5144", uri.netloc)

        # Spaces in the hostname are trimmed, the default path is /.
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST "))
        self.assertEqual(self.uriHost, uri.netloc)

    def test_path(self):
        """
        Parse the path from a I{URI}.
        """
        uri = self.makeURIString(b"http://HOST/foo/bar")
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b"http",
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b"/foo/bar",
        )
        self.assertEqual(uri, parsed.toBytes())

    def test_noPath(self):
        """
        The path of a I{URI} that has no path is the empty string.
        """
        uri = self.makeURIString(b"http://HOST")
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b"http",
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b"",
        )
        self.assertEqual(uri, parsed.toBytes())

    def test_emptyPath(self):
        """
        The path of a I{URI} with an empty path is C{b'/'}.
        """
        uri = self.makeURIString(b"http://HOST/")
        self.assertURIEquals(
            client.URI.fromBytes(uri),
            scheme=b"http",
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b"/",
        )

    def test_param(self):
        """
        Parse I{URI} parameters from a I{URI}.
        """
        uri = self.makeURIString(b"http://HOST/foo/bar;param")
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b"http",
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b"/foo/bar",
            params=b"param",
        )
        self.assertEqual(uri, parsed.toBytes())

    def test_query(self):
        """
        Parse the query string from a I{URI}.
        """
        uri = self.makeURIString(b"http://HOST/foo/bar;param?a=1&b=2")
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b"http",
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b"/foo/bar",
            params=b"param",
            query=b"a=1&b=2",
        )
        self.assertEqual(uri, parsed.toBytes())

    def test_fragment(self):
        """
        Parse the fragment identifier from a I{URI}.
        """
        uri = self.makeURIString(b"http://HOST/foo/bar;param?a=1&b=2#frag")
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b"http",
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b"/foo/bar",
            params=b"param",
            query=b"a=1&b=2",
            fragment=b"frag",
        )
        self.assertEqual(uri, parsed.toBytes())

    def test_originForm(self):
        """
        L{client.URI.originForm} produces an absolute I{URI} path including
        the I{URI} path.
        """
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST/foo"))
        self.assertEqual(b"/foo", uri.originForm)

    def test_originFormComplex(self):
        """
        L{client.URI.originForm} produces an absolute I{URI} path including
        the I{URI} path, parameters and query string but excludes the fragment
        identifier.
        """
        uri = client.URI.fromBytes(
            self.makeURIString(b"http://HOST/foo;param?a=1#frag")
        )
        self.assertEqual(b"/foo;param?a=1", uri.originForm)

    def test_originFormNoPath(self):
        """
        L{client.URI.originForm} produces a path of C{b'/'} when the I{URI}
        specifies no path.
        """
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST"))
        self.assertEqual(b"/", uri.originForm)

    def test_originFormEmptyPath(self):
        """
        L{client.URI.originForm} produces a path of C{b'/'} when the I{URI}
        specifies an empty path.
        """
        uri = client.URI.fromBytes(self.makeURIString(b"http://HOST/"))
        self.assertEqual(b"/", uri.originForm)

    def test_externalUnicodeInterference(self):
        """
        L{client.URI.fromBytes} parses the scheme, host, and path elements
        into L{bytes}, even when passed an URL which has previously been passed
        to L{urlparse} as a L{unicode} string.
        """
        goodInput = self.makeURIString(b"http://HOST/path")
        badInput = goodInput.decode("ascii")
        urlparse(badInput)
        uri = client.URI.fromBytes(goodInput)
        self.assertIsInstance(uri.scheme, bytes)
        self.assertIsInstance(uri.host, bytes)
        self.assertIsInstance(uri.path, bytes)


class URITestsForHostname(URITests, unittest.TestCase):
    """
    Tests for L{twisted.web.client.URI} with host names.
    """

    uriHost = host = b"example.com"


class URITestsForIPv4(URITests, unittest.TestCase):
    """
    Tests for L{twisted.web.client.URI} with IPv4 host addresses.
    """

    uriHost = host = b"192.168.1.67"


class URITestsForIPv6(URITests, unittest.TestCase):
    """
    Tests for L{twisted.web.client.URI} with IPv6 host addresses.

    IPv6 addresses must always be surrounded by square braces in URIs. No
    attempt is made to test without.
    """

    host = b"fe80::20c:29ff:fea4:c60"
    uriHost = b"[fe80::20c:29ff:fea4:c60]"

    def test_hostBracketIPv6AddressLiteral(self):
        """
        Brackets around IPv6 addresses are stripped in the host field. The host
        field is then exported with brackets in the output of
        L{client.URI.toBytes}.
        """
        uri = client.URI.fromBytes(b"http://[::1]:80/index.html")

        self.assertEqual(uri.host, b"::1")
        self.assertEqual(uri.netloc, b"[::1]:80")
        self.assertEqual(uri.toBytes(), b"http://[::1]:80/index.html")
