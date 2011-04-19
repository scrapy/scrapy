"""
This module contains general purpose URL functions not found in the standard
library.

Some of the functions that used to be imported from this module have been moved
to the w3lib.url module. Always import those from there instead.
"""

import os
import re
import urlparse
import urllib
import posixpath
import cgi

from w3lib.url import *
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
