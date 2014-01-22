from unittest import TestCase
import six
import scrapy


class ToplevelTestCase(TestCase):

    def test_version(self):
        self.assertIs(type(scrapy.__version__), six.text_type)

    def test_version_info(self):
        self.assertIs(type(scrapy.version_info), tuple)

    def test_optional_features(self):
        self.assertIs(type(scrapy.optional_features), set)
        self.assertIn('ssl', scrapy.optional_features)
