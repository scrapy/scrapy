"""
This module contains general purpose URL functions not found in the standard
library.
"""

import re
import urlparse
import urllib
import posixpath

def url_is_from_any_domain(url, domains):
    """Return True if the url belongs to the given domain"""
    host = urlparse.urlparse(url).hostname

    if host:
        return any(((host == d) or (host.endswith('.%s' % d)) for d in domains))
    else:
        return False

def url_is_from_spider(url, spider):
    """Return True if the url belongs to the given spider"""
    domains = [spider.domain_name] + spider.extra_domain_names
    return url_is_from_any_domain(url, domains)

def urljoin_rfc(base, ref):
    """
    Fixed urlparse.urljoin version that handles
    relative query string as RFC states.
    """
    if ref.startswith('?'):
        fpart = urlparse.urlsplit(str(base))[2].rsplit('/', 1)[-1]
        ref = ''.join([fpart, ref])
    # convert ref to a string. This should already
    # be the case, however, many spiders do not convert.
    return urlparse.urljoin(base, str(ref))


_reserved = ';/?:@&=+$|,#' # RFC 2396 (Generic Syntax)
_safe_chars = urllib.always_safe + '%' + _reserved

def safe_url_string(url, use_encoding='utf8'):
    """Convert a unicode (or utf8 string) object into a legal URL.

    Illegal characters are escaped.  See rfc3968.

    It is safe to call this function multiple times. Do not pass this
    function strings in encodings other than utf8.

    The use_encoding argument is the encoding to use to determine the numerical
    values in the escaping. For urls on html pages, you should use the original
    encoding of that page.

    html pages you should escape urls in the original encoding
    of the page and not using utf8.
    """
    s = url.encode(use_encoding)
    return urllib.quote(s,  _safe_chars)


_parent_dirs = re.compile(r'/?(\.\./)+')

def safe_download_url(url):
    """ Make a url for download. This will call safe_url_string
    and then strip the fragment, if one exists. The path will
    be normalised.

    If the path is outside the document root, it will be changed
    to be within the document root.
    """
    safe_url = safe_url_string(url)
    scheme, netloc, path, query, fragment = urlparse.urlsplit(safe_url)
    if path:
        path = _parent_dirs.sub('', posixpath.normpath(path))
        if url.endswith('/') and not path.endswith('/'):
            path += '/'
    else:
        path = '/'
    return urlparse.urlunsplit((scheme, netloc, path, query, ''))


def is_url(text):
    return text.partition("://")[0] in ('file', 'http', 'https')

