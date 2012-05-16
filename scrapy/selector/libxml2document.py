"""
This module contains a simple class (Libxml2Document) which provides cache and
garbage collection to libxml2 documents (xmlDoc).
"""

import weakref
from scrapy.utils.trackref import object_ref
from scrapy import optional_features

if 'libxml2' in optional_features:
    import libxml2
    xml_parser_options = libxml2.XML_PARSE_RECOVER + \
                         libxml2.XML_PARSE_NOERROR + \
                         libxml2.XML_PARSE_NOWARNING

    html_parser_options = libxml2.HTML_PARSE_RECOVER + \
                          libxml2.HTML_PARSE_NOERROR + \
                          libxml2.HTML_PARSE_NOWARNING


_UTF8_ENCODINGS = set(('utf-8', 'UTF-8', 'utf8', 'UTF8'))
def _body_as_utf8(response):
    if response.encoding in _UTF8_ENCODINGS:
        return response.body
    else:
        return response.body_as_unicode().encode('utf-8')


def xmlDoc_from_html(response):
    """Return libxml2 doc for HTMLs"""
    utf8body = _body_as_utf8(response) or ' '
    try:
        lxdoc = libxml2.htmlReadDoc(utf8body, response.url, 'utf-8', \
            html_parser_options)
    except TypeError:  # libxml2 doesn't parse text with null bytes
        lxdoc = libxml2.htmlReadDoc(utf8body.replace("\x00", ""), response.url, \
            'utf-8', html_parser_options)
    return lxdoc


def xmlDoc_from_xml(response):
    """Return libxml2 doc for XMLs"""
    utf8body = _body_as_utf8(response) or ' '
    try:
        lxdoc = libxml2.readDoc(utf8body, response.url, 'utf-8', \
            xml_parser_options)
    except TypeError:  # libxml2 doesn't parse text with null bytes
        lxdoc = libxml2.readDoc(utf8body.replace("\x00", ""), response.url, \
            'utf-8', xml_parser_options)
    return lxdoc


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
