"""
Selector tests for cssselect backend
"""
import warnings
from twisted.trial import unittest
from scrapy.selector.csstranslator import (
    ScrapyHTMLTranslator,
    ScrapyGenericTranslator,
    ScrapyXPathExpr
)


class DeprecatedClassesTest(unittest.TestCase):

    def test_deprecated_warnings(self):
        for cls in [ScrapyHTMLTranslator, ScrapyGenericTranslator, ScrapyXPathExpr]:
            with warnings.catch_warnings(record=True) as w:
                obj = cls()
                self.assertIn('%s is deprecated' % cls.__name__, str(w[-1].message),
                              'Missing deprecate warning for %s' % cls.__name__)


