"""
This module contains a simple class (Libxml2Document) to wrap libxml2 documents
(xmlDoc) for proper garbage collection.
"""

from scrapy.xpath.constructors import xmlDoc_from_html

class Libxml2Document(object):

    def __init__(self, response, constructor=xmlDoc_from_html):
        self.xmlDoc = constructor(response)
        self.xpathContext = self.xmlDoc.xpathNewContext()

    def __del__(self):
        if hasattr(self, 'xmlDoc'):
            self.xmlDoc.freeDoc()
        if hasattr(self, 'xpathContext'):
            self.xpathContext.xpathFreeContext()

    def __str__(self):
        return "<Libxml2Document %s>" % self.xmlDoc.name

