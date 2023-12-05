# -*- test-case-name: twisted.python.test.test_urlpath -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.urlpath}.
"""

from twisted.python import urlpath
from twisted.trial import unittest


class _BaseURLPathTests:
    """
    Tests for instantiated L{urlpath.URLPath}s.
    """

    def test_partsAreBytes(self):
        """
        All of the attributes of L{urlpath.URLPath} should be L{bytes}.
        """
        self.assertIsInstance(self.path.scheme, bytes)
        self.assertIsInstance(self.path.netloc, bytes)
        self.assertIsInstance(self.path.path, bytes)
        self.assertIsInstance(self.path.query, bytes)
        self.assertIsInstance(self.path.fragment, bytes)

    def test_strReturnsStr(self):
        """
        Calling C{str()} with a L{URLPath} will always return a L{str}.
        """
        self.assertEqual(type(self.path.__str__()), str)

    def test_mutabilityWithText(self, stringType=str):
        """
        Setting attributes on L{urlpath.URLPath} should change the value
        returned by L{str}.

        @param stringType: a callable to parameterize this test for different
            text types.
        @type stringType: 1-argument callable taking L{str} and returning
            L{str} or L{bytes}.
        """
        self.path.scheme = stringType("https")
        self.assertEqual(
            str(self.path), "https://example.com/foo/bar?yes=no&no=yes#footer"
        )
        self.path.netloc = stringType("another.example.invalid")
        self.assertEqual(
            str(self.path),
            "https://another.example.invalid/foo/bar?yes=no&no=yes#footer",
        )
        self.path.path = stringType("/hello")
        self.assertEqual(
            str(self.path), "https://another.example.invalid/hello?yes=no&no=yes#footer"
        )
        self.path.query = stringType("alpha=omega&opposites=same")
        self.assertEqual(
            str(self.path),
            "https://another.example.invalid/hello?alpha=omega&opposites=same"
            "#footer",
        )
        self.path.fragment = stringType("header")
        self.assertEqual(
            str(self.path),
            "https://another.example.invalid/hello?alpha=omega&opposites=same"
            "#header",
        )

    def test_mutabilityWithBytes(self):
        """
        Same as L{test_mutabilityWithText} but for bytes.
        """
        self.test_mutabilityWithText(lambda x: x.encode("ascii"))

    def test_allAttributesAreBytes(self):
        """
        A created L{URLPath} has bytes attributes.
        """
        self.assertIsInstance(self.path.scheme, bytes)
        self.assertIsInstance(self.path.netloc, bytes)
        self.assertIsInstance(self.path.path, bytes)
        self.assertIsInstance(self.path.query, bytes)
        self.assertIsInstance(self.path.fragment, bytes)

    def test_stringConversion(self):
        """
        Calling C{str()} with a L{URLPath} will return the same URL that it was
        constructed with.
        """
        self.assertEqual(
            str(self.path), "http://example.com/foo/bar?yes=no&no=yes#footer"
        )

    def test_childString(self):
        """
        Calling C{str()} with a C{URLPath.child()} will return a URL which is
        the child of the URL it was instantiated with.
        """
        self.assertEqual(
            str(self.path.child(b"hello")), "http://example.com/foo/bar/hello"
        )
        self.assertEqual(
            str(self.path.child(b"hello").child(b"")),
            "http://example.com/foo/bar/hello/",
        )
        self.assertEqual(
            str(self.path.child(b"hello", keepQuery=True)),
            "http://example.com/foo/bar/hello?yes=no&no=yes",
        )

    def test_siblingString(self):
        """
        Calling C{str()} with a C{URLPath.sibling()} will return a URL which is
        the sibling of the URL it was instantiated with.
        """
        self.assertEqual(str(self.path.sibling(b"baz")), "http://example.com/foo/baz")
        self.assertEqual(
            str(self.path.sibling(b"baz", keepQuery=True)),
            "http://example.com/foo/baz?yes=no&no=yes",
        )

        # The sibling of http://example.com/foo/bar/
        #     is http://example.comf/foo/bar/baz
        # because really we are constructing a sibling of
        # http://example.com/foo/bar/index.html
        self.assertEqual(
            str(self.path.child(b"").sibling(b"baz")), "http://example.com/foo/bar/baz"
        )

    def test_parentString(self):
        """
        Calling C{str()} with a C{URLPath.parent()} will return a URL which is
        the parent of the URL it was instantiated with.
        """
        # .parent() should be equivalent to '..'
        # 'foo' is the current directory, '/' is the parent directory
        self.assertEqual(str(self.path.parent()), "http://example.com/")
        self.assertEqual(
            str(self.path.parent(keepQuery=True)), "http://example.com/?yes=no&no=yes"
        )
        self.assertEqual(str(self.path.child(b"").parent()), "http://example.com/foo/")
        self.assertEqual(
            str(self.path.child(b"baz").parent()), "http://example.com/foo/"
        )
        self.assertEqual(
            str(self.path.parent().parent().parent().parent().parent()),
            "http://example.com/",
        )

    def test_hereString(self):
        """
        Calling C{str()} with a C{URLPath.here()} will return a URL which is
        the URL that it was instantiated with, without any file, query, or
        fragment.
        """
        # .here() should be equivalent to '.'
        self.assertEqual(str(self.path.here()), "http://example.com/foo/")
        self.assertEqual(
            str(self.path.here(keepQuery=True)), "http://example.com/foo/?yes=no&no=yes"
        )
        self.assertEqual(
            str(self.path.child(b"").here()), "http://example.com/foo/bar/"
        )

    def test_doubleSlash(self):
        """
        Calling L{urlpath.URLPath.click} on a L{urlpath.URLPath} with a
        trailing slash with a relative URL containing a leading slash will
        result in a URL with a single slash at the start of the path portion.
        """
        self.assertEqual(
            str(self.path.click(b"/hello/world")).encode("ascii"),
            b"http://example.com/hello/world",
        )

    def test_pathList(self):
        """
        L{urlpath.URLPath.pathList} returns a L{list} of L{bytes}.
        """
        self.assertEqual(
            self.path.child(b"%00%01%02").pathList(),
            [b"", b"foo", b"bar", b"%00%01%02"],
        )

        # Just testing that the 'copy' argument exists for compatibility; it
        # was originally provided for performance reasons, and its behavioral
        # contract is kind of nonsense (where is the state shared? who with?)
        # so it doesn't actually *do* anything any more.
        self.assertEqual(
            self.path.child(b"%00%01%02").pathList(copy=False),
            [b"", b"foo", b"bar", b"%00%01%02"],
        )
        self.assertEqual(
            self.path.child(b"%00%01%02").pathList(unquote=True),
            [b"", b"foo", b"bar", b"\x00\x01\x02"],
        )


class BytesURLPathTests(_BaseURLPathTests, unittest.TestCase):
    """
    Tests for interacting with a L{URLPath} created with C{fromBytes}.
    """

    def setUp(self):
        self.path = urlpath.URLPath.fromBytes(
            b"http://example.com/foo/bar?yes=no&no=yes#footer"
        )

    def test_mustBeBytes(self):
        """
        L{URLPath.fromBytes} must take a L{bytes} argument.
        """
        with self.assertRaises(ValueError):
            urlpath.URLPath.fromBytes(None)

        with self.assertRaises(ValueError):
            urlpath.URLPath.fromBytes("someurl")

    def test_withoutArguments(self):
        """
        An instantiation with no arguments creates a usable L{URLPath} with
        default arguments.
        """
        url = urlpath.URLPath()
        self.assertEqual(str(url), "http://localhost/")

    def test_partialArguments(self):
        """
        Leaving some optional arguments unfilled makes a L{URLPath} with those
        optional arguments filled with defaults.
        """
        # Not a "full" URL given to fromBytes, no /
        # / is filled in
        url = urlpath.URLPath.fromBytes(b"http://google.com")
        self.assertEqual(url.scheme, b"http")
        self.assertEqual(url.netloc, b"google.com")
        self.assertEqual(url.path, b"/")
        self.assertEqual(url.fragment, b"")
        self.assertEqual(url.query, b"")
        self.assertEqual(str(url), "http://google.com/")

    def test_nonASCIIBytes(self):
        """
        L{URLPath.fromBytes} can interpret non-ASCII bytes as percent-encoded
        """
        url = urlpath.URLPath.fromBytes(b"http://example.com/\xff\x00")
        self.assertEqual(str(url), "http://example.com/%FF%00")


class StringURLPathTests(_BaseURLPathTests, unittest.TestCase):
    """
    Tests for interacting with a L{URLPath} created with C{fromString} and a
    L{str} argument.
    """

    def setUp(self):
        self.path = urlpath.URLPath.fromString(
            "http://example.com/foo/bar?yes=no&no=yes#footer"
        )

    def test_mustBeStr(self):
        """
        C{URLPath.fromString} must take a L{str} or L{str} argument.
        """
        with self.assertRaises(ValueError):
            urlpath.URLPath.fromString(None)

        with self.assertRaises(ValueError):
            urlpath.URLPath.fromString(b"someurl")


class UnicodeURLPathTests(_BaseURLPathTests, unittest.TestCase):
    """
    Tests for interacting with a L{URLPath} created with C{fromString} and a
    L{str} argument.
    """

    def setUp(self):
        self.path = urlpath.URLPath.fromString(
            "http://example.com/foo/bar?yes=no&no=yes#footer"
        )

    def test_nonASCIICharacters(self):
        """
        L{URLPath.fromString} can load non-ASCII characters.
        """
        url = urlpath.URLPath.fromString("http://example.com/\xff\x00")
        self.assertEqual(str(url), "http://example.com/%C3%BF%00")
