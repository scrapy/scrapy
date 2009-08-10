"""
The scrapy.xpath module provides useful classes for selecting HTML and XML
documents using XPath. It requires libxml2 and its python bindings.

This parent module exports the classes most commonly used when building
spiders, for convenience.
"""

from scrapy.xpath.selector import XPathSelector, XmlXPathSelector, HtmlXPathSelector
