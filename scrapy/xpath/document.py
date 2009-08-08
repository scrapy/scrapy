"""
This module contains a simple class (Libxml2Document) to wrap libxml2 documents
(xmlDoc) for proper garbage collection.
"""

from scrapy.xpath.factories import xmlDoc_from_html

class Libxml2Document(object):

    def __init__(self, response, factory=xmlDoc_from_html):
        self.xmlDoc = factory(response)
        self.xpathContext = self.xmlDoc.xpathNewContext()

    def __del__(self):
        # we must call both cleanup functions, so we try/except all exceptions
        # to make sure one doesn't prevent the other from being called
        # this call sometimes raises a "NoneType is not callable" TypeError
        # also, these calls sometimes raise a "NoneType is not callable"
        # TypeError, so the try/except block silences them
        try:
            self.xmlDoc.freeDoc()
        except:
            pass
        try:
            self.xpathContext.xpathFreeContext()
        except:
            pass

    def __str__(self):
        return "<Libxml2Document %s>" % self.xmlDoc.name
