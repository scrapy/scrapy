import re, csv

from scrapy.xpath import XmlXPathSelector
from scrapy.http import Response
from scrapy import log

def _normalize_input(obj):
    assert isinstance(obj, (Response, basestring)), "obj must be Response or basestring, not %s" % type(obj).__name__
    if isinstance(obj, Response):
        return obj.body.to_unicode()
    elif isinstance(obj, str):
        return obj.decode('utf-8')
    else:
        return obj

def xmliter(obj, nodename):
    """Return a iterator of XPathSelector's over all nodes of a XML document,
       given tha name of the node to iterate. Useful for parsing XML feeds.

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8
    """
    text = _normalize_input(obj)

    r = re.compile(r"<%s[\s>].*?</%s>" % (nodename, nodename), re.DOTALL)
    for match in r.finditer(text):
        nodetext = match.group()
        yield XmlXPathSelector(text=nodetext).x('/' + nodename)[0]

def csviter(obj, delimiter=None, headers=None):
    """ Returns an iterator of dictionaries from the given csv object

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8

    delimiter is the character used to separate field on the given obj.
    
    headers is an iterable that when provided offers the keys
    for the returned dictionaries, if not the first row is used.
    """
    def _getrow(csv_r):
        return [field.decode() for field in csv_r.next()]

    lines = _normalize_input(obj).splitlines(True)
    if delimiter:
        csv_r = csv.reader(lines, delimiter=delimiter)
    else:
        csv_r = csv.reader(lines)

    if not headers:
        headers = _getrow(csv_r)

    while True:
        row = _getrow(csv_r)
        if len(row) != len(headers):
            log.msg("ignoring row %d (length: %d, should be: %d)" % (csv_r.line_num, len(row), len(headers)), log.WARNING)
            continue
        else:
            yield dict(zip(headers, row))

