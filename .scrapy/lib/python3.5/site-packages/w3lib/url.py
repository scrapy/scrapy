"""
This module contains general purpose URL functions not found in the standard
library.
"""
import codecs
import os
import re
import posixpath
import warnings
import six
from six.moves.urllib.parse import (urljoin, urlsplit, urlunsplit,
                                    urldefrag, urlencode, urlparse,
                                    quote, parse_qs, parse_qsl,
                                    ParseResult, unquote, urlunparse)
from six.moves.urllib.request import pathname2url, url2pathname
from w3lib.util import to_bytes, to_native_str, to_unicode


# error handling function for bytes-to-Unicode decoding errors with URLs
def _quote_byte(error):
    return (to_unicode(quote(error.object[error.start:error.end])), error.end)

codecs.register_error('percentencode', _quote_byte)


# Python 2.x urllib.always_safe become private in Python 3.x;
# its content is copied here
_ALWAYS_SAFE_BYTES = (b'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                      b'abcdefghijklmnopqrstuvwxyz'
                      b'0123456789' b'_.-')


def urljoin_rfc(base, ref, encoding='utf-8'):
    r"""
    .. warning::

        This function is deprecated and will be removed in future.
        It is not supported with Python 3.
        Please use ``urlparse.urljoin`` instead.

    Same as urlparse.urljoin but supports unicode values in base and ref
    parameters (in which case they will be converted to str using the given
    encoding).

    Always returns a str.

    >>> import w3lib.url
    >>> w3lib.url.urljoin_rfc('http://www.example.com/path/index.html', u'/otherpath/index2.html')
    'http://www.example.com/otherpath/index2.html'
    >>>

    >>> # Note: the following does not work in Python 3
    >>> w3lib.url.urljoin_rfc(b'http://www.example.com/path/index.html', u'fran\u00e7ais/d\u00e9part.htm') # doctest: +SKIP
    'http://www.example.com/path/fran\xc3\xa7ais/d\xc3\xa9part.htm'
    >>>


    """

    warnings.warn("w3lib.url.urljoin_rfc is deprecated, use urlparse.urljoin instead",
        DeprecationWarning)

    str_base = to_bytes(base, encoding)
    str_ref = to_bytes(ref, encoding)
    return urljoin(str_base, str_ref)

_reserved = b';/?:@&=+$|,#' # RFC 3986 (Generic Syntax)
_unreserved_marks = b"-_.!~*'()" # RFC 3986 sec 2.3
_safe_chars = _ALWAYS_SAFE_BYTES + b'%' + _reserved + _unreserved_marks

def safe_url_string(url, encoding='utf8', path_encoding='utf8'):
    """Convert the given URL into a legal URL by escaping unsafe characters
    according to RFC-3986.

    If a bytes URL is given, it is first converted to `str` using the given
    encoding (which defaults to 'utf-8'). 'utf-8' encoding is used for
    URL path component (unless overriden by path_encoding), and given
    encoding is used for query string or form data.
    When passing an encoding, you should use the encoding of the
    original page (the page from which the URL was extracted from).

    Calling this function on an already "safe" URL will return the URL
    unmodified.

    Always returns a native `str` (bytes in Python2, unicode in Python3).
    """
    # Python3's urlsplit() chokes on bytes input with non-ASCII chars,
    # so let's decode (to Unicode) using page encoding:
    #   - it is assumed that a raw bytes input comes from a document
    #     encoded with the supplied encoding (or UTF8 by default)
    #   - if the supplied (or default) encoding chokes,
    #     percent-encode offending bytes
    parts = urlsplit(to_unicode(url, encoding=encoding,
                                errors='percentencode'))

    # IDNA encoding can fail for too long labels (>63 characters)
    # or missing labels (e.g. http://.example.com)
    try:
        netloc = parts.netloc.encode('idna')
    except UnicodeError:
        netloc = parts.netloc

    # quote() in Python2 return type follows input type;
    # quote() in Python3 always returns Unicode (native str)
    return urlunsplit((
        to_native_str(parts.scheme),
        to_native_str(netloc),

        # default encoding for path component SHOULD be UTF-8
        quote(to_bytes(parts.path, path_encoding), _safe_chars),

        # encoding of query and fragment follows page encoding
        # or form-charset (if known and passed)
        quote(to_bytes(parts.query, encoding), _safe_chars),
        quote(to_bytes(parts.fragment, encoding), _safe_chars),
    ))

_parent_dirs = re.compile(r'/?(\.\./)+')

def safe_download_url(url):
    """ Make a url for download. This will call safe_url_string
    and then strip the fragment, if one exists. The path will
    be normalised.

    If the path is outside the document root, it will be changed
    to be within the document root.
    """
    safe_url = safe_url_string(url)
    scheme, netloc, path, query, _ = urlsplit(safe_url)
    if path:
        path = _parent_dirs.sub('', posixpath.normpath(path))
        if url.endswith('/') and not path.endswith('/'):
            path += '/'
    else:
        path = '/'
    return urlunsplit((scheme, netloc, path, query, ''))

def is_url(text):
    return text.partition("://")[0] in ('file', 'http', 'https')

def url_query_parameter(url, parameter, default=None, keep_blank_values=0):
    """Return the value of a url parameter, given the url and parameter name

    General case:

    >>> import w3lib.url
    >>> w3lib.url.url_query_parameter("product.html?id=200&foo=bar", "id")
    '200'
    >>>

    Return a default value if the parameter is not found:

    >>> w3lib.url.url_query_parameter("product.html?id=200&foo=bar", "notthere", "mydefault")
    'mydefault'
    >>>

    Returns None if `keep_blank_values` not set or 0 (default):

    >>> w3lib.url.url_query_parameter("product.html?id=", "id")
    >>>

    Returns an empty string if `keep_blank_values` set to 1:

    >>> w3lib.url.url_query_parameter("product.html?id=", "id", keep_blank_values=1)
    ''
    >>>

    """

    queryparams = parse_qs(
        urlsplit(str(url))[3],
        keep_blank_values=keep_blank_values
    )
    return queryparams.get(parameter, [default])[0]

def url_query_cleaner(url, parameterlist=(), sep='&', kvsep='=', remove=False, unique=True):
    """Clean URL arguments leaving only those passed in the parameterlist keeping order

    >>> import w3lib.url
    >>> w3lib.url.url_query_cleaner("product.html?id=200&foo=bar&name=wired", ('id',))
    'product.html?id=200'
    >>> w3lib.url.url_query_cleaner("product.html?id=200&foo=bar&name=wired", ['id', 'name'])
    'product.html?id=200&name=wired'
    >>>

    If `unique` is ``False``, do not remove duplicated keys

    >>> w3lib.url.url_query_cleaner("product.html?d=1&e=b&d=2&d=3&other=other", ['d'], unique=False)
    'product.html?d=1&d=2&d=3'
    >>>

    If `remove` is ``True``, leave only those **not in parameterlist**.

    >>> w3lib.url.url_query_cleaner("product.html?id=200&foo=bar&name=wired", ['id'], remove=True)
    'product.html?foo=bar&name=wired'
    >>> w3lib.url.url_query_cleaner("product.html?id=2&foo=bar&name=wired", ['id', 'foo'], remove=True)
    'product.html?name=wired'
    >>>

    """

    if isinstance(parameterlist, (six.text_type, bytes)):
        parameterlist = [parameterlist]
    url = urldefrag(url)[0]
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

def add_or_replace_parameter(url, name, new_value):
    """Add or remove a parameter to a given url

    >>> import w3lib.url
    >>> w3lib.url.add_or_replace_parameter('http://www.example.com/index.php', 'arg', 'v')
    'http://www.example.com/index.php?arg=v'
    >>> w3lib.url.add_or_replace_parameter('http://www.example.com/index.php?arg1=v1&arg2=v2&arg3=v3', 'arg4', 'v4')
    'http://www.example.com/index.php?arg1=v1&arg2=v2&arg3=v3&arg4=v4'
    >>> w3lib.url.add_or_replace_parameter('http://www.example.com/index.php?arg1=v1&arg2=v2&arg3=v3', 'arg3', 'v3new')
    'http://www.example.com/index.php?arg1=v1&arg2=v2&arg3=v3new'
    >>>

    """
    parsed = urlsplit(url)
    args = parse_qsl(parsed.query, keep_blank_values=True)

    new_args = []
    found = False
    for name_, value_ in args:
        if name_ == name:
            new_args.append((name_, new_value))
            found = True
        else:
            new_args.append((name_, value_))

    if not found:
        new_args.append((name, new_value))

    query = urlencode(new_args)
    return urlunsplit(parsed._replace(query=query))


def path_to_file_uri(path):
    """Convert local filesystem path to legal File URIs as described in:
    http://en.wikipedia.org/wiki/File_URI_scheme
    """
    x = pathname2url(os.path.abspath(path))
    if os.name == 'nt':
        x = x.replace('|', ':') # http://bugs.python.org/issue5861
    return 'file:///%s' % x.lstrip('/')

def file_uri_to_path(uri):
    """Convert File URI to local filesystem path according to:
    http://en.wikipedia.org/wiki/File_URI_scheme
    """
    uri_path = urlparse(uri).path
    return url2pathname(uri_path)

def any_to_uri(uri_or_path):
    """If given a path name, return its File URI, otherwise return it
    unmodified
    """
    if os.path.splitdrive(uri_or_path)[0]:
        return path_to_file_uri(uri_or_path)
    u = urlparse(uri_or_path)
    return uri_or_path if u.scheme else path_to_file_uri(uri_or_path)


__all__ = ["add_or_replace_parameter",
           "any_to_uri",
           "canonicalize_url",
           "file_uri_to_path",
           "is_url",
           "path_to_file_uri",
           "safe_download_url",
           "safe_url_string",
           "url_query_cleaner",
           "url_query_parameter",

           # this last one is deprecated ; include it to be on the safe side
           "urljoin_rfc"]


def _safe_ParseResult(parts, encoding='utf8', path_encoding='utf8'):
    # IDNA encoding can fail for too long labels (>63 characters)
    # or missing labels (e.g. http://.example.com)
    try:
        netloc = parts.netloc.encode('idna')
    except UnicodeError:
        netloc = parts.netloc

    return (
        to_native_str(parts.scheme),
        to_native_str(netloc),

        # default encoding for path component SHOULD be UTF-8
        quote(to_bytes(parts.path, path_encoding), _safe_chars),
        quote(to_bytes(parts.params, path_encoding), _safe_chars),

        # encoding of query and fragment follows page encoding
        # or form-charset (if known and passed)
        quote(to_bytes(parts.query, encoding), _safe_chars),
        quote(to_bytes(parts.fragment, encoding), _safe_chars)
    )


def canonicalize_url(url, keep_blank_values=True, keep_fragments=False,
                     encoding=None):
    r"""Canonicalize the given url by applying the following procedures:

    - sort query arguments, first by key, then by value
    - percent encode paths ; non-ASCII characters are percent-encoded
      using UTF-8 (RFC-3986)
    - percent encode query arguments ; non-ASCII characters are percent-encoded
      using passed `encoding` (UTF-8 by default)
    - normalize all spaces (in query arguments) '+' (plus symbol)
    - normalize percent encodings case (%2f -> %2F)
    - remove query arguments with blank values (unless `keep_blank_values` is True)
    - remove fragments (unless `keep_fragments` is True)

    The url passed can be bytes or unicode, while the url returned is
    always a native str (bytes in Python 2, unicode in Python 3).

    >>> import w3lib.url
    >>>
    >>> # sorting query arguments
    >>> w3lib.url.canonicalize_url('http://www.example.com/do?c=3&b=5&b=2&a=50')
    'http://www.example.com/do?a=50&b=2&b=5&c=3'
    >>>
    >>> # UTF-8 conversion + percent-encoding of non-ASCII characters
    >>> w3lib.url.canonicalize_url(u'http://www.example.com/r\u00e9sum\u00e9')
    'http://www.example.com/r%C3%A9sum%C3%A9'
    >>>

    For more examples, see the tests in `tests/test_url.py`.
    """
    # If supplied `encoding` is not compatible with all characters in `url`,
    # fallback to UTF-8 as safety net.
    # UTF-8 can handle all Unicode characters,
    # so we should be covered regarding URL normalization,
    # if not for proper URL expected by remote website.
    try:
        scheme, netloc, path, params, query, fragment = _safe_ParseResult(
            parse_url(url), encoding=encoding)
    except UnicodeEncodeError as e:
        scheme, netloc, path, params, query, fragment = _safe_ParseResult(
            parse_url(url), encoding='utf8')

    # 1. decode query-string as UTF-8 (or keep raw bytes),
    #    sort values,
    #    and percent-encode them back
    if six.PY2:
        keyvals = parse_qsl(query, keep_blank_values)
    else:
        # Python3's urllib.parse.parse_qsl does not work as wanted
        # for percent-encoded characters that do not match passed encoding,
        # they get lost.
        #
        # e.g., 'q=b%a3' becomes [('q', 'b\ufffd')]
        # (ie. with 'REPLACEMENT CHARACTER' (U+FFFD),
        #      instead of \xa3 that you get with Python2's parse_qsl)
        #
        # what we want here is to keep raw bytes, and percent encode them
        # so as to preserve whatever encoding what originally used.
        #
        # See https://tools.ietf.org/html/rfc3987#section-6.4:
        #
        # For example, it is possible to have a URI reference of
        # "http://www.example.org/r%E9sum%E9.xml#r%C3%A9sum%C3%A9", where the
        # document name is encoded in iso-8859-1 based on server settings, but
        # where the fragment identifier is encoded in UTF-8 according to
        # [XPointer]. The IRI corresponding to the above URI would be (in XML
        # notation)
        # "http://www.example.org/r%E9sum%E9.xml#r&#xE9;sum&#xE9;".
        # Similar considerations apply to query parts.  The functionality of
        # IRIs (namely, to be able to include non-ASCII characters) can only be
        # used if the query part is encoded in UTF-8.
        keyvals = parse_qsl_to_bytes(query, keep_blank_values)
    keyvals.sort()
    query = urlencode(keyvals)

    # 2. decode percent-encoded sequences in path as UTF-8 (or keep raw bytes)
    #    and percent-encode path again (this normalizes to upper-case %XX)
    uqp = _unquotepath(path)
    path = quote(uqp, _safe_chars) or '/'

    fragment = '' if not keep_fragments else fragment

    # every part should be safe already
    return urlunparse((scheme, netloc.lower(), path, params, query, fragment))


def _unquotepath(path):
    for reserved in ('2f', '2F', '3f', '3F'):
        path = path.replace('%' + reserved, '%25' + reserved.upper())

    if six.PY2:
        # in Python 2, '%a3' becomes '\xa3', which is what we want
        return unquote(path)
    else:
        # in Python 3,
        # standard lib's unquote() does not work for non-UTF-8
        # percent-escaped characters, they get lost.
        # e.g., '%a3' becomes 'REPLACEMENT CHARACTER' (U+FFFD)
        #
        # unquote_to_bytes() returns raw bytes instead
        return unquote_to_bytes(path)


def parse_url(url, encoding=None):
    """Return urlparsed url from the given argument (which could be an already
    parsed url)
    """
    if isinstance(url, ParseResult):
        return url
    return urlparse(to_unicode(url, encoding))


if not six.PY2:
    from urllib.parse import _coerce_args, unquote_to_bytes

    def parse_qsl_to_bytes(qs, keep_blank_values=False):
        """Parse a query given as a string argument.

        Data are returned as a list of name, value pairs as bytes.

        Arguments:

        qs: percent-encoded query string to be parsed

        keep_blank_values: flag indicating whether blank values in
            percent-encoded queries should be treated as blank strings.  A
            true value indicates that blanks should be retained as blank
            strings.  The default false value indicates that blank values
            are to be ignored and treated as if they were  not included.

        """
        # This code is the same as Python3's parse_qsl()
        # (at https://hg.python.org/cpython/rev/c38ac7ab8d9a)
        # except for the unquote(s, encoding, errors) calls replaced
        # with unquote_to_bytes(s)
        qs, _coerce_result = _coerce_args(qs)
        pairs = [s2 for s1 in qs.split('&') for s2 in s1.split(';')]
        r = []
        for name_value in pairs:
            if not name_value:
                continue
            nv = name_value.split('=', 1)
            if len(nv) != 2:
                # Handle case of a control-name with no equal sign
                if keep_blank_values:
                    nv.append('')
                else:
                    continue
            if len(nv[1]) or keep_blank_values:
                name = nv[0].replace('+', ' ')
                name = unquote_to_bytes(name)
                name = _coerce_result(name)
                value = nv[1].replace('+', ' ')
                value = unquote_to_bytes(value)
                value = _coerce_result(value)
                r.append((name, value))
        return r
