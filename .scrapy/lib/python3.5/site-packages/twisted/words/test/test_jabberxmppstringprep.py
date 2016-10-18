# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.trial import unittest

from twisted.words.protocols.jabber.xmpp_stringprep import (
    nodeprep, resourceprep, nameprep)



class DeprecationTests(unittest.TestCase):
    """
    Deprecations in L{twisted.words.protocols.jabber.xmpp_stringprep}.
    """
    def test_crippled(self):
        """
        L{xmpp_stringprep.crippled} is deprecated and always returns C{False}.
        """
        from twisted.words.protocols.jabber.xmpp_stringprep import crippled
        warnings = self.flushWarnings(
            offendingFunctions=[self.test_crippled])
        self.assertEqual(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(
            "twisted.words.protocols.jabber.xmpp_stringprep.crippled was "
            "deprecated in Twisted 13.1.0: crippled is always False",
            warnings[0]['message'])
        self.assertEqual(1, len(warnings))
        self.assertEqual(crippled, False)



class XMPPStringPrepTests(unittest.TestCase):
    """
    The nodeprep stringprep profile is similar to the resourceprep profile,
    but does an extra mapping of characters (table B.2) and disallows
    more characters (table C.1.1 and eight extra punctuation characters).
    Due to this similarity, the resourceprep tests are more extensive, and
    the nodeprep tests only address the mappings additional restrictions.

    The nameprep profile is nearly identical to the nameprep implementation in
    L{encodings.idna}, but that implementation assumes the C{UseSTD4ASCIIRules}
    flag to be false. This implementation assumes it to be true, and restricts
    the allowed set of characters.  The tests here only check for the
    differences.
    """

    def testResourcePrep(self):
        self.assertEqual(resourceprep.prepare(u'resource'), u'resource')
        self.assertNotEqual(resourceprep.prepare(u'Resource'), u'resource')
        self.assertEqual(resourceprep.prepare(u' '), u' ')

        self.assertEqual(resourceprep.prepare(u'Henry \u2163'), u'Henry IV')
        self.assertEqual(resourceprep.prepare(u'foo\xad\u034f\u1806\u180b'
                                               u'bar\u200b\u2060'
                                               u'baz\ufe00\ufe08\ufe0f\ufeff'),
                          u'foobarbaz')
        self.assertEqual(resourceprep.prepare(u'\u00a0'), u' ')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u1680')
        self.assertEqual(resourceprep.prepare(u'\u2000'), u' ')
        self.assertEqual(resourceprep.prepare(u'\u200b'), u'')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u0010\u007f')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u0085')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u180e')
        self.assertEqual(resourceprep.prepare(u'\ufeff'), u'')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\uf123')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\U000f1234')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\U0010f234')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\U0008fffe')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\U0010ffff')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\udf42')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\ufffd')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u2ff5')
        self.assertEqual(resourceprep.prepare(u'\u0341'), u'\u0301')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u200e')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u202a')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\U000e0001')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\U000e0042')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'foo\u05bebar')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'foo\ufd50bar')
        #self.assertEqual(resourceprep.prepare(u'foo\ufb38bar'),
        #                  u'foo\u064ebar')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\u06271')
        self.assertEqual(resourceprep.prepare(u'\u06271\u0628'),
                          u'\u06271\u0628')
        self.assertRaises(UnicodeError, resourceprep.prepare, u'\U000e0002')


    def testNodePrep(self):
        self.assertEqual(nodeprep.prepare(u'user'), u'user')
        self.assertEqual(nodeprep.prepare(u'User'), u'user')
        self.assertRaises(UnicodeError, nodeprep.prepare, u'us&er')


    def test_nodeprepUnassignedInUnicode32(self):
        """
        Make sure unassigned code points from Unicode 3.2 are rejected.
        """
        self.assertRaises(UnicodeError, nodeprep.prepare, u'\u1d39')


    def testNamePrep(self):
        self.assertEqual(nameprep.prepare(u'example.com'), u'example.com')
        self.assertEqual(nameprep.prepare(u'Example.com'), u'example.com')
        self.assertRaises(UnicodeError, nameprep.prepare, u'ex@mple.com')
        self.assertRaises(UnicodeError, nameprep.prepare, u'-example.com')
        self.assertRaises(UnicodeError, nameprep.prepare, u'example-.com')

        self.assertEqual(nameprep.prepare(u'stra\u00dfe.example.com'),
                          u'strasse.example.com')

    def test_nameprepTrailingDot(self):
        """
        A trailing dot in domain names is preserved.
        """
        self.assertEqual(nameprep.prepare(u'example.com.'), u'example.com.')
