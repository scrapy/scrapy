import re

from scrapy.xpath import XmlXPathSelector
from scrapy.http import Response

def xpathselector_iternodes(obj, nodename):
    """Return a iterator of XPathSelector's over all nodes of a XML document,
       given tha name of the node to iterate. Useful for parsing XML feeds.

    obj can be:
    - a Response object
    - a unicode string
    - a string encoded as utf-8
    """
    
    assert isinstance(obj, (Response, basestring)), "obj must be Response or basestring, not %s" % type(obj).__name__

    if isinstance(obj, Response):
        text = obj.body.to_unicode()
    elif isinstance(obj, str):
        text = obj.decode('utf-8')

    r = re.compile(r"<%s[\s>].*?</%s>" % (nodename, nodename), re.DOTALL)
    for match in r.finditer(text):
        nodetext = match.group()
        yield XmlXPathSelector(text=nodetext).x('/' + nodename)[0]
