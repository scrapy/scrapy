from urlparse import urlunparse

from twisted.web.client import HTTPClientFactory

from scrapy.http import Url

def _parse(url, defaultPort=None):
    url = url.strip()
    try:
        parsed = url.parsedurl
    except AttributeError:
        parsed = Url(url).parsedurl

    scheme = parsed[0]
    path = urlunparse(('','')+parsed[2:])
    if defaultPort is None:
        if scheme == 'https':
            defaultPort = 443
        else:
            defaultPort = 80
    host, port = parsed[1], defaultPort
    if ':' in host:
        host, port = host.split(':')
        port = int(port)
    if path == "":
        path = "/"
    return scheme, host, port, path


class ScrapyHTTPClientFactory(HTTPClientFactory):
    """Scrapy implementation of the HTTPClientFactory overwriting the
    serUrl method to make use of our Url object that cache the parse 
    result. Also we override gotHeaders that dies when parsing malformed 
    cookies.
    """

    def setURL(self, url):
        self.url = url
        scheme, host, port, path = _parse(url)
        if scheme and host:
            self.scheme = scheme
            self.host = host
            self.port = port
        self.path = path

    def gotHeaders(self, headers):
        """
        HTTPClientFactory.gotHeaders dies when parsing malformed cookies,
        and the crawler is getting malformed cookies from this site.

        Cookies format: 
            http://www.ietf.org/rfc/rfc2109.txt
        
        I have choosen not to filter based on this, so we don't filter invalid
        values that could be managed correctly by twisted.
        """
        self.response_headers = headers
        if 'set-cookie' in headers:
            goodcookies = []
            for cookie in headers['set-cookie']:
                cookparts = cookie.split(';')
                cook = cookparts[0].lstrip()
                t = cook.split('=', 1)
                if len(t) == 2: #Good cookie
                    goodcookies.append(cookie)
                    k, v = t                
                    self.cookies[k.lstrip()] = v.lstrip()
            if goodcookies:
                self.response_headers['set-cookie'] = goodcookies
            else:
                del self.response_headers['set-cookie']

