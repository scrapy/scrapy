"""
This module contains a simple class (LxmlDocument) which provides cache and
garbage collection to lxml element tree documents.
"""

import weakref
from lxml import etree
from scrapy.utils.trackref import object_ref


def _factory(response, parser_cls):
    url = response.url
    body = response.body_as_unicode().strip().encode('utf8') or '<html/>'
    parser = parser_cls(recover=True, encoding='utf8')
    return etree.fromstring(body, parser=parser, base_url=url)


class LxmlDocument(object_ref):

    cache = weakref.WeakKeyDictionary()
    __slots__ = ['__weakref__']

    def __new__(cls, response, parser=etree.HTMLParser):
        cache = cls.cache.setdefault(response, {})
        if parser not in cache:
            obj = object_ref.__new__(cls)
            cache[parser] = _factory(response, parser)
        return cache[parser]

    def __str__(self):
        return "<LxmlDocument %s>" % self.root.tag
