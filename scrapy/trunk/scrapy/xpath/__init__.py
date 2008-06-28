"""
The scrapy.xpath module provides useful classes for parsing HTML and XML
documents using XPath. It requires libxml2 and its python bindings.

This parent module exports the classes most commonly used when building
spiders, for convenience.

* XPath - a simple class to represent a XPath expression
* XPathSelector - to extract data using XPaths (parses the entire response)
* XMLNodeIterator - to iterate over XML nodes without parsing the entire response in memory
"""

from scrapy.xpath.types import XPath
from scrapy.xpath.selector import XPathSelector
from scrapy.xpath.iterator import XMLNodeIterator
