"""A django alike request-response model

most of this code is borrowed from django
"""

from Cookie import SimpleCookie
from scrapy.utils.datatypes import MultiValueDict, CaselessDict


def build_httprequest(twistedrequest):
    """Translate twisted request object to a django request approach"""
    request = HttpRequest()
    request.path = twistedrequest.path
    request.method = twistedrequest.method.upper()
    request.COOKIES = SimpleCookie(twistedrequest.received_cookies)
    request.HEADERS = Headers(twistedrequest.received_headers)
    request.ARGS = MultiValueDict(twistedrequest.args)
    request.FILES = {} # not yet supported
    request.content = twistedrequest.content
    request.twistedrequest = twistedrequest
    return request


class HttpRequest(object):
    def __init__(self):
        self.path = ''
        self.method = None
        self.COOKIES = {}
        self.HEADERS = {}
        self.ARGS = {}
        self.FILES = {}


class HttpResponse(object):
    status_code = 200

    def __init__(self, content='', status=None, content_type=None):
        content_type = content_type or "text/html; charset=utf-8"
        self._headers = {'content-type': content_type}
        self.content = content
        self.cookies = SimpleCookie()
        self.status_code = status

    def __str__(self):
        "Full HTTP message, including headers"
        return '\n'.join(['%s: %s' % (key, value)
            for key, value in self._headers.items()]) \
            + '\n\n' + self.content

    def __setitem__(self, header, value):
        self._headers[header.lower()] = value

    def __delitem__(self, header):
        try:
            del self._headers[header.lower()]
        except KeyError:
            pass

    def __getitem__(self, header):
        return self._headers[header.lower()]

    def has_header(self, header):
        "Case-insensitive check for a header"
        return self._headers.has_key(header.lower())

    __contains__ = has_header

    def items(self):
        return self._headers.items()

    def get(self, header, alternate):
        return self._headers.get(header, alternate)

    def set_cookie(self, key, value='', max_age=None, expires=None, path='/', domain=None, secure=None):
        self.cookies[key] = value
        for var in ('max_age', 'path', 'domain', 'secure', 'expires'):
            val = locals()[var]
            if val is not None:
                self.cookies[key][var.replace('_', '-')] = val

    def delete_cookie(self, key, path='/', domain=None):
        self.cookies[key] = ''
        if path is not None:
            self.cookies[key]['path'] = path
        if domain is not None:
            self.cookies[key]['domain'] = domain
        self.cookies[key]['expires'] = 0
        self.cookies[key]['max-age'] = 0


class Headers(CaselessDict):
    def __init__(self, source=None, encoding='utf-8'):
        self.encoding = encoding

        if getattr(source, 'iteritems', None):
            d = source.iteritems()
        else:
            d = source # best effort

        # can't use CaselessDict.__init__(self, d) because it doesn't call __setitem__
        for k,v in d:
            self.__setitem__(k.lower(), v) 

    def normkey(self, key):
        return key.title() # 'Content-Type' styles headers

    def __setitem__(self, key, value):
        """Headers must not be unicode"""
        if isinstance(key, unicode):
            key = key.encode(self.encoding)
        if isinstance(value, unicode):
            value = value.encode(self.encoding)
        super(Headers, self).__setitem__(key, value)


