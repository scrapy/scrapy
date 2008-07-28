import unittest

from scrapy.utils.markup import remove_entities, replace_tags

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

        # keep some entities
        self.assertEqual(remove_entities('<b>Low &lt; High &amp; Medium &pound; six</b>', keep=['lt', 'amp']),
                         u'<b>Low &lt; High &amp; Medium \xa3 six</b>')

        # illegal entities
        self.assertEqual(remove_entities('a &lt; b &illegal; c &#12345678; six', remove_illegal=False),
                         u'a < b &illegal; c &#12345678; six')
        self.assertEqual(remove_entities('a &lt; b &illegal; c &#12345678; six', remove_illegal=True),
                         u'a < b  c  six')

    def test_remove_tags(self):
        # make sure it always return uncode
        assert isinstance(replace_tags('no entities'), unicode)

        self.assertEqual(replace_tags(u'This text contains <a>some tag</a>'),
                         u'This text contains some tag')

        self.assertEqual(replace_tags('This text is very im<b>port</b>ant', ' '),
                         u'This text is very im port ant')

        # multiline tags
        self.assertEqual(replace_tags('Click <a class="one"\r\n href="url">here</a>'),
                         u'Click here')
