# -*- test-case-name: twisted.python.test.test_url -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.url}.
"""

from __future__ import unicode_literals

from ..url import URL
unicode = type(u'')
from unittest import TestCase

theurl = "http://www.foo.com/a/nice/path/?zot=23&zut"

# Examples from RFC 3986 section 5.4, Reference Resolution Examples
relativeLinkBaseForRFC3986 = 'http://a/b/c/d;p?q'
relativeLinkTestsForRFC3986 = [
    # "Normal"
    #('g:h', 'g:h'),     # Not supported:  scheme with relative path
    ('g', 'http://a/b/c/g'),
    ('./g', 'http://a/b/c/g'),
    ('g/', 'http://a/b/c/g/'),
    ('/g', 'http://a/g'),
    ('//g', 'http://g'),
    ('?y', 'http://a/b/c/d;p?y'),
    ('g?y', 'http://a/b/c/g?y'),
    ('#s', 'http://a/b/c/d;p?q#s'),
    ('g#s', 'http://a/b/c/g#s'),
    ('g?y#s', 'http://a/b/c/g?y#s'),
    (';x', 'http://a/b/c/;x'),
    ('g;x', 'http://a/b/c/g;x'),
    ('g;x?y#s', 'http://a/b/c/g;x?y#s'),
    ('', 'http://a/b/c/d;p?q'),
    ('.', 'http://a/b/c/'),
    ('./', 'http://a/b/c/'),
    ('..', 'http://a/b/'),
    ('../', 'http://a/b/'),
    ('../g', 'http://a/b/g'),
    ('../..', 'http://a/'),
    ('../../', 'http://a/'),
    ('../../g', 'http://a/g'),

    # Abnormal examples
    # ".." cannot be used to change the authority component of a URI.
    ('../../../g', 'http://a/g'),
    ('../../../../g', 'http://a/g'),

    # Only include "." and ".." when they are only part of a larger segment,
    # not by themselves.
    ('/./g', 'http://a/g'),
    ('/../g', 'http://a/g'),
    ('g.', 'http://a/b/c/g.'),
    ('.g', 'http://a/b/c/.g'),
    ('g..', 'http://a/b/c/g..'),
    ('..g', 'http://a/b/c/..g'),
    # Unnecessary or nonsensical forms of "." and "..".
    ('./../g', 'http://a/b/g'),
    ('./g/.', 'http://a/b/c/g/'),
    ('g/./h', 'http://a/b/c/g/h'),
    ('g/../h', 'http://a/b/c/h'),
    ('g;x=1/./y', 'http://a/b/c/g;x=1/y'),
    ('g;x=1/../y', 'http://a/b/c/y'),
    # Separating the reference's query and fragment components from the path.
    ('g?y/./x', 'http://a/b/c/g?y/./x'),
    ('g?y/../x', 'http://a/b/c/g?y/../x'),
    ('g#s/./x', 'http://a/b/c/g#s/./x'),
    ('g#s/../x', 'http://a/b/c/g#s/../x'),

    # Not supported:  scheme with relative path
    #("http:g", "http:g"),              # strict
    #("http:g", "http://a/b/c/g"),      # non-strict
]


_percentenc = lambda s: ''.join('%%%02X' % ord(c) for c in s)

class TestURL(TestCase):
    """
    Tests for L{URL}.
    """

    def assertUnicoded(self, u):
        """
        The given L{URL}'s components should be L{unicode}.

        @param u: The L{URL} to test.
        """
        self.assertTrue(isinstance(u.scheme, unicode)
                        or u.scheme is None, repr(u))
        self.assertTrue(isinstance(u.host, unicode)
                        or u.host is None, repr(u))
        for seg in u.path:
            self.assertIsInstance(seg, unicode, repr(u))
        for (k, v) in u.query:
            self.assertIsInstance(k, unicode, repr(u))
            self.assertTrue(v is None or isinstance(v, unicode), repr(u))
        self.assertIsInstance(u.fragment, unicode, repr(u))


    def assertURL(self, u, scheme, host, path, query,
                  fragment, port, userinfo=u''):
        """
        The given L{URL} should have the given components.

        @param u: The actual L{URL} to examine.

        @param scheme: The expected scheme.

        @param host: The expected host.

        @param path: The expected path.

        @param query: The expected query.

        @param fragment: The expected fragment.

        @param port: The expected port.

        @param userinfo: The expected userinfo.
        """
        actual = (u.scheme, u.host, u.path, u.query,
                  u.fragment, u.port, u.userinfo)
        expected = (scheme, host, tuple(path), tuple(query),
                    fragment, port, u.userinfo)
        self.assertEqual(actual, expected)


    def test_initDefaults(self):
        """
        L{URL} should have appropriate default values.
        """
        def check(u):
            self.assertUnicoded(u)
            self.assertURL(u, u'http', u'', [], [], u'', 80, u'')

        check(URL(u'http', u''))
        check(URL(u'http', u'', [], []))
        check(URL(u'http', u'', [], [], u''))


    def test_init(self):
        """
        L{URL} should accept L{unicode} parameters.
        """
        u = URL(u's', u'h', [u'p'], [(u'k', u'v'), (u'k', None)], u'f')
        self.assertUnicoded(u)
        self.assertURL(u, u's', u'h', [u'p'], [(u'k', u'v'), (u'k', None)],
                       u'f', None)

        self.assertURL(URL(u'http', u'\xe0', [u'\xe9'],
                           [(u'\u03bb', u'\u03c0')], u'\u22a5'),
                       u'http', u'\xe0', [u'\xe9'],
                       [(u'\u03bb', u'\u03c0')], u'\u22a5', 80)


    def test_initPercent(self):
        """
        L{URL} should accept (and not interpret) percent characters.
        """
        u = URL(u's', u'%68', [u'%70'], [(u'%6B', u'%76'), (u'%6B', None)],
                u'%66')
        self.assertUnicoded(u)
        self.assertURL(u,
                       u's', u'%68', [u'%70'],
                       [(u'%6B', u'%76'), (u'%6B', None)],
                       u'%66', None)


    def test_repr(self):
        """
        L{URL.__repr__} will display the canoncial form of the URL, wrapped in
        a L{URL.fromText} invocation, so that it is C{eval}-able but still easy
        to read.
        """
        self.assertEqual(
            repr(URL(scheme=u'http', host=u'foo', path=[u'bar'],
                     query=[(u'baz', None), (u'k', u'v')],
                     fragment=u'frob')),
            "URL.fromText(%s)" % (repr(u"http://foo/bar?baz&k=v#frob"),)
        )


    def test_fromText(self):
        """
        Round-tripping L{URL.fromText} with C{str} results in an equivalent
        URL.
        """
        urlpath = URL.fromText(theurl)
        self.assertEqual(theurl, urlpath.asText())


    def test_roundtrip(self):
        """
        L{URL.asText} should invert L{URL.fromText}.
        """
        tests = (
            "http://localhost",
            "http://localhost/",
            "http://localhost/foo",
            "http://localhost/foo/",
            "http://localhost/foo!!bar/",
            "http://localhost/foo%20bar/",
            "http://localhost/foo%2Fbar/",
            "http://localhost/foo?n",
            "http://localhost/foo?n=v",
            "http://localhost/foo?n=/a/b",
            "http://example.com/foo!@$bar?b!@z=123",
            "http://localhost/asd?a=asd%20sdf/345",
            "http://(%2525)/(%2525)?(%2525)&(%2525)=(%2525)#(%2525)",
            "http://(%C3%A9)/(%C3%A9)?(%C3%A9)&(%C3%A9)=(%C3%A9)#(%C3%A9)",
            )
        for test in tests:
            result = URL.fromText(test).asText()
            self.assertEqual(test, result)


    def test_equality(self):
        """
        Two URLs decoded using L{URL.fromText} will be equal (C{==}) if they
        decoded same URL string, and unequal (C{!=}) if they decoded different
        strings.
        """
        urlpath = URL.fromText(theurl)
        self.assertEqual(urlpath, URL.fromText(theurl))
        self.assertNotEqual(
            urlpath,
            URL.fromText('ftp://www.anotherinvaliddomain.com/'
                         'foo/bar/baz/?zot=21&zut')
        )


    def test_fragmentEquality(self):
        """
        An URL created with the empty string for a fragment compares equal
        to an URL created with an unspecified fragment.
        """
        self.assertEqual(URL(fragment=u''), URL())
        self.assertEqual(URL.fromText(u"http://localhost/#"),
                         URL.fromText(u"http://localhost/"))


    def test_child(self):
        """
        L{URL.child} appends a new path segment, but does not affect the query
        or fragment.
        """
        urlpath = URL.fromText(theurl)
        self.assertEqual("http://www.foo.com/a/nice/path/gong?zot=23&zut",
                          urlpath.child(u'gong').asText())
        self.assertEqual("http://www.foo.com/a/nice/path/gong%2F?zot=23&zut",
                          urlpath.child(u'gong/').asText())
        self.assertEqual(
            "http://www.foo.com/a/nice/path/gong%2Fdouble?zot=23&zut",
            urlpath.child(u'gong/double').asText()
        )
        self.assertEqual(
            "http://www.foo.com/a/nice/path/gong%2Fdouble%2F?zot=23&zut",
            urlpath.child(u'gong/double/').asText()
        )


    def test_multiChild(self):
        """
        L{URL.child} receives multiple segments as C{*args} and appends each in
        turn.
        """
        self.assertEqual(URL.fromText('http://example.com/a/b')
                         .child('c', 'd', 'e').asText(),
                         'http://example.com/a/b/c/d/e')


    def test_childInitRoot(self):
        """
        L{URL.child} of a L{URL} without a path produces a L{URL} with a single
        path segment.
        """
        childURL = URL(host=u"www.foo.com").child(u"c")
        self.assertTrue(childURL.rooted)
        self.assertEqual("http://www.foo.com/c", childURL.asText())


    def test_sibling(self):
        """
        L{URL.sibling} of a L{URL} replaces the last path segment, but does not
        affect the query or fragment.
        """
        urlpath = URL.fromText(theurl)
        self.assertEqual(
            "http://www.foo.com/a/nice/path/sister?zot=23&zut",
            urlpath.sibling(u'sister').asText()
        )
        # Use an url without trailing '/' to check child removal.
        theurl2 = "http://www.foo.com/a/nice/path?zot=23&zut"
        urlpath = URL.fromText(theurl2)
        self.assertEqual(
            "http://www.foo.com/a/nice/sister?zot=23&zut",
            urlpath.sibling(u'sister').asText()
        )


    def test_click(self):
        """
        L{URL.click} interprets the given string as a relative URI-reference
        and returns a new L{URL} interpreting C{self} as the base absolute URI.
        """
        urlpath = URL.fromText(theurl)
        # A null uri should be valid (return here).
        self.assertEqual("http://www.foo.com/a/nice/path/?zot=23&zut",
                          urlpath.click("").asText())
        # A simple relative path remove the query.
        self.assertEqual("http://www.foo.com/a/nice/path/click",
                          urlpath.click("click").asText())
        # An absolute path replace path and query.
        self.assertEqual("http://www.foo.com/click",
                          urlpath.click("/click").asText())
        # Replace just the query.
        self.assertEqual("http://www.foo.com/a/nice/path/?burp",
                          urlpath.click("?burp").asText())
        # One full url to another should not generate '//' between authority.
        # and path
        self.assertNotIn("//foobar",
                         urlpath.click('http://www.foo.com/foobar').asText())

        # From a url with no query clicking a url with a query, the query
        # should be handled properly.
        u = URL.fromText('http://www.foo.com/me/noquery')
        self.assertEqual('http://www.foo.com/me/17?spam=158',
                         u.click('/me/17?spam=158').asText())

        # Check that everything from the path onward is removed when the click
        # link has no path.
        u = URL.fromText('http://localhost/foo?abc=def')
        self.assertEqual(u.click('http://www.python.org').asText(),
                         'http://www.python.org')


    def test_clickRFC3986(self):
        """
        L{URL.click} should correctly resolve the examples in RFC 3986.
        """
        base = URL.fromText(relativeLinkBaseForRFC3986)
        for (ref, expected) in relativeLinkTestsForRFC3986:
            self.assertEqual(base.click(ref).asText(), expected)


    def test_clickSchemeRelPath(self):
        """
        L{URL.click} should not accept schemes with relative paths.
        """
        base = URL.fromText(relativeLinkBaseForRFC3986)
        self.assertRaises(NotImplementedError, base.click, 'g:h')
        self.assertRaises(NotImplementedError, base.click, 'http:h')


    def test_cloneUnchanged(self):
        """
        Verify that L{URL.replace} doesn't change any of the arguments it
        is passed.
        """
        urlpath = URL.fromText('https://x:1/y?z=1#A')
        self.assertEqual(
            urlpath.replace(urlpath.scheme,
                            urlpath.host,
                            urlpath.path,
                            urlpath.query,
                            urlpath.fragment,
                            urlpath.port),
            urlpath)
        self.assertEqual(
            urlpath.replace(),
            urlpath)


    def test_clickCollapse(self):
        """
        L{URL.click} collapses C{.} and C{..} according to RFC 3986 section
        5.2.4.
        """
        tests = [
            ['http://localhost/', '.', 'http://localhost/'],
            ['http://localhost/', '..', 'http://localhost/'],
            ['http://localhost/a/b/c', '.', 'http://localhost/a/b/'],
            ['http://localhost/a/b/c', '..', 'http://localhost/a/'],
            ['http://localhost/a/b/c', './d/e', 'http://localhost/a/b/d/e'],
            ['http://localhost/a/b/c', '../d/e', 'http://localhost/a/d/e'],
            ['http://localhost/a/b/c', '/./d/e', 'http://localhost/d/e'],
            ['http://localhost/a/b/c', '/../d/e', 'http://localhost/d/e'],
            ['http://localhost/a/b/c/', '../../d/e/',
             'http://localhost/a/d/e/'],
            ['http://localhost/a/./c', '../d/e', 'http://localhost/d/e'],
            ['http://localhost/a/./c/', '../d/e', 'http://localhost/a/d/e'],
            ['http://localhost/a/b/c/d', './e/../f/../g',
             'http://localhost/a/b/c/g'],
            ['http://localhost/a/b/c', 'd//e', 'http://localhost/a/b/d//e'],
        ]
        for start, click, expected in tests:
            actual = URL.fromText(start).click(click).asText()
            self.assertEqual(
                actual,
                expected,
                "{start}.click({click}) => {actual} not {expected}".format(
                    start=start,
                    click=repr(click),
                    actual=actual,
                    expected=expected,
                )
            )


    def test_queryAdd(self):
        """
        L{URL.add} adds query parameters.
        """
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?foo=bar",
            URL.fromText("http://www.foo.com/a/nice/path/")
            .add(u"foo", u"bar").asText())
        self.assertEqual(
            "http://www.foo.com/?foo=bar",
            URL(host=u"www.foo.com").add(u"foo", u"bar")
            .asText())
        urlpath = URL.fromText(theurl)
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot=23&zut&burp",
            urlpath.add(u"burp").asText())
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot=23&zut&burp=xxx",
            urlpath.add(u"burp", u"xxx").asText())
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot=23&zut&burp=xxx&zing",
            urlpath.add(u"burp", u"xxx").add(u"zing").asText())
        # Note the inversion!
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot=23&zut&zing&burp=xxx",
            urlpath.add(u"zing").add(u"burp", u"xxx").asText())
        # Note the two values for the same name.
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot=23&zut&burp=xxx&zot=32",
            urlpath.add(u"burp", u"xxx").add(u"zot", u'32')
            .asText())


    def test_querySet(self):
        """
        L{URL.set} replaces query parameters by name.
        """
        urlpath = URL.fromText(theurl)
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot=32&zut",
            urlpath.set(u"zot", u'32').asText())
        # Replace name without value with name/value and vice-versa.
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot&zut=itworked",
            urlpath.set(u"zot").set(u"zut", u"itworked").asText()
        )
        # Q: what happens when the query has two values and we replace?
        # A: we replace both values with a single one
        self.assertEqual(
            "http://www.foo.com/a/nice/path/?zot=32&zut",
            urlpath.add(u"zot", u"xxx").set(u"zot", u'32').asText()
        )


    def test_queryRemove(self):
        """
        L{URL.remove} removes all instances of a query parameter.
        """
        url = URL.fromText(u"https://example.com/a/b/?foo=1&bar=2&foo=3")
        self.assertEqual(
            url.remove(u"foo"),
            URL.fromText(u"https://example.com/a/b/?bar=2")
        )


    def test_parseEqualSignInParamValue(self):
        """
        Every C{=}-sign after the first in a query parameter is simply included
        in the value of the parameter.
        """
        u = URL.fromText('http://localhost/?=x=x=x')
        self.assertEqual(u.get(u''), ['x=x=x'])
        self.assertEqual(u.asText(), 'http://localhost/?=x%3Dx%3Dx')
        u = URL.fromText('http://localhost/?foo=x=x=x&bar=y')
        self.assertEqual(u.query, (('foo', 'x=x=x'),
                                             ('bar', 'y')))
        self.assertEqual(u.asText(), 'http://localhost/?foo=x%3Dx%3Dx&bar=y')


    def test_empty(self):
        """
        An empty L{URL} should serialize as the empty string.
        """
        self.assertEqual(URL().asText(), u'')


    def test_justQueryText(self):
        """
        An L{URL} with query text should serialize as just query text.
        """
        u = URL(query=[(u"hello", u"world")])
        self.assertEqual(u.asText(), u'?hello=world')


    def test_identicalEqual(self):
        """
        L{URL} compares equal to itself.
        """
        u = URL.fromText('http://localhost/')
        self.assertEqual(u, u)


    def test_similarEqual(self):
        """
        URLs with equivalent components should compare equal.
        """
        u1 = URL.fromText('http://localhost/')
        u2 = URL.fromText('http://localhost/')
        self.assertEqual(u1, u2)


    def test_differentNotEqual(self):
        """
        L{URL}s that refer to different resources are both unequal (C{!=}) and
        also not equal (not C{==}).
        """
        u1 = URL.fromText('http://localhost/a')
        u2 = URL.fromText('http://localhost/b')
        self.assertFalse(u1 == u2, "%r != %r" % (u1, u2))
        self.assertNotEqual(u1, u2)


    def test_otherTypesNotEqual(self):
        """
        L{URL} is not equal (C{==}) to other types.
        """
        u = URL.fromText('http://localhost/')
        self.assertFalse(u == 42, "URL must not equal a number.")
        self.assertFalse(u == object(), "URL must not equal an object.")
        self.assertNotEqual(u, 42)
        self.assertNotEqual(u, object())


    def test_identicalNotUnequal(self):
        """
        Identical L{URL}s are not unequal (C{!=}) to each other.
        """
        u = URL.fromText('http://localhost/')
        self.assertFalse(u != u, "%r == itself" % u)


    def test_similarNotUnequal(self):
        """
        Structurally similar L{URL}s are not unequal (C{!=}) to each other.
        """
        u1 = URL.fromText('http://localhost/')
        u2 = URL.fromText('http://localhost/')
        self.assertFalse(u1 != u2, "%r == %r" % (u1, u2))


    def test_differentUnequal(self):
        """
        Structurally different L{URL}s are unequal (C{!=}) to each other.
        """
        u1 = URL.fromText('http://localhost/a')
        u2 = URL.fromText('http://localhost/b')
        self.assertTrue(u1 != u2, "%r == %r" % (u1, u2))


    def test_otherTypesUnequal(self):
        """
        L{URL} is unequal (C{!=}) to other types.
        """
        u = URL.fromText('http://localhost/')
        self.assertTrue(u != 42, "URL must differ from a number.")
        self.assertTrue(u != object(), "URL must be differ from an object.")


    def test_asURI(self):
        """
        L{URL.asURI} produces an URI which converts any URI unicode encoding
        into pure US-ASCII and returns a new L{URL}.
        """
        unicodey = ('http://\N{LATIN SMALL LETTER E WITH ACUTE}.com/'
                    '\N{LATIN SMALL LETTER E}\N{COMBINING ACUTE ACCENT}'
                    '?\N{LATIN SMALL LETTER A}\N{COMBINING ACUTE ACCENT}='
                    '\N{LATIN SMALL LETTER I}\N{COMBINING ACUTE ACCENT}'
                    '#\N{LATIN SMALL LETTER U}\N{COMBINING ACUTE ACCENT}')
        iri = URL.fromText(unicodey)
        uri = iri.asURI()
        self.assertEqual(iri.host, '\N{LATIN SMALL LETTER E WITH ACUTE}.com')
        self.assertEqual(iri.path[0],
                         '\N{LATIN SMALL LETTER E}\N{COMBINING ACUTE ACCENT}')
        self.assertEqual(iri.asText(), unicodey)
        expectedURI = 'http://xn--9ca.com/%C3%A9?%C3%A1=%C3%AD#%C3%BA'
        actualURI = uri.asText()
        self.assertEqual(actualURI, expectedURI,
                         '%r != %r' % (actualURI, expectedURI))


    def test_asIRI(self):
        """
        L{URL.asIRI} decodes any percent-encoded text in the URI, making it
        more suitable for reading by humans, and returns a new L{URL}.
        """
        asciiish = 'http://xn--9ca.com/%C3%A9?%C3%A1=%C3%AD#%C3%BA'
        uri = URL.fromText(asciiish)
        iri = uri.asIRI()
        self.assertEqual(uri.host, 'xn--9ca.com')
        self.assertEqual(uri.path[0], '%C3%A9')
        self.assertEqual(uri.asText(), asciiish)
        expectedIRI = ('http://\N{LATIN SMALL LETTER E WITH ACUTE}.com/'
                       '\N{LATIN SMALL LETTER E WITH ACUTE}'
                       '?\N{LATIN SMALL LETTER A WITH ACUTE}='
                       '\N{LATIN SMALL LETTER I WITH ACUTE}'
                       '#\N{LATIN SMALL LETTER U WITH ACUTE}')
        actualIRI = iri.asText()
        self.assertEqual(actualIRI, expectedIRI,
                         '%r != %r' % (actualIRI, expectedIRI))


    def test_badUTF8AsIRI(self):
        """
        Bad UTF-8 in a path segment, query parameter, or fragment results in
        that portion of the URI remaining percent-encoded in the IRI.
        """
        urlWithBinary = 'http://xn--9ca.com/%00%FF/%C3%A9'
        uri = URL.fromText(urlWithBinary)
        iri = uri.asIRI()
        expectedIRI = ('http://\N{LATIN SMALL LETTER E WITH ACUTE}.com/'
                       '%00%FF/'
                       '\N{LATIN SMALL LETTER E WITH ACUTE}')
        actualIRI = iri.asText()
        self.assertEqual(actualIRI, expectedIRI,
                         '%r != %r' % (actualIRI, expectedIRI))


    def test_alreadyIRIAsIRI(self):
        """
        A L{URL} composed of non-ASCII text will result in non-ASCII text.
        """
        unicodey = ('http://\N{LATIN SMALL LETTER E WITH ACUTE}.com/'
                    '\N{LATIN SMALL LETTER E}\N{COMBINING ACUTE ACCENT}'
                    '?\N{LATIN SMALL LETTER A}\N{COMBINING ACUTE ACCENT}='
                    '\N{LATIN SMALL LETTER I}\N{COMBINING ACUTE ACCENT}'
                    '#\N{LATIN SMALL LETTER U}\N{COMBINING ACUTE ACCENT}')
        iri = URL.fromText(unicodey)
        alsoIRI = iri.asIRI()
        self.assertEqual(alsoIRI.asText(), unicodey)


    def test_alreadyURIAsURI(self):
        """
        A L{URL} composed of encoded text will remain encoded.
        """
        expectedURI = 'http://xn--9ca.com/%C3%A9?%C3%A1=%C3%AD#%C3%BA'
        uri = URL.fromText(expectedURI)
        actualURI = uri.asURI().asText()
        self.assertEqual(actualURI, expectedURI)


    def test_userinfo(self):
        """
        L{URL.fromText} will parse the C{userinfo} portion of the URI
        separately from the host and port.
        """
        url = URL.fromText(
            'http://someuser:somepassword@example.com/some-segment@ignore'
        )
        self.assertEqual(url.authority(True),
                         'someuser:somepassword@example.com')
        self.assertEqual(url.authority(False), 'someuser:@example.com')
        self.assertEqual(url.userinfo, 'someuser:somepassword')
        self.assertEqual(url.user, 'someuser')
        self.assertEqual(url.asText(),
                         'http://someuser:@example.com/some-segment@ignore')
        self.assertEqual(
            url.replace(userinfo=u"someuser").asText(),
            'http://someuser@example.com/some-segment@ignore'
        )


    def test_portText(self):
        """
        L{URL.fromText} parses custom port numbers as integers.
        """
        portURL = URL.fromText(u"http://www.example.com:8080/")
        self.assertEqual(portURL.port, 8080)
        self.assertEqual(portURL.asText(), u"http://www.example.com:8080/")


    def test_mailto(self):
        """
        Although L{URL} instances are mainly for dealing with HTTP, other
        schemes (such as C{mailto:}) should work as well.  For example,
        L{URL.fromText}/L{URL.asText} round-trips cleanly for a C{mailto:} URL
        representing an email address.
        """
        self.assertEqual(URL.fromText(u"mailto:user@example.com").asText(),
                         u"mailto:user@example.com")


    def test_queryIterable(self):
        """
        When a L{URL} is created with a C{query} argument, the C{query}
        argument is converted into an N-tuple of 2-tuples.
        """
        url = URL(query=[[u'alpha', u'beta']])
        self.assertEqual(url.query, ((u'alpha', u'beta'),))


    def test_pathIterable(self):
        """
        When a L{URL} is created with a C{path} argument, the C{path} is
        converted into a tuple.
        """
        url = URL(path=[u'hello', u'world'])
        self.assertEqual(url.path, (u'hello', u'world'))


    def test_invalidArguments(self):
        """
        Passing an argument of the wrong type to any of the constructor
        arguments of L{URL} will raise a descriptive L{TypeError}.

        L{URL} typechecks very aggressively to ensure that its constitutent
        parts are all properly immutable and to prevent confusing errors when
        bad data crops up in a method call long after the code that called the
        constructor is off the stack.
        """
        class Unexpected(object):
            def __str__(self):
                return "wrong"
            def __repr__(self):
                return "<unexpected>"
        defaultExpectation = "unicode" if bytes is str else "str"
        def assertRaised(raised, expectation, name):
            self.assertEqual(str(raised.exception),
                             "expected {} for {}, got {}".format(
                                 expectation,
                                 name, "<unexpected>"))

        def check(param, expectation=defaultExpectation):
            with self.assertRaises(TypeError) as raised:
                URL(**{param: Unexpected()})
            assertRaised(raised, expectation, param)
        check("scheme")
        check("host")
        check("fragment")
        check("rooted", "bool")
        check("userinfo")
        check("port", "int or NoneType")

        with self.assertRaises(TypeError) as raised:
            URL(path=[Unexpected(),])
        assertRaised(raised, defaultExpectation, "path segment")
        with self.assertRaises(TypeError) as raised:
            URL(query=[(u"name", Unexpected()),])
        assertRaised(raised, defaultExpectation + " or NoneType",
                     "query parameter value")
        with self.assertRaises(TypeError) as raised:
            URL(query=[(Unexpected(), u"value"),])
        assertRaised(raised, defaultExpectation, "query parameter name")
        # No custom error message for this one, just want to make sure
        # non-2-tuples don't get through.
        with self.assertRaises(TypeError):
            URL(query=[Unexpected()])
        with self.assertRaises(ValueError):
            URL(query=[(u'k', u'v', u'vv')])
        with self.assertRaises(ValueError):
            URL(query=[(u'k',)])

        url = URL.fromText("https://valid.example.com/")
        with self.assertRaises(TypeError) as raised:
            url.child(Unexpected())
        assertRaised(raised, defaultExpectation, "path segment")
        with self.assertRaises(TypeError) as raised:
            url.sibling(Unexpected())
        assertRaised(raised, defaultExpectation, "path segment")
        with self.assertRaises(TypeError) as raised:
            url.click(Unexpected())
        assertRaised(raised, defaultExpectation, "relative URL")


    def test_technicallyTextIsIterableBut(self):
        """
        Technically, L{str} (or L{unicode}, as appropriate) is iterable, but
        C{URL(path="foo")} resulting in C{URL.fromText("f/o/o")} is never what
        you want.
        """
        with self.assertRaises(TypeError) as raised:
            URL(path=u'foo')
        self.assertEqual(
            str(raised.exception),
            "expected iterable of text for path, got text itself: {}"
            .format(repr(u'foo'))
        )
