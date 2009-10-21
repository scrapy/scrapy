"""
This module contains a simple class (Libxml2Document) which provides cache and
garbage collection to libxml2 documents (xmlDoc).
"""

import weakref

from scrapy.utils.trackref import object_ref
from .factories import xmlDoc_from_html

class Libxml2Document(object_ref):

    cache = weakref.WeakKeyDictionary()
    __slots__ = ['xmlDoc', 'xpathContext', '__weakref__']

    def __new__(cls, response, factory=xmlDoc_from_html):
        cache = cls.cache.setdefault(response, {})
        if factory not in cache:
            obj = object_ref.__new__(cls)
            obj.xmlDoc = factory(response)
            obj.xpathContext = obj.xmlDoc.xpathNewContext()
            cache[factory] = obj
        return cache[factory]

    def __del__(self):
        # we must call both cleanup functions, so we try/except all exceptions
        # to make sure one doesn't prevent the other from being called
        # this call sometimes raises a "NoneType is not callable" TypeError
        # so the try/except block silences them
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
