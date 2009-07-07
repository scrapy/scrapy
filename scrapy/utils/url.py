"""
This module contains general purpose URL functions not found in the standard
library.
"""

import re
import urlparse
import urllib
import posixpath
import cgi

from scrapy.utils.python import unicode_to_str

def url_is_from_any_domain(url, domains):
    """Return True if the url belongs to the given domain"""
    host = urlparse.urlparse(url).hostname

    if host:
        return any(((host == d) or (host.endswith('.%s' % d)) for d in domains))
    else:
        return False

def url_is_from_spider(url, spider):
    """Return True if the url belongs to the given spider"""
    domains = [spider.domain_name]
    domains.extend(spider.extra_domain_names)
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
_unreserved_marks = "-_.!~*'()" #RFC 2396 sec 2.3
_safe_chars = urllib.always_safe + '%' + _reserved + _unreserved_marks

def safe_url_string(url, use_encoding='utf8'):
    """Convert a unicode object (using 'use_encoding' as the encoding), or an already
    encoded string into a legal URL.

    Illegal characters are escaped (RFC-3986)

    It is safe to call this function multiple times.

    The use_encoding argument is the encoding to use to determine the numerical
    values in the escaping. For urls on html pages, you should use the original
    encoding of that page.
    """
    s = unicode_to_str(url, use_encoding)
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
    scheme, netloc, path, query, _ = urlparse.urlsplit(safe_url)
    if path:
        path = _parent_dirs.sub('', posixpath.normpath(path))
        if url.endswith('/') and not path.endswith('/'):
            path += '/'
    else:
        path = '/'
    return urlparse.urlunsplit((scheme, netloc, path, query, ''))

def is_url(text):
    return text.partition("://")[0] in ('file', 'http', 'https')

def url_query_parameter(url, parameter, default=None, keep_blank_values=0):
    """Return the value of a url parameter, given the url and parameter name"""
    queryparams = cgi.parse_qs(urlparse.urlsplit(str(url))[3], keep_blank_values=keep_blank_values)
    result = queryparams.get(parameter, [default])[0]
    return result

def url_query_cleaner(url, parameterlist=(), sep='&', kvsep='='):
    """Clean url arguments leaving only those passed in the parameterlist"""
    try:
        url = urlparse.urldefrag(url)[0]
        base, query = url.split('?', 1)
        parameters = [pair.split(kvsep, 1) for pair in query.split(sep)]
    except:
        base = url
        query = ""
        parameters = []

    # unique parameters while keeping order
    unique = {}
    querylist = []
    for pair in parameters:
        k = pair[0]
        if not unique.get(k):
            querylist += [pair]
            unique[k] = 1

    query = sep.join([kvsep.join(pair) for pair in querylist if pair[0] in parameterlist])
    return '?'.join([base, query])

def add_or_replace_parameter(url, name, new_value, sep='&', url_is_quoted=False):
    """Add or remove a parameter to a given url"""
    def has_querystring(url):
        _, _, _, query, _ = urlparse.urlsplit(url)
        return bool(query)

    parameter = url_query_parameter(url, name, keep_blank_values=1)
    if url_is_quoted:
        parameter = urllib.quote(parameter)
    if parameter is None:
        if has_querystring(url):
            next_url = url + sep + name + '=' + new_value
        else:
            next_url = url + '?' + name + '=' + new_value
    else:
        next_url = url.replace(name+'='+parameter,
                               name+'='+new_value)
    return next_url

def canonicalize_url(url, keep_blank_values=True, keep_fragments=False):
    """Canonicalize the given url by applying the following procedures:

    - sort query arguments, first by key, then by value
    - percent encode paths and query arguments. non-ASCII characters are
      percent-encoded using UTF-8 (RFC-3986)
    - normalize all spaces (in query arguments) '+' (plus symbol)
    - normalize percent encodings case (%2f -> %2F)
    - remove query arguments with blank values (unless keep_blank_values is True)
    - remove fragments (unless keep_fragments is True)

    The url passed can be a str or unicode, while the url returned is always a
    str.

    For examples see the tests in scrapy.tests.test_utils_url
    """

    url = unicode_to_str(url)
    scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
    keyvals = cgi.parse_qsl(query, keep_blank_values)
    keyvals.sort()
    query = urllib.urlencode(keyvals)
    path = urllib.quote(urllib.unquote(path))
    fragment = '' if not keep_fragments else fragment
    return urlparse.urlunparse((scheme, netloc, path, params, query, fragment))
