from parsel.csstranslator import XPathExpr, GenericTranslator, HTMLTranslator
from scrapy.utils.deprecate import create_deprecated_class


ScrapyXPathExpr = create_deprecated_class(
    'ScrapyXPathExpr', XPathExpr,
    new_class_path='parsel.csstranslator.XPathExpr')

ScrapyGenericTranslator = create_deprecated_class(
    'ScrapyGenericTranslator', GenericTranslator,
    new_class_path='parsel.csstranslator.GenericTranslator')

ScrapyHTMLTranslator = create_deprecated_class(
    'ScrapyHTMLTranslator', HTMLTranslator,
    new_class_path='parsel.csstranslator.HTMLTranslator')
