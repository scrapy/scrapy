import re, csv, six

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

from scrapy.http import TextResponse, Response
from scrapy.selector import Selector
from scrapy import log
from scrapy.utils.python import re_rsearch, str_to_unicode


def xmliter(obj, nodename):
    """Return a iterator of Selector's over all nodes of a XML document,
       given tha name of the node to iterate. Useful for parsing XML feeds.

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8
    """
    DOCUMENT_HEADER_RE = re.compile(r'<\?xml[^>]+>\s*', re.S)
    HEADER_END_RE = re.compile(r'<\s*/%s\s*>' % nodename, re.S)
    END_TAG_RE = re.compile(r'<\s*/([^\s>]+)\s*>', re.S)
    NAMESPACE_RE = re.compile(r'((xmlns[:A-Za-z]*)=[^>\s]+)', re.S)
    text = _body_or_str(obj)

    document_header = re.search(DOCUMENT_HEADER_RE, text)
    document_header = document_header.group().strip() if document_header else ''
    header_end_idx = re_rsearch(HEADER_END_RE, text)
    header_end = text[header_end_idx[1]:].strip() if header_end_idx else ''
    namespaces = {}
    if header_end:
        for tagname in reversed(re.findall(END_TAG_RE, header_end)):
            tag = re.search(r'<\s*%s.*?xmlns[:=][^>]*>' % tagname, text[:header_end_idx[1]], re.S)
            if tag:
                namespaces.update(reversed(x) for x in re.findall(NAMESPACE_RE, tag.group()))

    r = re.compile(r"<%s[\s>].*?</%s>" % (nodename, nodename), re.DOTALL)
    for match in r.finditer(text):
        nodetext = document_header + match.group().replace(nodename, '%s %s' % (nodename, ' '.join(namespaces.values())), 1) + header_end
        yield Selector(text=nodetext, type='xml')


def csviter(obj, delimiter=None, headers=None, encoding=None):
    """ Returns an iterator of dictionaries from the given csv object

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8

    delimiter is the character used to separate field on the given obj.

    headers is an iterable that when provided offers the keys
    for the returned dictionaries, if not the first row is used.
    """
    encoding = obj.encoding if isinstance(obj, TextResponse) else encoding or 'utf-8'
    def _getrow(csv_r):
        return [str_to_unicode(field, encoding) for field in next(csv_r)]

    lines = BytesIO(_body_or_str(obj, unicode=False))
    if delimiter:
        csv_r = csv.reader(lines, delimiter=delimiter)
    else:
        csv_r = csv.reader(lines)

    if not headers:
        headers = _getrow(csv_r)

    while True:
        row = _getrow(csv_r)
        if len(row) != len(headers):
            log.msg(format="ignoring row %(csvlnum)d (length: %(csvrow)d, should be: %(csvheader)d)",
                    level=log.WARNING, csvlnum=csv_r.line_num, csvrow=len(row), csvheader=len(headers))
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
