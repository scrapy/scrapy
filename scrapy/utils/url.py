"""
This module contains general purpose URL functions not found in the standard
library.
"""

import os
import re
import urlparse
import urllib
import posixpath
import cgi

from scrapy.utils.python import unicode_to_str

def url_is_from_any_domain(url, domains):
    """Return True if the url belongs to any of the given domains"""
    host = urlparse.urlparse(url).hostname

    if host:
        return any(((host == d) or (host.endswith('.%s' % d)) for d in domains))
    else:
        return False

def url_is_from_spider(url, spider):
    """Return True if the url belongs to the given spider"""
    return url_is_from_any_domain(url, [spider.name] + \
        getattr(spider, 'allowed_domains', []))

def urljoin_rfc(base, ref, encoding='utf-8'):
    """Same as urlparse.urljoin but supports unicode values in base and ref
    parameters (in which case they will be converted to str using the given
    encoding).

    Always returns a str.
    """
    return urlparse.urljoin(unicode_to_str(base, encoding), \
        unicode_to_str(ref, encoding))

_reserved = ';/?:@&=+$|,#' # RFC 3986 (Generic Syntax)
_unreserved_marks = "-_.!~*'()" # RFC 3986 sec 2.3
_safe_chars = urllib.always_safe + '%' + _reserved + _unreserved_marks

def safe_url_string(url, encoding='utf8'):
    """Convert the given url into a legal URL by escaping unsafe characters
    according to RFC-3986.

    If a unicode url is given, it is first converted to str using the given
    encoding (which defaults to 'utf-8'). When passing a encoding, you should
    use the encoding of the original page (the page from which the url was
    extracted from).

    Calling this function on an already "safe" url will return the url
    unmodified.

    Always returns a str.
    """
    s = unicode_to_str(url, encoding)
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
    queryparams = cgi.parse_qs(urlparse.urlsplit(str(url))[3], \
        keep_blank_values=keep_blank_values)
    return queryparams.get(parameter, [default])[0]

def url_query_cleaner(url, parameterlist=(), sep='&', kvsep='=', remove=False, unique=True):
    """Clean url arguments leaving only those passed in the parameterlist keeping order

    If remove is True, leave only those not in parameterlist.
    If unique is False, do not remove duplicated keys
    """
    url = urlparse.urldefrag(url)[0]
    base, _, query = url.partition('?')
    seen = set()
    querylist = []
    for ksv in query.split(sep):
        k, _, _ = ksv.partition(kvsep)
        if unique and k in seen:
            continue
        elif remove and k in parameterlist:
            continue
        elif not remove and k not in parameterlist:
            continue
        else:
            querylist.append(ksv)
            seen.add(k)
    return '?'.join([base, sep.join(querylist)]) if querylist else base

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

def canonicalize_url(url, keep_blank_values=True, keep_fragments=False, \
        encoding=None):
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

    url = unicode_to_str(url, encoding)
    scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
    keyvals = cgi.parse_qsl(query, keep_blank_values)
    keyvals.sort()
    query = urllib.urlencode(keyvals)
    path = safe_url_string(urllib.unquote(path))
    fragment = '' if not keep_fragments else fragment
    return urlparse.urlunparse((scheme, netloc.lower(), path, params, query, fragment))

def path_to_file_uri(path):
    """Convert local filesystem path to legal File URIs as described in:
    http://en.wikipedia.org/wiki/File_URI_scheme
    """
    x = urllib.pathname2url(os.path.abspath(path))
    if os.name == 'nt':
        x = x.replace('|', ':') # http://bugs.python.org/issue5861
    return 'file:///%s' % x.lstrip('/')

def file_uri_to_path(uri):
    """Convert File URI to local filesystem path according to:
    http://en.wikipedia.org/wiki/File_URI_scheme
    """
    return urllib.url2pathname(urlparse.urlparse(uri).path)

def any_to_uri(uri_or_path):
    """If given a path name, return its File URI, otherwise return it
    unmodified
    """
    if os.path.splitdrive(uri_or_path)[0]:
        return path_to_file_uri(uri_or_path)
    u = urlparse.urlparse(uri_or_path)
    return uri_or_path if u.scheme else path_to_file_uri(uri_or_path)
