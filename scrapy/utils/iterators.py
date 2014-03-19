import re, csv
from cStringIO import StringIO
from importlib import import_module
from utils import walk_modules

from scrapy.http import TextResponse, Response
from scrapy.selector import Selector
from scrapy import log
from scrapy.utils.python import re_rsearch, str_to_unicode

def iter_classes(module_name, parent_module_name, parent_name, is_file=False):
    """Return an iterator over all classes defined in the given module
    that can be instantiated (i.e. have a name)

    obj can be:
    - a module name string
    - a file name string pointing to a module
    """

    parent_module = import_module(parent_module_name)
    parent_class = getattr(parent_module, parent_name)()

    for module in walk_modules(module_name, is_file=is_file):
        for obj in vars(module).itervalues():
            if inspect.isclass(obj) and \
                issubclass(obj, parent_class) and \
                obj.__module__ == module.__name__ and \
                getattr(obj, 'name', None):
                    yield obj


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

    lines = StringIO(_body_or_str(obj, unicode=False))
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
    assert isinstance(obj, (Response, basestring)), \
        "obj must be Response or basestring, not %s" % type(obj).__name__
    if isinstance(obj, Response):
        if not unicode:
            return obj.body
        elif isinstance(obj, TextResponse):
            return obj.body_as_unicode()
        else:
            return obj.body.decode('utf-8')
    elif type(obj) is type(u''):
        return obj if unicode else obj.encode('utf-8')
    else:
        return obj.decode('utf-8') if unicode else obj
