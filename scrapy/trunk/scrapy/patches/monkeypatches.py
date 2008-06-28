"""
Monkey patches

These are generally a bad idea.
"""
from twisted.web.client import HTTPClientFactory


# Extend limit for BeautifulSoup parsing loops
#import sys
#sys.setrecursionlimit(7400)

def apply_patches():
    patch_HTTPClientFactory_gotHeaders()


# XXX: Monkeypatch for twisted.web.client-HTTPClientFactory
# HTTPClientFactory.gotHeaders dies when parsing malformed cookies,
# and the crawler is getting malformed cookies from this site.
_old_gotHeaders = HTTPClientFactory.gotHeaders
# Cookies format: http://www.ietf.org/rfc/rfc2109.txt
# I have choosen not to filter based on this, so we don't filter invalid
# values that could be managed correctly by twisted.
#_COOKIES = re.compile(r'^[^=;]+=[^=;]*(;[^=;]+=[^=;])*$')

def _is_good_cookie(cookie):
    """ Check if a given cookie would make gotHeaders raise an exception """
    cookparts = cookie.split(';')
    cook = cookparts[0]
    return len(cook.split('=', 1)) == 2

def _new_gotHeaders(self, headers):
    """ Remove cookies that would make twisted raise an exception """
    if headers.has_key('set-cookie'):
        cookies = [cookie for cookie in headers['set-cookie']
                   if _is_good_cookie(cookie)]
        if cookies:
            headers['set-cookie'] = cookies
        else:
            del headers['set-cookie']

    return _old_gotHeaders(self, headers)

def patch_HTTPClientFactory_gotHeaders():
    setattr(HTTPClientFactory, 'gotHeaders', _new_gotHeaders)
