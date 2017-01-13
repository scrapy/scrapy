# -*- test-case-name: twisted.web.test.test_error -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Exception definitions for L{twisted.web}.
"""

from __future__ import division, absolute_import
try:
    from future_builtins import ascii
except ImportError:
    pass

__all__ = [
    'Error', 'PageRedirect', 'InfiniteRedirection', 'RenderError',
    'MissingRenderMethod', 'MissingTemplateLoader', 'UnexposedMethodError',
    'UnfilledSlot', 'UnsupportedType', 'FlattenerError',
    'RedirectWithNoLocation',
    ]

from collections import Sequence

from twisted.web._responses import RESPONSES
from twisted.python.compat import unicode, nativeString, intToBytes


def _codeToMessage(code):
    """
    Returns the response message corresponding to an HTTP code, or None
    if the code is unknown or unrecognized.

    @type code: L{bytes}
    @param code: Refers to an HTTP status code, for example C{http.NOT_FOUND}.

    @return: A string message or none
    @rtype: L{bytes}
    """
    try:
        return RESPONSES.get(int(code))
    except (ValueError, AttributeError):
        return None


class Error(Exception):
    """
    A basic HTTP error.

    @type status: L{bytes}
    @ivar status: Refers to an HTTP status code, for example C{http.NOT_FOUND}.

    @type message: L{bytes}
    @param message: A short error message, for example "NOT FOUND".

    @type response: L{bytes}
    @ivar response: A complete HTML document for an error page.
    """
    def __init__(self, code, message=None, response=None):
        """
        Initializes a basic exception.

        @type code: L{bytes} or L{int}
        @param code: Refers to an HTTP status code (for example, 200) either as
            an integer or a bytestring representing such. If no C{message} is
            given, C{code} is mapped to a descriptive bytestring that is used
            instead.

        @type message: L{bytes}
        @param message: A short error message, for example "NOT FOUND".

        @type response: L{bytes}
        @param response: A complete HTML document for an error page.
        """
        message = message or _codeToMessage(code)

        Exception.__init__(self, code, message, response)

        if isinstance(code, int):
            # If we're given an int, convert it to a bytestring
            # downloadPage gives a bytes, Agent gives an int, and it worked by
            # accident previously, so just make it keep working.
            code = intToBytes(code)

        self.status = code
        self.message = message
        self.response = response


    def __str__(self):
        return nativeString(self.status + b" " + self.message)



class PageRedirect(Error):
    """
    A request resulted in an HTTP redirect.

    @type location: L{bytes}
    @ivar location: The location of the redirect which was not followed.
    """
    def __init__(self, code, message=None, response=None, location=None):
        """
        Initializes a page redirect exception.

        @type code: L{bytes}
        @param code: Refers to an HTTP status code, for example
            C{http.NOT_FOUND}. If no C{message} is given, C{code} is mapped to a
            descriptive string that is used instead.

        @type message: L{bytes}
        @param message: A short error message, for example "NOT FOUND".

        @type response: L{bytes}
        @param response: A complete HTML document for an error page.

        @type location: L{bytes}
        @param location: The location response-header field value. It is an
            absolute URI used to redirect the receiver to a location other than
            the Request-URI so the request can be completed.
        """
        Error.__init__(self, code, message, response)
        if self.message and location:
            self.message = self.message + b" to " + location
        self.location = location



class InfiniteRedirection(Error):
    """
    HTTP redirection is occurring endlessly.

    @type location: L{bytes}
    @ivar location: The first URL in the series of redirections which was
        not followed.
    """
    def __init__(self, code, message=None, response=None, location=None):
        """
        Initializes an infinite redirection exception.

        @type code: L{bytes}
        @param code: Refers to an HTTP status code, for example
            C{http.NOT_FOUND}. If no C{message} is given, C{code} is mapped to a
            descriptive string that is used instead.

        @type message: L{bytes}
        @param message: A short error message, for example "NOT FOUND".

        @type response: L{bytes}
        @param response: A complete HTML document for an error page.

        @type location: L{bytes}
        @param location: The location response-header field value. It is an
            absolute URI used to redirect the receiver to a location other than
            the Request-URI so the request can be completed.
        """
        Error.__init__(self, code, message, response)
        if self.message and location:
            self.message = self.message + b" to " + location
        self.location = location



class RedirectWithNoLocation(Error):
    """
    Exception passed to L{ResponseFailed} if we got a redirect without a
    C{Location} header field.

    @type uri: L{bytes}
    @ivar uri: The URI which failed to give a proper location header
        field.

    @since: 11.1
    """

    def __init__(self, code, message, uri):
        """
        Initializes a page redirect exception when no location is given.

        @type code: L{bytes}
        @param code: Refers to an HTTP status code, for example
            C{http.NOT_FOUND}. If no C{message} is given, C{code} is mapped to
            a descriptive string that is used instead.

        @type message: L{bytes}
        @param message: A short error message.

        @type uri: L{bytes}
        @param uri: The URI which failed to give a proper location header
            field.
        """
        Error.__init__(self, code, message)
        self.message = self.message + b" to " + uri
        self.uri = uri



class UnsupportedMethod(Exception):
    """
    Raised by a resource when faced with a strange request method.

    RFC 2616 (HTTP 1.1) gives us two choices when faced with this situation:
    If the type of request is known to us, but not allowed for the requested
    resource, respond with NOT_ALLOWED.  Otherwise, if the request is something
    we don't know how to deal with in any case, respond with NOT_IMPLEMENTED.

    When this exception is raised by a Resource's render method, the server
    will make the appropriate response.

    This exception's first argument MUST be a sequence of the methods the
    resource *does* support.
    """

    allowedMethods = ()

    def __init__(self, allowedMethods, *args):
        Exception.__init__(self, allowedMethods, *args)
        self.allowedMethods = allowedMethods

        if not isinstance(allowedMethods, Sequence):
            raise TypeError(
                "First argument must be a sequence of supported methods, "
                "but my first argument is not a sequence.")



class SchemeNotSupported(Exception):
    """
    The scheme of a URI was not one of the supported values.
    """



class RenderError(Exception):
    """
    Base exception class for all errors which can occur during template
    rendering.
    """



class MissingRenderMethod(RenderError):
    """
    Tried to use a render method which does not exist.

    @ivar element: The element which did not have the render method.
    @ivar renderName: The name of the renderer which could not be found.
    """
    def __init__(self, element, renderName):
        RenderError.__init__(self, element, renderName)
        self.element = element
        self.renderName = renderName


    def __repr__(self):
        return '%r: %r had no render method named %r' % (
            self.__class__.__name__, self.element, self.renderName)



class MissingTemplateLoader(RenderError):
    """
    L{MissingTemplateLoader} is raised when trying to render an Element without
    a template loader, i.e. a C{loader} attribute.

    @ivar element: The Element which did not have a document factory.
    """
    def __init__(self, element):
        RenderError.__init__(self, element)
        self.element = element


    def __repr__(self):
        return '%r: %r had no loader' % (self.__class__.__name__,
                                         self.element)



class UnexposedMethodError(Exception):
    """
    Raised on any attempt to get a method which has not been exposed.
    """



class UnfilledSlot(Exception):
    """
    During flattening, a slot with no associated data was encountered.
    """



class UnsupportedType(Exception):
    """
    During flattening, an object of a type which cannot be flattened was
    encountered.
    """



class FlattenerError(Exception):
    """
    An error occurred while flattening an object.

    @ivar _roots: A list of the objects on the flattener's stack at the time
        the unflattenable object was encountered.  The first element is least
        deeply nested object and the last element is the most deeply nested.
    """
    def __init__(self, exception, roots, traceback):
        self._exception = exception
        self._roots = roots
        self._traceback = traceback
        Exception.__init__(self, exception, roots, traceback)


    def _formatRoot(self, obj):
        """
        Convert an object from C{self._roots} to a string suitable for
        inclusion in a render-traceback (like a normal Python traceback, but
        can include "frame" source locations which are not in Python source
        files).

        @param obj: Any object which can be a render step I{root}.
            Typically, L{Tag}s, strings, and other simple Python types.

        @return: A string representation of C{obj}.
        @rtype: L{str}
        """
        # There's a circular dependency between this class and 'Tag', although
        # only for an isinstance() check.
        from twisted.web.template import Tag

        if isinstance(obj, (bytes, str, unicode)):
            # It's somewhat unlikely that there will ever be a str in the roots
            # list.  However, something like a MemoryError during a str.replace
            # call (eg, replacing " with &quot;) could possibly cause this.
            # Likewise, UTF-8 encoding a unicode string to a byte string might
            # fail like this.
            if len(obj) > 40:
                if isinstance(obj, unicode):
                    ellipsis = u'<...>'
                else:
                    ellipsis = b'<...>'
                return ascii(obj[:20] + ellipsis + obj[-20:])
            else:
                return ascii(obj)
        elif isinstance(obj, Tag):
            if obj.filename is None:
                return 'Tag <' + obj.tagName + '>'
            else:
                return "File \"%s\", line %d, column %d, in \"%s\"" % (
                    obj.filename, obj.lineNumber,
                    obj.columnNumber, obj.tagName)
        else:
            return ascii(obj)


    def __repr__(self):
        """
        Present a string representation which includes a template traceback, so
        we can tell where this error occurred in the template, as well as in
        Python.
        """
        # Avoid importing things unnecessarily until we actually need them;
        # since this is an 'error' module we should be extra paranoid about
        # that.
        from traceback import format_list
        if self._roots:
            roots = '  ' + '\n  '.join([
                    self._formatRoot(r) for r in self._roots]) + '\n'
        else:
            roots = ''
        if self._traceback:
            traceback = '\n'.join([
                    line
                    for entry in format_list(self._traceback)
                    for line in entry.splitlines()]) + '\n'
        else:
            traceback = ''
        return (
            'Exception while flattening:\n' +
            roots + traceback +
            self._exception.__class__.__name__ + ': ' +
            str(self._exception) + '\n')


    def __str__(self):
        return repr(self)



class UnsupportedSpecialHeader(Exception):
    """
    A HTTP/2 request was received that contained a HTTP/2 pseudo-header field
    that is not recognised by Twisted.
    """
