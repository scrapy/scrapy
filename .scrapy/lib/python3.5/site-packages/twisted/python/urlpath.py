# -*- test-case-name: twisted.python.test.test_urlpath -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
L{URLPath}, a representation of a URL.
"""

from __future__ import division, absolute_import

from twisted.python.compat import (
    nativeString, unicode, urllib_parse as urlparse, urlunquote, urlquote
)

from twisted.python.url import URL as _URL

_allascii = b"".join([chr(x).encode('ascii') for x in range(1, 128)])

def _rereconstituter(name):
    """
    Attriute declaration to preserve mutability on L{URLPath}.

    @param name: a public attribute name
    @type name: native L{str}

    @return: a descriptor which retrieves the private version of the attribute
        on get and calls rerealize on set.
    """
    privateName = nativeString("_") + name
    return property(
        lambda self: getattr(self, privateName),
        lambda self, value: (setattr(self, privateName,
                                     value if isinstance(value, bytes)
                                     else value.encode("charmap")) or
                             self._reconstitute())
    )



class URLPath(object):
    """
    A representation of a URL.

    @ivar scheme: The scheme of the URL (e.g. 'http').
    @type scheme: L{bytes}

    @ivar netloc: The network location ("host").
    @type netloc: L{bytes}

    @ivar path: The path on the network location.
    @type path: L{bytes}

    @ivar query: The query argument (the portion after ?  in the URL).
    @type query: L{bytes}

    @ivar fragment: The page fragment (the portion after # in the URL).
    @type fragment: L{bytes}
    """
    def __init__(self, scheme=b'', netloc=b'localhost', path=b'',
                 query=b'', fragment=b''):
        self._scheme = scheme or b'http'
        self._netloc = netloc
        self._path = path or b'/'
        self._query = query
        self._fragment = fragment
        self._reconstitute()


    def _reconstitute(self):
        """
        Reconstitute this L{URLPath} from all its given attributes.
        """
        urltext = urlquote(
            urlparse.urlunsplit((self._scheme, self._netloc,
                                 self._path, self._query, self._fragment)),
            safe=_allascii
        )
        self._url = _URL.fromText(urltext.encode("ascii").decode("ascii"))

    scheme   = _rereconstituter("scheme")
    netloc   = _rereconstituter("netloc")
    path     = _rereconstituter("path")
    query    = _rereconstituter("query")
    fragment = _rereconstituter("fragment")


    @classmethod
    def _fromURL(cls, urlInstance):
        """
        Reconstruct all the public instance variables of this L{URLPath} from
        its underlying L{_URL}.

        @param urlInstance: the object to base this L{URLPath} on.
        @type urlInstance: L{_URL}

        @return: a new L{URLPath}
        """
        self = cls.__new__(cls)
        self._url = urlInstance.replace(path=urlInstance.path or [u""])
        self._scheme = self._url.scheme.encode("ascii")
        self._netloc = self._url.authority().encode("ascii")
        self._path = (_URL(path=self._url.path,
                           rooted=True).asURI().asText()
                      .encode("ascii"))
        self._query = (_URL(query=self._url.query).asURI().asText()
                       .encode("ascii"))[1:]
        self._fragment = self._url.fragment.encode("ascii")
        return self


    def pathList(self, unquote=False, copy=True):
        """
        Split this URL's path into its components.

        @param unquote: whether to remove %-encoding from the returned strings.

        @param copy: (ignored, do not use)

        @return: The components of C{self.path}
        @rtype: L{list} of L{bytes}
        """
        segments = self._url.path
        mapper = lambda x: x.encode("ascii")
        if unquote:
            mapper = (lambda x, m=mapper: m(urlunquote(x)))
        return [b''] + [mapper(segment) for segment in segments]


    @classmethod
    def fromString(klass, url):
        """
        Make a L{URLPath} from a L{str} or L{unicode}.

        @param url: A L{str} representation of a URL.
        @type url: L{str} or L{unicode}.

        @return: a new L{URLPath} derived from the given string.
        @rtype: L{URLPath}
        """
        if not isinstance(url, (str, unicode)):
            raise ValueError("'url' must be a str or unicode")
        if isinstance(url, bytes):
            # On Python 2, accepting 'str' (for compatibility) means we might
            # get 'bytes'.  On py3, this will not work with bytes due to the
            # check above.
            return klass.fromBytes(url)
        return klass._fromURL(_URL.fromText(url))


    @classmethod
    def fromBytes(klass, url):
        """
        Make a L{URLPath} from a L{bytes}.

        @param url: A L{bytes} representation of a URL.
        @type url: L{bytes}

        @return: a new L{URLPath} derived from the given L{bytes}.
        @rtype: L{URLPath}

        @since: 15.4
        """
        if not isinstance(url, bytes):
            raise ValueError("'url' must be bytes")
        quoted = urlquote(url, safe=_allascii)
        if isinstance(quoted, bytes):
            # This will only be bytes on python 2, where we can transform it
            # into unicode.  On python 3, urlquote always returns str.
            quoted = quoted.decode("ascii")
        return klass.fromString(quoted)


    @classmethod
    def fromRequest(klass, request):
        """
        Make a L{URLPath} from a L{twisted.web.http.Request}.

        @param request: A L{twisted.web.http.Request} to make the L{URLPath}
            from.

        @return: a new L{URLPath} derived from the given request.
        @rtype: L{URLPath}
        """
        return klass.fromBytes(request.prePathURL())


    def _mod(self, newURL, keepQuery):
        """
        Return a modified copy of C{self} using C{newURL}, keeping the query
        string if C{keepQuery} is C{True}.

        @param newURL: a L{URL} to derive a new L{URLPath} from
        @type newURL: L{URL}

        @param keepQuery: if C{True}, preserve the query parameters from
            C{self} on the new L{URLPath}; if C{False}, give the new L{URLPath}
            no query parameters.
        @type keepQuery: L{bool}

        @return: a new L{URLPath}
        """
        return self._fromURL(newURL.replace(
            fragment=u'', query=self._url.query if keepQuery else ()
        ))


    def sibling(self, path, keepQuery=False):
        """
        Get the sibling of the current L{URLPath}.  A sibling is a file which
        is in the same directory as the current file.

        @param path: The path of the sibling.
        @type path: L{bytes}

        @param keepQuery: Whether to keep the query parameters on the returned
            L{URLPath}.
        @type: keepQuery: L{bool}

        @return: a new L{URLPath}
        """
        return self._mod(self._url.sibling(path.decode("ascii")), keepQuery)


    def child(self, path, keepQuery=False):
        """
        Get the child of this L{URLPath}.

        @param path: The path of the child.
        @type path: L{bytes}

        @param keepQuery: Whether to keep the query parameters on the returned
            L{URLPath}.
        @type: keepQuery: L{bool}

        @return: a new L{URLPath}
        """
        return self._mod(self._url.child(path.decode("ascii")), keepQuery)


    def parent(self, keepQuery=False):
        """
        Get the parent directory of this L{URLPath}.

        @param keepQuery: Whether to keep the query parameters on the returned
            L{URLPath}.
        @type: keepQuery: L{bool}

        @return: a new L{URLPath}
        """
        return self._mod(self._url.click(u".."), keepQuery)


    def here(self, keepQuery=False):
        """
        Get the current directory of this L{URLPath}.

        @param keepQuery: Whether to keep the query parameters on the returned
            L{URLPath}.
        @type: keepQuery: L{bool}

        @return: a new L{URLPath}
        """
        return self._mod(self._url.click(u"."), keepQuery)


    def click(self, st):
        """
        Return a path which is the URL where a browser would presumably take
        you if you clicked on a link with an HREF as given.

        @param st: A relative URL, to be interpreted relative to C{self} as the
            base URL.
        @type st: L{bytes}

        @return: a new L{URLPath}
        """
        return self._fromURL(self._url.click(st.decode("ascii")))


    def __str__(self):
        """
        The L{str} of a L{URLPath} is its URL text.
        """
        return nativeString(self._url.asURI().asText())


    def __repr__(self):
        """
        The L{repr} of a L{URLPath} is an eval-able expression which will
        construct a similar L{URLPath}.
        """
        return ('URLPath(scheme=%r, netloc=%r, path=%r, query=%r, fragment=%r)'
                % (self.scheme, self.netloc, self.path, self.query,
                   self.fragment))
