# -*- test-case-name: twisted.web.test.test_http_headers -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An API for storing HTTP header names and values.
"""

from __future__ import division, absolute_import

from twisted.python.compat import comparable, cmp, unicode


def _dashCapitalize(name):
    """
    Return a byte string which is capitalized using '-' as a word separator.

    @param name: The name of the header to capitalize.
    @type name: L{bytes}

    @return: The given header capitalized using '-' as a word separator.
    @rtype: L{bytes}
    """
    return b'-'.join([word.capitalize() for word in name.split(b'-')])



@comparable
class Headers(object):
    """
    Stores HTTP headers in a key and multiple value format.

    Most methods accept L{bytes} and L{unicode}, with an internal L{bytes}
    representation. When passed L{unicode}, header names (e.g. 'Content-Type')
    are encoded using ISO-8859-1 and header values (e.g.
    'text/html;charset=utf-8') are encoded using UTF-8. Some methods that return
    values will return them in the same type as the name given.

    If the header keys or values cannot be encoded or decoded using the rules
    above, using just L{bytes} arguments to the methods of this class will
    ensure no decoding or encoding is done, and L{Headers} will treat the keys
    and values as opaque byte strings.

    @cvar _caseMappings: A L{dict} that maps lowercase header names
        to their canonicalized representation.

    @ivar _rawHeaders: A L{dict} mapping header names as L{bytes} to L{list}s of
        header values as L{bytes}.
    """
    _caseMappings = {
        b'content-md5': b'Content-MD5',
        b'dnt': b'DNT',
        b'etag': b'ETag',
        b'p3p': b'P3P',
        b'te': b'TE',
        b'www-authenticate': b'WWW-Authenticate',
        b'x-xss-protection': b'X-XSS-Protection'}

    def __init__(self, rawHeaders=None):
        self._rawHeaders = {}
        if rawHeaders is not None:
            for name, values in rawHeaders.items():
                self.setRawHeaders(name, values)


    def __repr__(self):
        """
        Return a string fully describing the headers set on this object.
        """
        return '%s(%r)' % (self.__class__.__name__, self._rawHeaders,)


    def __cmp__(self, other):
        """
        Define L{Headers} instances as being equal to each other if they have
        the same raw headers.
        """
        if isinstance(other, Headers):
            return cmp(
                sorted(self._rawHeaders.items()),
                sorted(other._rawHeaders.items()))
        return NotImplemented


    def _encodeName(self, name):
        """
        Encode the name of a header (eg 'Content-Type') to an ISO-8859-1 encoded
        bytestring if required.

        @param name: A HTTP header name
        @type name: L{unicode} or L{bytes}

        @return: C{name}, encoded if required, lowercased
        @rtype: L{bytes}
        """
        if isinstance(name, unicode):
            return name.lower().encode('iso-8859-1')
        return name.lower()


    def _encodeValue(self, value):
        """
        Encode a single header value to a UTF-8 encoded bytestring if required.

        @param value: A single HTTP header value.
        @type value: L{bytes} or L{unicode}

        @return: C{value}, encoded if required
        @rtype: L{bytes}
        """
        if isinstance(value, unicode):
            return value.encode('utf8')
        return value


    def _encodeValues(self, values):
        """
        Encode a L{list} of header values to a L{list} of UTF-8 encoded
        bytestrings if required.

        @param values: A list of HTTP header values.
        @type values: L{list} of L{bytes} or L{unicode} (mixed types allowed)

        @return: C{values}, with each item encoded if required
        @rtype: L{list} of L{bytes}
        """
        newValues = []

        for value in values:
            newValues.append(self._encodeValue(value))
        return newValues


    def _decodeValues(self, values):
        """
        Decode a L{list} of header values into a L{list} of Unicode strings.

        @param values: A list of HTTP header values.
        @type values: L{list} of UTF-8 encoded L{bytes}

        @return: C{values}, with each item decoded
        @rtype: L{list} of L{unicode}
        """
        if type(values) is not list:
            return values

        newValues = []

        for value in values:
            newValues.append(value.decode('utf8'))
        return newValues


    def copy(self):
        """
        Return a copy of itself with the same headers set.

        @return: A new L{Headers}
        """
        return self.__class__(self._rawHeaders)


    def hasHeader(self, name):
        """
        Check for the existence of a given header.

        @type name: L{bytes} or L{unicode}
        @param name: The name of the HTTP header to check for.

        @rtype: L{bool}
        @return: C{True} if the header exists, otherwise C{False}.
        """
        return self._encodeName(name) in self._rawHeaders


    def removeHeader(self, name):
        """
        Remove the named header from this header object.

        @type name: L{bytes} or L{unicode}
        @param name: The name of the HTTP header to remove.

        @return: L{None}
        """
        self._rawHeaders.pop(self._encodeName(name), None)


    def setRawHeaders(self, name, values):
        """
        Sets the raw representation of the given header.

        @type name: L{bytes} or L{unicode}
        @param name: The name of the HTTP header to set the values for.

        @type values: L{list} of L{bytes} or L{unicode} strings
        @param values: A list of strings each one being a header value of
            the given name.

        @return: L{None}
        """
        if not isinstance(values, list):
            raise TypeError("Header entry %r should be list but found "
                            "instance of %r instead" % (name, type(values)))

        name = self._encodeName(name)
        self._rawHeaders[name] = self._encodeValues(values)


    def addRawHeader(self, name, value):
        """
        Add a new raw value for the given header.

        @type name: L{bytes} or L{unicode}
        @param name: The name of the header for which to set the value.

        @type value: L{bytes} or L{unicode}
        @param value: The value to set for the named header.
        """
        values = self.getRawHeaders(name)

        if values is not None:
            values.append(value)
        else:
            values = [value]

        self.setRawHeaders(name, values)


    def getRawHeaders(self, name, default=None):
        """
        Returns a list of headers matching the given name as the raw string
        given.

        @type name: L{bytes} or L{unicode}
        @param name: The name of the HTTP header to get the values of.

        @param default: The value to return if no header with the given C{name}
            exists.

        @rtype: L{list} of strings, same type as C{name}
        @return: A L{list} of values for the given header.
        """
        encodedName = self._encodeName(name)
        values = self._rawHeaders.get(encodedName, default)

        if isinstance(name, unicode):
            return self._decodeValues(values)
        return values


    def getAllRawHeaders(self):
        """
        Return an iterator of key, value pairs of all headers contained in this
        object, as L{bytes}.  The keys are capitalized in canonical
        capitalization.
        """
        for k, v in self._rawHeaders.items():
            yield self._canonicalNameCaps(k), v


    def _canonicalNameCaps(self, name):
        """
        Return the canonical name for the given header.

        @type name: L{bytes}
        @param name: The all-lowercase header name to capitalize in its
            canonical form.

        @rtype: L{bytes}
        @return: The canonical name of the header.
        """
        return self._caseMappings.get(name, _dashCapitalize(name))



__all__ = ['Headers']
