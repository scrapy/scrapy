"""
This module contains general purpose URL functions not found in the standard
library.
"""

import re
import urlparse
import urllib
import posixpath
import cgi

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
    """ Return the given query parameter in the url.
    For example:
    >>> url_query_parameter("product.html?id=200&foo=bar", "id")
    '200'
    >>> url_query_parameter("product.html?id=200&foo=bar", "notthere", "mydefault")
    'mydefault'
    >>> url_query_parameter("product.html?id=", "id")
    >>> url_query_parameter("product.html?id=", "id", keep_blank_values=1)
    ''
    """
    queryparams = cgi.parse_qs(urlparse.urlsplit(str(url))[3], keep_blank_values=keep_blank_values)
    return queryparams.get(parameter, [default])[0] 

def url_query_cleaner(url, parameterlist=None, sep='&', kvsep='='):
    """ Return the given url with given query parameters.
    >>> url_query_cleaner("product.html?id=200&foo=bar&name=wired", 'id')
    'product.html?id=200'
    >>> url_query_cleaner("product.html?id=200&foo=bar&name=wired", ['id', 'name'])
    'product.html?id=200&name=wired'
    """
    parameterlist = parameterlist or []
    if not isinstance(parameterlist, (list, tuple)):
        parameterlist = [parameterlist]
     
    try:
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
    
def _has_querystring(url):
    _, _, _, query, _ = urlparse.urlsplit(url)
    return bool(query)

def add_or_replace_parameter(url, name, new_value, sep='&'):
    """
    >>> url = 'http://domain/test'
    >>> add_or_replace_parameter(url, 'arg', 'v')
    'http://domain/test?arg=v'
    >>> url = 'http://domain/test?arg1=v1&arg2=v2&arg3=v3'
    >>> add_or_replace_parameter(url, 'arg4', 'v4')
    'http://domain/test?arg1=v1&arg2=v2&arg3=v3&arg4=v4'
    >>> add_or_replace_parameter(url, 'arg3', 'nv3')
    'http://domain/test?arg1=v1&arg2=v2&arg3=nv3'
    >>> url = 'http://domain/test?arg1=v1'
    >>> add_or_replace_parameter(url, 'arg2', 'v2', sep=';')
    'http://domain/test?arg1=v1;arg2=v2'
    >>> add_or_replace_parameter("http://domain/moreInfo.asp?prodID=", 'prodID', '20')
    'http://domain/moreInfo.asp?prodID=20'
    """
    parameter = url_query_parameter(url, name, keep_blank_values=1)
    if parameter is None:
        if _has_querystring(url):
            next_url = url + sep + name + '=' + new_value
        else:
            next_url = url + '?' + name + '=' + new_value
    else:
        next_url = url.replace(name+'='+parameter,
                               name+'='+new_value)
    return next_url
