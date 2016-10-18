# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.http_headers}.
"""

from __future__ import division, absolute_import

from twisted.trial.unittest import TestCase
from twisted.python.compat import _PY3
from twisted.web.http_headers import Headers

class BytesHeadersTests(TestCase):
    """
    Tests for L{Headers}, using L{bytes} arguments for methods.
    """
    def test_initializer(self):
        """
        The header values passed to L{Headers.__init__} can be retrieved via
        L{Headers.getRawHeaders}.
        """
        h = Headers({b'Foo': [b'bar']})
        self.assertEqual(h.getRawHeaders(b'foo'), [b'bar'])


    def test_setRawHeaders(self):
        """
        L{Headers.setRawHeaders} sets the header values for the given
        header name to the sequence of byte string values.
        """
        rawValue = [b"value1", b"value2"]
        h = Headers()
        h.setRawHeaders(b"test", rawValue)
        self.assertTrue(h.hasHeader(b"test"))
        self.assertTrue(h.hasHeader(b"Test"))
        self.assertEqual(h.getRawHeaders(b"test"), rawValue)


    def test_rawHeadersTypeChecking(self):
        """
        L{Headers.setRawHeaders} requires values to be of type list.
        """
        h = Headers()
        self.assertRaises(TypeError, h.setRawHeaders, b'key', {b'Foo': b'bar'})


    def test_addRawHeader(self):
        """
        L{Headers.addRawHeader} adds a new value for a given header.
        """
        h = Headers()
        h.addRawHeader(b"test", b"lemur")
        self.assertEqual(h.getRawHeaders(b"test"), [b"lemur"])
        h.addRawHeader(b"test", b"panda")
        self.assertEqual(h.getRawHeaders(b"test"), [b"lemur", b"panda"])


    def test_getRawHeadersNoDefault(self):
        """
        L{Headers.getRawHeaders} returns L{None} if the header is not found and
        no default is specified.
        """
        self.assertIsNone(Headers().getRawHeaders(b"test"))


    def test_getRawHeadersDefaultValue(self):
        """
        L{Headers.getRawHeaders} returns the specified default value when no
        header is found.
        """
        h = Headers()
        default = object()
        self.assertIdentical(h.getRawHeaders(b"test", default), default)


    def test_getRawHeaders(self):
        """
        L{Headers.getRawHeaders} returns the values which have been set for a
        given header.
        """
        h = Headers()
        h.setRawHeaders(b"test", [b"lemur"])
        self.assertEqual(h.getRawHeaders(b"test"), [b"lemur"])
        self.assertEqual(h.getRawHeaders(b"Test"), [b"lemur"])


    def test_hasHeaderTrue(self):
        """
        Check that L{Headers.hasHeader} returns C{True} when the given header
        is found.
        """
        h = Headers()
        h.setRawHeaders(b"test", [b"lemur"])
        self.assertTrue(h.hasHeader(b"test"))
        self.assertTrue(h.hasHeader(b"Test"))


    def test_hasHeaderFalse(self):
        """
        L{Headers.hasHeader} returns C{False} when the given header is not
        found.
        """
        self.assertFalse(Headers().hasHeader(b"test"))


    def test_removeHeader(self):
        """
        Check that L{Headers.removeHeader} removes the given header.
        """
        h = Headers()

        h.setRawHeaders(b"foo", [b"lemur"])
        self.assertTrue(h.hasHeader(b"foo"))
        h.removeHeader(b"foo")
        self.assertFalse(h.hasHeader(b"foo"))

        h.setRawHeaders(b"bar", [b"panda"])
        self.assertTrue(h.hasHeader(b"bar"))
        h.removeHeader(b"Bar")
        self.assertFalse(h.hasHeader(b"bar"))


    def test_removeHeaderDoesntExist(self):
        """
        L{Headers.removeHeader} is a no-operation when the specified header is
        not found.
        """
        h = Headers()
        h.removeHeader(b"test")
        self.assertEqual(list(h.getAllRawHeaders()), [])


    def test_canonicalNameCaps(self):
        """
        L{Headers._canonicalNameCaps} returns the canonical capitalization for
        the given header.
        """
        h = Headers()
        self.assertEqual(h._canonicalNameCaps(b"test"), b"Test")
        self.assertEqual(h._canonicalNameCaps(b"test-stuff"), b"Test-Stuff")
        self.assertEqual(h._canonicalNameCaps(b"content-md5"), b"Content-MD5")
        self.assertEqual(h._canonicalNameCaps(b"dnt"), b"DNT")
        self.assertEqual(h._canonicalNameCaps(b"etag"), b"ETag")
        self.assertEqual(h._canonicalNameCaps(b"p3p"), b"P3P")
        self.assertEqual(h._canonicalNameCaps(b"te"), b"TE")
        self.assertEqual(h._canonicalNameCaps(b"www-authenticate"),
                          b"WWW-Authenticate")
        self.assertEqual(h._canonicalNameCaps(b"x-xss-protection"),
                          b"X-XSS-Protection")


    def test_getAllRawHeaders(self):
        """
        L{Headers.getAllRawHeaders} returns an iterable of (k, v) pairs, where
        C{k} is the canonicalized representation of the header name, and C{v}
        is a sequence of values.
        """
        h = Headers()
        h.setRawHeaders(b"test", [b"lemurs"])
        h.setRawHeaders(b"www-authenticate", [b"basic aksljdlk="])

        allHeaders = set([(k, tuple(v)) for k, v in h.getAllRawHeaders()])

        self.assertEqual(allHeaders,
                          set([(b"WWW-Authenticate", (b"basic aksljdlk=",)),
                               (b"Test", (b"lemurs",))]))


    def test_headersComparison(self):
        """
        A L{Headers} instance compares equal to itself and to another
        L{Headers} instance with the same values.
        """
        first = Headers()
        first.setRawHeaders(b"foo", [b"panda"])
        second = Headers()
        second.setRawHeaders(b"foo", [b"panda"])
        third = Headers()
        third.setRawHeaders(b"foo", [b"lemur", b"panda"])
        self.assertEqual(first, first)
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)


    def test_otherComparison(self):
        """
        An instance of L{Headers} does not compare equal to other unrelated
        objects.
        """
        h = Headers()
        self.assertNotEqual(h, ())
        self.assertNotEqual(h, object())
        self.assertNotEqual(h, b"foo")


    def test_repr(self):
        """
        The L{repr} of a L{Headers} instance shows the names and values of all
        the headers it contains.
        """
        foo = b"foo"
        bar = b"bar"
        baz = b"baz"
        self.assertEqual(
            repr(Headers({foo: [bar, baz]})),
            "Headers({%r: [%r, %r]})" % (foo, bar, baz))


    def test_reprWithRawBytes(self):
        """
        The L{repr} of a L{Headers} instance shows the names and values of all
        the headers it contains, not attempting to decode any raw bytes.
        """
        # There's no such thing as undecodable latin-1, you'll just get
        # some mojibake
        foo = b"foo"
        # But this is invalid UTF-8! So, any accidental decoding/encoding will
        # throw an exception.
        bar = b"bar\xe1"
        baz = b"baz\xe1"
        self.assertEqual(
            repr(Headers({foo: [bar, baz]})),
            "Headers({%r: [%r, %r]})" % (foo, bar, baz))


    def test_subclassRepr(self):
        """
        The L{repr} of an instance of a subclass of L{Headers} uses the name
        of the subclass instead of the string C{"Headers"}.
        """
        foo = b"foo"
        bar = b"bar"
        baz = b"baz"
        class FunnyHeaders(Headers):
            pass
        self.assertEqual(
            repr(FunnyHeaders({foo: [bar, baz]})),
            "FunnyHeaders({%r: [%r, %r]})" % (foo, bar, baz))


    def test_copy(self):
        """
        L{Headers.copy} creates a new independent copy of an existing
        L{Headers} instance, allowing future modifications without impacts
        between the copies.
        """
        h = Headers()
        h.setRawHeaders(b'test', [b'foo'])
        i = h.copy()
        self.assertEqual(i.getRawHeaders(b'test'), [b'foo'])
        h.addRawHeader(b'test', b'bar')
        self.assertEqual(i.getRawHeaders(b'test'), [b'foo'])
        i.addRawHeader(b'test', b'baz')
        self.assertEqual(h.getRawHeaders(b'test'), [b'foo', b'bar'])



class UnicodeHeadersTests(TestCase):
    """
    Tests for L{Headers}, using L{unicode} arguments for methods.
    """
    def test_initializer(self):
        """
        The header values passed to L{Headers.__init__} can be retrieved via
        L{Headers.getRawHeaders}. If a L{bytes} argument is given, it returns
        L{bytes} values, and if a L{unicode} argument is given, it returns
        L{unicode} values. Both are the same header value, just encoded or
        decoded.
        """
        h = Headers({u'Foo': [u'bar']})
        self.assertEqual(h.getRawHeaders(b'foo'), [b'bar'])
        self.assertEqual(h.getRawHeaders(u'foo'), [u'bar'])


    def test_setRawHeaders(self):
        """
        L{Headers.setRawHeaders} sets the header values for the given
        header name to the sequence of strings, encoded.
        """
        rawValue = [u"value1", u"value2"]
        rawEncodedValue = [b"value1", b"value2"]
        h = Headers()
        h.setRawHeaders("test", rawValue)
        self.assertTrue(h.hasHeader(b"test"))
        self.assertTrue(h.hasHeader(b"Test"))
        self.assertTrue(h.hasHeader("test"))
        self.assertTrue(h.hasHeader("Test"))
        self.assertEqual(h.getRawHeaders("test"), rawValue)
        self.assertEqual(h.getRawHeaders(b"test"), rawEncodedValue)


    def test_nameNotEncodable(self):
        """
        Passing L{unicode} to any function that takes a header name will encode
        said header name as ISO-8859-1, and if it cannot be encoded, it will
        raise a L{UnicodeDecodeError}.
        """
        h = Headers()

        # Only these two functions take names
        with self.assertRaises(UnicodeEncodeError):
            h.setRawHeaders(u"\u2603", [u"val"])

        with self.assertRaises(UnicodeEncodeError):
            h.hasHeader(u"\u2603")


    def test_nameEncoding(self):
        """
        Passing L{unicode} to any function that takes a header name will encode
        said header name as ISO-8859-1.
        """
        h = Headers()

        # We set it using a Unicode string.
        h.setRawHeaders(u"\u00E1", [b"foo"])

        # It's encoded to the ISO-8859-1 value, which we can use to access it
        self.assertTrue(h.hasHeader(b"\xe1"))
        self.assertEqual(h.getRawHeaders(b"\xe1"), [b'foo'])

        # We can still access it using the Unicode string..
        self.assertTrue(h.hasHeader(u"\u00E1"))


    def test_rawHeadersValueEncoding(self):
        """
        Passing L{unicode} to L{Headers.setRawHeaders} will encode the name as
        ISO-8859-1 and values as UTF-8.
        """
        h = Headers()
        h.setRawHeaders(u"\u00E1", [u"\u2603", b"foo"])
        self.assertTrue(h.hasHeader(b"\xe1"))
        self.assertEqual(h.getRawHeaders(b"\xe1"), [b'\xe2\x98\x83', b'foo'])


    def test_rawHeadersTypeChecking(self):
        """
        L{Headers.setRawHeaders} requires values to be of type list.
        """
        h = Headers()
        self.assertRaises(TypeError, h.setRawHeaders, u'key', {u'Foo': u'bar'})


    def test_addRawHeader(self):
        """
        L{Headers.addRawHeader} adds a new value for a given header.
        """
        h = Headers()
        h.addRawHeader(u"test", u"lemur")
        self.assertEqual(h.getRawHeaders(u"test"), [u"lemur"])
        h.addRawHeader(u"test", u"panda")
        self.assertEqual(h.getRawHeaders(u"test"), [u"lemur", u"panda"])
        self.assertEqual(h.getRawHeaders(b"test"), [b"lemur", b"panda"])


    def test_getRawHeadersNoDefault(self):
        """
        L{Headers.getRawHeaders} returns L{None} if the header is not found and
        no default is specified.
        """
        self.assertIsNone(Headers().getRawHeaders(u"test"))


    def test_getRawHeadersDefaultValue(self):
        """
        L{Headers.getRawHeaders} returns the specified default value when no
        header is found.
        """
        h = Headers()
        default = object()
        self.assertIdentical(h.getRawHeaders(u"test", default), default)


    def test_getRawHeaders(self):
        """
        L{Headers.getRawHeaders} returns the values which have been set for a
        given header.
        """
        h = Headers()
        h.setRawHeaders(u"test\u00E1", [u"lemur"])
        self.assertEqual(h.getRawHeaders(u"test\u00E1"), [u"lemur"])
        self.assertEqual(h.getRawHeaders(u"Test\u00E1"), [u"lemur"])
        self.assertEqual(h.getRawHeaders(b"test\xe1"), [b"lemur"])
        self.assertEqual(h.getRawHeaders(b"Test\xe1"), [b"lemur"])


    def test_hasHeaderTrue(self):
        """
        Check that L{Headers.hasHeader} returns C{True} when the given header
        is found.
        """
        h = Headers()
        h.setRawHeaders(u"test\u00E1", [u"lemur"])
        self.assertTrue(h.hasHeader(u"test\u00E1"))
        self.assertTrue(h.hasHeader(u"Test\u00E1"))
        self.assertTrue(h.hasHeader(b"test\xe1"))
        self.assertTrue(h.hasHeader(b"Test\xe1"))


    def test_hasHeaderFalse(self):
        """
        L{Headers.hasHeader} returns C{False} when the given header is not
        found.
        """
        self.assertFalse(Headers().hasHeader(u"test\u00E1"))


    def test_removeHeader(self):
        """
        Check that L{Headers.removeHeader} removes the given header.
        """
        h = Headers()

        h.setRawHeaders(u"foo", [u"lemur"])
        self.assertTrue(h.hasHeader(u"foo"))
        h.removeHeader(u"foo")
        self.assertFalse(h.hasHeader(u"foo"))
        self.assertFalse(h.hasHeader(b"foo"))

        h.setRawHeaders(u"bar", [u"panda"])
        self.assertTrue(h.hasHeader(u"bar"))
        h.removeHeader(u"Bar")
        self.assertFalse(h.hasHeader(u"bar"))
        self.assertFalse(h.hasHeader(b"bar"))


    def test_removeHeaderDoesntExist(self):
        """
        L{Headers.removeHeader} is a no-operation when the specified header is
        not found.
        """
        h = Headers()
        h.removeHeader(u"test")
        self.assertEqual(list(h.getAllRawHeaders()), [])


    def test_getAllRawHeaders(self):
        """
        L{Headers.getAllRawHeaders} returns an iterable of (k, v) pairs, where
        C{k} is the canonicalized representation of the header name, and C{v}
        is a sequence of values.
        """
        h = Headers()
        h.setRawHeaders(u"test\u00E1", [u"lemurs"])
        h.setRawHeaders(u"www-authenticate", [u"basic aksljdlk="])
        h.setRawHeaders(u"content-md5", [u"kjdfdfgdfgnsd"])

        allHeaders = set([(k, tuple(v)) for k, v in h.getAllRawHeaders()])

        self.assertEqual(allHeaders,
                          set([(b"WWW-Authenticate", (b"basic aksljdlk=",)),
                               (b"Content-MD5", (b"kjdfdfgdfgnsd",)),
                               (b"Test\xe1", (b"lemurs",))]))


    def test_headersComparison(self):
        """
        A L{Headers} instance compares equal to itself and to another
        L{Headers} instance with the same values.
        """
        first = Headers()
        first.setRawHeaders(u"foo\u00E1", [u"panda"])
        second = Headers()
        second.setRawHeaders(u"foo\u00E1", [u"panda"])
        third = Headers()
        third.setRawHeaders(u"foo\u00E1", [u"lemur", u"panda"])

        self.assertEqual(first, first)
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

        # Headers instantiated with bytes equivs are also the same
        firstBytes = Headers()
        firstBytes.setRawHeaders(b"foo\xe1", [b"panda"])
        secondBytes = Headers()
        secondBytes.setRawHeaders(b"foo\xe1", [b"panda"])
        thirdBytes = Headers()
        thirdBytes.setRawHeaders(b"foo\xe1", [b"lemur", u"panda"])

        self.assertEqual(first, firstBytes)
        self.assertEqual(second, secondBytes)
        self.assertEqual(third, thirdBytes)


    def test_otherComparison(self):
        """
        An instance of L{Headers} does not compare equal to other unrelated
        objects.
        """
        h = Headers()
        self.assertNotEqual(h, ())
        self.assertNotEqual(h, object())
        self.assertNotEqual(h, u"foo")


    def test_repr(self):
        """
        The L{repr} of a L{Headers} instance shows the names and values of all
        the headers it contains. This shows only reprs of bytes values, as
        undecodable headers may cause an exception.
        """
        foo = u"foo\u00E1"
        bar = u"bar\u2603"
        baz = u"baz"
        fooEncoded = "'foo\\xe1'"
        barEncoded = "'bar\\xe2\\x98\\x83'"
        if _PY3:
            fooEncoded = "b" + fooEncoded
            barEncoded = "b" + barEncoded
        self.assertEqual(
            repr(Headers({foo: [bar, baz]})),
            "Headers({%s: [%s, %r]})" % (fooEncoded,
                                         barEncoded,
                                         baz.encode('utf8')))


    def test_subclassRepr(self):
        """
        The L{repr} of an instance of a subclass of L{Headers} uses the name
        of the subclass instead of the string C{"Headers"}.
        """
        foo = u"foo\u00E1"
        bar = u"bar\u2603"
        baz = u"baz"
        fooEncoded = "'foo\\xe1'"
        barEncoded = "'bar\\xe2\\x98\\x83'"
        if _PY3:
            fooEncoded = "b" + fooEncoded
            barEncoded = "b" + barEncoded
        class FunnyHeaders(Headers):
            pass
        self.assertEqual(
            repr(FunnyHeaders({foo: [bar, baz]})),
            "FunnyHeaders({%s: [%s, %r]})" % (fooEncoded,
                                              barEncoded,
                                              baz.encode('utf8')))


    def test_copy(self):
        """
        L{Headers.copy} creates a new independent copy of an existing
        L{Headers} instance, allowing future modifications without impacts
        between the copies.
        """
        h = Headers()
        h.setRawHeaders(u'test\u00E1', [u'foo\u2603'])
        i = h.copy()

        # The copy contains the same value as the original
        self.assertEqual(i.getRawHeaders(u'test\u00E1'), [u'foo\u2603'])
        self.assertEqual(i.getRawHeaders(b'test\xe1'), [b'foo\xe2\x98\x83'])

        # Add a header to the original
        h.addRawHeader(u'test\u00E1', u'bar')

        # Verify that the copy has not changed
        self.assertEqual(i.getRawHeaders(u'test\u00E1'), [u'foo\u2603'])
        self.assertEqual(i.getRawHeaders(b'test\xe1'), [b'foo\xe2\x98\x83'])

        # Add a header to the copy
        i.addRawHeader(u'test\u00E1', b'baz')

        # Verify that the orignal does not have it
        self.assertEqual(
            h.getRawHeaders(u'test\u00E1'), [u'foo\u2603', u'bar'])
        self.assertEqual(
            h.getRawHeaders(b'test\xe1'), [b'foo\xe2\x98\x83', b'bar'])
