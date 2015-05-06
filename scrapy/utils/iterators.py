import re
import csv
import logging

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

import six

from scrapy.http import TextResponse, Response
from scrapy.selector import Selector
from scrapy.utils.python import re_rsearch, str_to_unicode

logger = logging.getLogger(__name__)


def xmliter(obj, nodename):
    """Return a iterator of Selector's over all nodes of a XML document,
       given tha name of the node to iterate. Useful for parsing XML feeds.

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8
    """
    HEADER_START_RE = re.compile(r'^(.*?)<\s*%s(?:\s|>)' % nodename, re.S)
    HEADER_END_RE = re.compile(r'<\s*/%s\s*>' % nodename, re.S)
    text = _body_or_str(obj)

    header_start = re.search(HEADER_START_RE, text)
    header_start = header_start.group(1).strip() if header_start else ''
    header_end = re_rsearch(HEADER_END_RE, text)
    header_end = text[header_end[1]:].strip() if header_end else ''

    r = re.compile(r"<%s[\s>].*?</%s>" % (nodename, nodename), re.DOTALL)
    for match in r.finditer(text):
        nodetext = header_start + match.group() + header_end
        yield Selector(text=nodetext, type='xml').xpath('//' + nodename)[0]


def xmliter_lxml(obj, nodename, namespace=None, prefix='x'):
    from lxml import etree
    reader = _StreamReader(obj)
    tag = '{%s}%s' % (namespace, nodename) if namespace else nodename
    iterable = etree.iterparse(reader, tag=tag, encoding=reader.encoding)
    selxpath = '//' + ('%s:%s' % (prefix, nodename) if namespace else nodename)
    for _, node in iterable:
        nodetext = etree.tostring(node)
        node.clear()
        xs = Selector(text=nodetext, type='xml')
        if namespace:
            xs.register_namespace(prefix, namespace)
        yield xs.xpath(selxpath)[0]


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


def csviter(obj, delimiter=None, headers=None, encoding=None, quotechar=None):
    """ Returns an iterator of dictionaries from the given csv object

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8

    delimiter is the character used to separate fields on the given obj.

    headers is an iterable that when provided offers the keys
    for the returned dictionaries, if not the first row is used.
    
    quotechar is the character used to enclosure fields on the given obj.
    """

    encoding = obj.encoding if isinstance(obj, TextResponse) else encoding or 'utf-8'
    def _getrow(csv_r):
        return [str_to_unicode(field, encoding) for field in next(csv_r)]

    lines = BytesIO(_body_or_str(obj, unicode=False))

    kwargs = {}
    if delimiter: kwargs["delimiter"] = delimiter
    if quotechar: kwargs["quotechar"] = quotechar
    csv_r = csv.reader(lines, **kwargs)

    if not headers:
        headers = _getrow(csv_r)

    while True:
        row = _getrow(csv_r)
        if len(row) != len(headers):
            logger.warning("ignoring row %(csvlnum)d (length: %(csvrow)d, "
                           "should be: %(csvheader)d)",
                           {'csvlnum': csv_r.line_num, 'csvrow': len(row),
                            'csvheader': len(headers)})
            continue
        else:
            yield dict(zip(headers, row))


def _body_or_str(obj, unicode=True):
    assert isinstance(obj, (Response, six.string_types)), \
        "obj must be Response or basestring, not %s" % type(obj).__name__
    if isinstance(obj, Response):
        if not unicode:
            return obj.body
        elif isinstance(obj, TextResponse):
            return obj.body_as_unicode()
        else:
            return obj.body.decode('utf-8')
    elif isinstance(obj, six.text_type):
        return obj if unicode else obj.encode('utf-8')
    else:
        return obj.decode('utf-8') if unicode else obj
