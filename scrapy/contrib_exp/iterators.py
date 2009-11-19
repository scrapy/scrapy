from scrapy.http import Response
from scrapy.selector import XmlXPathSelector


def xmliter_lxml(obj, nodename):
    from lxml import etree
    reader = _StreamReader(obj)
    iterable = etree.iterparse(reader, tag=nodename, encoding=reader.encoding)
    for _, node in iterable:
        nodetext = etree.tostring(node)
        node.clear()
        yield XmlXPathSelector(text=nodetext).select('//' + nodename)[0]


class _StreamReader(object):

    def __init__(self, obj):
        self._ptr = 0
        if isinstance(obj, Response):
            self._text, self.encoding = obj.body, obj.encoding
        else:
            self._text, self.encoding = obj, 'utf-8'
        self._is_unicode = isinstance(self._text, unicode)

    def read(self, n=65535):
        self.read = self._read_unicode if self._is_unicode else self._read_string
        return self.read(n).lstrip()

    def _read_string(self, n=65535):
        s, e = self._ptr, self._ptr + n
        self._ptr = e
        return self._text[s:e]

    def _read_unicode(self, n=65535):
        s, e = self._ptr, self._ptr + n
        self._ptr = e
        return self._text[s:e].encode('utf-8')
