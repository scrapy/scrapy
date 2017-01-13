# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.text}.
"""

from twisted.python.compat import NativeStringIO as StringIO

from twisted.trial import unittest
from twisted.python import text


sampleText = \
"""Every attempt to employ mathematical methods in the study of chemical
questions must be considered profoundly irrational and contrary to the
spirit of chemistry ...  If mathematical analysis should ever hold a
prominent place in chemistry - an aberration which is happily almost
impossible - it would occasion a rapid and widespread degeneration of that
science.

           --  Auguste Comte, Philosophie Positive, Paris, 1838
"""


class WrapTests(unittest.TestCase):
    """
    Tests for L{text.greedyWrap}.
    """
    def setUp(self):
        self.lineWidth = 72
        self.sampleSplitText = sampleText.split()
        self.output = text.wordWrap(sampleText, self.lineWidth)


    def test_wordCount(self):
        """
        Compare the number of words.
        """
        words = []
        for line in self.output:
            words.extend(line.split())
        wordCount = len(words)
        sampleTextWordCount = len(self.sampleSplitText)

        self.assertEqual(wordCount, sampleTextWordCount)


    def test_wordMatch(self):
        """
        Compare the lists of words.
        """
        words = []
        for line in self.output:
            words.extend(line.split())

        # Using assertEqual here prints out some
        # rather too long lists.
        self.assertTrue(self.sampleSplitText == words)


    def test_lineLength(self):
        """
        Check the length of the lines.
        """
        failures = []
        for line in self.output:
            if not len(line) <= self.lineWidth:
                failures.append(len(line))

        if failures:
            self.fail("%d of %d lines were too long.\n"
                      "%d < %s" % (len(failures), len(self.output),
                                   self.lineWidth, failures))

    def test_doubleNewline(self):
        """
        Allow paragraphs delimited by two \ns.
        """
        sampleText = "et\n\nphone\nhome."
        result = text.wordWrap(sampleText, self.lineWidth)
        self.assertEqual(result, ["et", "", "phone home.", ""]) 



class LineTests(unittest.TestCase):
    """
    Tests for L{isMultiline} and L{endsInNewline}.
    """
    def test_isMultiline(self):
        """
        L{text.isMultiline} returns C{True} if the string has a newline in it.
        """
        s = 'This code\n "breaks."'
        m = text.isMultiline(s)
        self.assertTrue(m)

        s = 'This code does not "break."'
        m = text.isMultiline(s)
        self.assertFalse(m)


    def test_endsInNewline(self):
        """
        L{text.endsInNewline} returns C{True} if the string ends in a newline.
        """
        s = 'newline\n'
        m = text.endsInNewline(s)
        self.assertTrue(m)

        s = 'oldline'
        m = text.endsInNewline(s)
        self.assertFalse(m)



class StringyStringTests(unittest.TestCase):
    """
    Tests for L{text.stringyString}.
    """
    def test_tuple(self):
        """
        Tuple elements are displayed on separate lines.
        """
        s = ('a', 'b')
        m = text.stringyString(s)
        self.assertEqual(m, '(a,\n b,)\n')


    def test_dict(self):
        """
        Dicts elements are displayed using C{str()}.
        """
        s = {'a': 0}
        m = text.stringyString(s)
        self.assertEqual(m, '{a: 0}')


    def test_list(self):
        """
        List elements are displayed on separate lines using C{str()}.
        """
        s = ['a', 'b']
        m = text.stringyString(s)
        self.assertEqual(m, '[a,\n b,]\n')



class SplitTests(unittest.TestCase):
    """
    Tests for L{text.splitQuoted}.
    """
    def test_oneWord(self):
        """
        Splitting strings with one-word phrases.
        """
        s = 'This code "works."'
        r = text.splitQuoted(s)
        self.assertEqual(['This', 'code', 'works.'], r)


    def test_multiWord(self):
        s = 'The "hairy monkey" likes pie.'
        r = text.splitQuoted(s)
        self.assertEqual(['The', 'hairy monkey', 'likes', 'pie.'], r)

    # Some of the many tests that would fail:

    #def test_preserveWhitespace(self):
    #    phrase = '"MANY     SPACES"'
    #    s = 'With %s between.' % (phrase,)
    #    r = text.splitQuoted(s)
    #    self.assertEqual(['With', phrase, 'between.'], r)

    #def test_escapedSpace(self):
    #    s = r"One\ Phrase"
    #    r = text.splitQuoted(s)
    #    self.assertEqual(["One Phrase"], r)



class StrFileTests(unittest.TestCase):
    def setUp(self):
        self.io = StringIO("this is a test string")

    def tearDown(self):
        pass

    def test_1_f(self):
        self.assertFalse(text.strFile("x", self.io))

    def test_1_1(self):
        self.assertTrue(text.strFile("t", self.io))

    def test_1_2(self):
        self.assertTrue(text.strFile("h", self.io))

    def test_1_3(self):
        self.assertTrue(text.strFile("i", self.io))

    def test_1_4(self):
        self.assertTrue(text.strFile("s", self.io))

    def test_1_5(self):
        self.assertTrue(text.strFile("n", self.io))

    def test_1_6(self):
        self.assertTrue(text.strFile("g", self.io))

    def test_3_1(self):
        self.assertTrue(text.strFile("thi", self.io))

    def test_3_2(self):
        self.assertTrue(text.strFile("his", self.io))

    def test_3_3(self):
        self.assertTrue(text.strFile("is ", self.io))

    def test_3_4(self):
        self.assertTrue(text.strFile("ing", self.io))

    def test_3_f(self):
        self.assertFalse(text.strFile("bla", self.io))

    def test_large_1(self):
        self.assertTrue(text.strFile("this is a test", self.io))

    def test_large_2(self):
        self.assertTrue(text.strFile("is a test string", self.io))

    def test_large_f(self):
        self.assertFalse(text.strFile("ds jhfsa k fdas", self.io))


    def test_overlarge_f(self):
        self.assertFalse(text.strFile(
                         "djhsakj dhsa fkhsa s,mdbnfsauiw bndasdf hreew",
                         self.io))


    def test_self(self):
        self.assertTrue(text.strFile("this is a test string", self.io))

    def test_insensitive(self):
        self.assertTrue(text.strFile("ThIs is A test STRING", self.io, False))

