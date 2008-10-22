from scrapy.utils.datatypes import CaselessDict

def headers_raw_to_dict(headers_raw):
    """
    Convert raw headers (single multi-line string)
    to the dictionary.
    
    For example:
    >>> headers_raw_to_dict("Content-type: text/html\\n\\rAccept: gzip\\n\\n")
    {'Content-type': ['text/html'], 'Accept': ['gzip']}
    
    Incorrect input:
    >>> headers_raw_to_dict("Content-typt gzip\\n\\n")
    {}
    
    Argument is None:
    >>> headers_raw_to_dict(None)
    """
    if headers_raw is None:
        return None 
    return dict([
        (header_item[0].strip(), [header_item[1].strip()]) 
        for header_item 
        in [
            header.split(':', 1) 
            for header 
            in headers_raw.splitlines()] 
        if len(header_item) == 2])
        
def headers_dict_to_raw(headers_dict):
    """
    Returns a raw HTTP headers representation of headers
    
    For example:
    >>> headers_dict_to_raw({'Content-type': 'text/html', 'Accept': 'gzip'})
    'Content-type: text/html\\r\\nAccept: gzip'
    >>> from twisted.python.util import InsensitiveDict
    >>> td = InsensitiveDict({'Content-type': ['text/html'], 'Accept': ['gzip']})
    >>> headers_dict_to_raw(td)
    'Content-type: text/html\\r\\nAccept: gzip'
    
    Argument is None:
    >>> headers_dict_to_raw(None)
    
    """
    if headers_dict is None:
        return None
    raw_lines = []
    for key, value in headers_dict.items():
        if isinstance(value, (str, unicode)):
            raw_lines.append("%s: %s" % (key, value))
        elif isinstance(value, (list, tuple)):
            for v in value:
                raw_lines.append("%s: %s" % (key, v))
    return '\r\n'.join(raw_lines)

class Headers(CaselessDict):
    def __init__(self, dictorstr=None, fromdict=None, fromstr=None, encoding='utf-8'):
        self.encoding = encoding

        if dictorstr is not None:
            if isinstance(dictorstr, dict):
                d = dictorstr
            elif isinstance(dictorstr, basestring):
                d = headers_raw_to_dict(dictorstr)
        elif fromdict is not None:
            d = fromdict
        elif fromstr is not None:
            d = headers_raw_to_dict(fromstr)
        else:
            d = {}

        # can't use CaselessDict.__init__(self, d) because it doesn't call __setitem__
        for k,v in d.iteritems(): 
            self.__setitem__(k.lower(), v) 

    def normkey(self, key):
        return key.title()

    def __setitem__(self, key, value):
        """Headers must not be unicode"""
        if isinstance(key, unicode):
            key = key.encode(self.encoding)
        if isinstance(value, unicode):
            value = value.encode(self.encoding)
        super(Headers, self).__setitem__(key, value)

    def tostring(self):
        return headers_dict_to_raw(self)

    def rawsize(self):
        """Estimated size of raw HTTP headers, in bytes"""
        # For each header line you have 4 extra chars: ": " and CRLF
        return sum([len(k)+len(v)+4 for k, v in self.iteritems()])

    def to_string(self):
        return headers_dict_to_raw(self)
