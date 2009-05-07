# -*- coding: utf-8 -*-
import unittest

from scrapy.utils.markup import remove_entities, replace_tags, remove_comments
from scrapy.utils.markup import remove_tags_with_content, remove_escape_chars, remove_tags
from scrapy.utils.markup import unquote_markup

class UtilsMarkupTest(unittest.TestCase):

    def test_remove_entities(self):
        # make sure it always return uncode
        assert isinstance(remove_entities('no entities'), unicode)
        assert isinstance(remove_entities('Price: &pound;100!'),  unicode)

        # regular conversions
        self.assertEqual(remove_entities(u'As low as &#163;100!'),
                         u'As low as \xa3100!')
        self.assertEqual(remove_entities('As low as &pound;100!'),
                         u'As low as \xa3100!')
        self.assertEqual(remove_entities('redirectTo=search&searchtext=MR0221Y&aff=buyat&affsrc=d_data&cm_mmc=buyat-_-ELECTRICAL & SEASONAL-_-MR0221Y-_-9-carat gold &frac12;oz solid crucifix pendant'),
                         u'redirectTo=search&searchtext=MR0221Y&aff=buyat&affsrc=d_data&cm_mmc=buyat-_-ELECTRICAL & SEASONAL-_-MR0221Y-_-9-carat gold \xbdoz solid crucifix pendant')
        # keep some entities
        self.assertEqual(remove_entities('<b>Low &lt; High &amp; Medium &pound; six</b>', keep=['lt', 'amp']),
                         u'<b>Low &lt; High &amp; Medium \xa3 six</b>')

        # illegal entities
        self.assertEqual(remove_entities('a &lt; b &illegal; c &#12345678; six', remove_illegal=False),
                         u'a < b &illegal; c &#12345678; six')
        self.assertEqual(remove_entities('a &lt; b &illegal; c &#12345678; six', remove_illegal=True),
                         u'a < b  c  six')
        self.assertEqual(remove_entities('x&#x2264;y'), u'x\u2264y')


    def test_replace_tags(self):
        # make sure it always return uncode
        assert isinstance(replace_tags('no entities'), unicode)

        self.assertEqual(replace_tags(u'This text contains <a>some tag</a>'),
                         u'This text contains some tag')

        self.assertEqual(replace_tags('This text is very im<b>port</b>ant', ' '),
                         u'This text is very im port ant')

        # multiline tags
        self.assertEqual(replace_tags('Click <a class="one"\r\n href="url">here</a>'),
                         u'Click here')

    def test_remove_comments(self):
        # make sure it always return unicode
        assert isinstance(remove_comments('without comments'), unicode)
        assert isinstance(remove_comments('<!-- with comments -->'), unicode)

        # text without comments 
        self.assertEqual(remove_comments(u'text without comments'), u'text without comments')

        # text with comments
        self.assertEqual(remove_comments(u'<!--text with comments-->'), u'')
        self.assertEqual(remove_comments(u'Hello<!--World-->'),u'Hello')

    def test_remove_tags(self):
        # make sure it always return unicode
        assert isinstance(remove_tags('no tags'), unicode)
        assert isinstance(remove_tags('no tags', which_ones=('p',)), unicode)
        assert isinstance(remove_tags('<p>one tag</p>'), unicode)
        assert isinstance(remove_tags('<p>one tag</p>', which_ones=('p')), unicode)
        assert isinstance(remove_tags('<a>link</a>', which_ones=('b',)), unicode)

        # text without tags
        self.assertEqual(remove_tags(u'no tags'), u'no tags')
        self.assertEqual(remove_tags(u'no tags', which_ones=('p','b',)), u'no tags')

        # text with tags
        self.assertEqual(remove_tags(u'<p>one p tag</p>'), u'one p tag')
        self.assertEqual(remove_tags(u'<p>one p tag</p>', which_ones=('b',)), u'<p>one p tag</p>')

        self.assertEqual(remove_tags(u'<b>not will removed</b><i>i will removed</i>', which_ones=('i',)),
                         u'<b>not will removed</b>i will removed')

        # text with tags and attributes
        self.assertEqual(remove_tags(u'<p align="center" class="one">texty</p>'), u'texty')
        self.assertEqual(remove_tags(u'<p align="center" class="one">texty</p>', which_ones=('b',)),
                         u'<p align="center" class="one">texty</p>')

    def test_remove_tags_with_content(self):
        # make sure it always return unicode
        assert isinstance(remove_tags_with_content('no tags'), unicode)
        assert isinstance(remove_tags_with_content('no tags', which_ones=('p',)), unicode)
        assert isinstance(remove_tags_with_content('<p>one tag</p>', which_ones=('p',)), unicode)
        assert isinstance(remove_tags_with_content('<a>link</a>', which_ones=('b',)), unicode)

        # text without tags
        self.assertEqual(remove_tags_with_content(u'no tags'), u'no tags')
        self.assertEqual(remove_tags_with_content(u'no tags', which_ones=('p','b',)), u'no tags')

        # text with tags
        self.assertEqual(remove_tags_with_content(u'<p>one p tag</p>'), u'<p>one p tag</p>')
        self.assertEqual(remove_tags_with_content(u'<p>one p tag</p>', which_ones=('p',)), u'')

        self.assertEqual(remove_tags_with_content(u'<b>not will removed</b><i>i will removed</i>', which_ones=('i',)),
                         u'<b>not will removed</b>')

    def test_remove_escape_chars(self):
        # make sure it always return unicode
        assert isinstance(remove_escape_chars('no ec'), unicode)
        assert isinstance(remove_escape_chars('no ec', which_ones=('\n','\t',)), unicode)

        # text without escape chars
        self.assertEqual(remove_escape_chars(u'no ec'), u'no ec')
        self.assertEqual(remove_escape_chars(u'no ec', which_ones=('\n',)), u'no ec')

        # text with escape chars
        self.assertEqual(remove_escape_chars(u'escape\n\n'), u'escape')
        self.assertEqual(remove_escape_chars(u'escape\n', which_ones=('\t',)), u'escape\n')
        self.assertEqual(remove_escape_chars(u'escape\tchars\n', which_ones=('\t')), 'escapechars\n')
        self.assertEqual(remove_escape_chars(u'escape\tchars\n', replace_by=' '), 'escape chars ')

    def test_unquote_markup(self):
        sample_txt1 = u"""<node1>hi, this is sample text with entities: &amp; &copy;
<![CDATA[although this is inside a cdata! &amp; &quot;]]></node1>"""
        sample_txt2 = u'<node2>blah&amp;blah<![CDATA[blahblahblah!&pound;]]>moreblah&lt;&gt;</node2>'
        sample_txt3 = u'something&pound;&amp;more<node3><![CDATA[things, stuff, and such]]>what&quot;ever</node3><node4'

        # make sure it always return unicode
        assert isinstance(unquote_markup(sample_txt1.encode('latin-1')), unicode)
        assert isinstance(unquote_markup(sample_txt2), unicode)

        self.assertEqual(unquote_markup(sample_txt1), u"""<node1>hi, this is sample text with entities: & \xa9
although this is inside a cdata! &amp; &quot;</node1>""")

        self.assertEqual(unquote_markup(sample_txt2), u'<node2>blah&blahblahblahblah!&pound;moreblah<></node2>')

        self.assertEqual(unquote_markup(sample_txt1 + sample_txt2), u"""<node1>hi, this is sample text with entities: & \xa9
although this is inside a cdata! &amp; &quot;</node1><node2>blah&blahblahblahblah!&pound;moreblah<></node2>""")

        self.assertEqual(unquote_markup(sample_txt3), u'something\xa3&more<node3>things, stuff, and suchwhat"ever</node3><node4')
