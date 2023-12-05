# -*- test-case-name: twisted.web.test.test_web, twisted.web.test.test_resource -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation of the lowest-level Resource class.

See L{twisted.web.pages} for some utility implementations.
"""


__all__ = [
    "IResource",
    "getChildForRequest",
    "Resource",
    "ErrorPage",
    "NoResource",
    "ForbiddenResource",
    "EncodingResourceWrapper",
]

import warnings

from zope.interface import Attribute, Interface, implementer

from incremental import Version

from twisted.python.compat import nativeString
from twisted.python.components import proxyForInterface
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.reflect import prefixedMethodNames
from twisted.web._responses import FORBIDDEN, NOT_FOUND
from twisted.web.error import UnsupportedMethod


class IResource(Interface):
    """
    A web resource.
    """

    isLeaf = Attribute(
        """
        Signal if this IResource implementor is a "leaf node" or not. If True,
        getChildWithDefault will not be called on this Resource.
        """
    )

    def getChildWithDefault(name, request):
        """
        Return a child with the given name for the given request.
        This is the external interface used by the Resource publishing
        machinery. If implementing IResource without subclassing
        Resource, it must be provided. However, if subclassing Resource,
        getChild overridden instead.

        @param name: A single path component from a requested URL.  For example,
            a request for I{http://example.com/foo/bar} will result in calls to
            this method with C{b"foo"} and C{b"bar"} as values for this
            argument.
        @type name: C{bytes}

        @param request: A representation of all of the information about the
            request that is being made for this child.
        @type request: L{twisted.web.server.Request}
        """

    def putChild(path: bytes, child: "IResource") -> None:
        """
        Put a child L{IResource} implementor at the given path.

        @param path: A single path component, to be interpreted relative to the
            path this resource is found at, at which to put the given child.
            For example, if resource A can be found at I{http://example.com/foo}
            then a call like C{A.putChild(b"bar", B)} will make resource B
            available at I{http://example.com/foo/bar}.

            The path component is I{not} URL-encoded -- pass C{b'foo bar'}
            rather than C{b'foo%20bar'}.
        """

    def render(request):
        """
        Render a request. This is called on the leaf resource for a request.

        @return: Either C{server.NOT_DONE_YET} to indicate an asynchronous or a
            C{bytes} instance to write as the response to the request.  If
            C{NOT_DONE_YET} is returned, at some point later (for example, in a
            Deferred callback) call C{request.write(b"<html>")} to write data to
            the request, and C{request.finish()} to send the data to the
            browser.

        @raise twisted.web.error.UnsupportedMethod: If the HTTP verb
            requested is not supported by this resource.
        """


def getChildForRequest(resource, request):
    """
    Traverse resource tree to find who will handle the request.
    """
    while request.postpath and not resource.isLeaf:
        pathElement = request.postpath.pop(0)
        request.prepath.append(pathElement)
        resource = resource.getChildWithDefault(pathElement, request)
    return resource


@implementer(IResource)
class Resource:
    """
    Define a web-accessible resource.

    This serves two main purposes: one is to provide a standard representation
    for what HTTP specification calls an 'entity', and the other is to provide
    an abstract directory structure for URL retrieval.
    """

    entityType = IResource

    server = None

    def __init__(self):
        """
        Initialize.
        """
        self.children = {}

    isLeaf = 0

    ### Abstract Collection Interface

    def listStaticNames(self):
        return list(self.children.keys())

    def listStaticEntities(self):
        return list(self.children.items())

    def listNames(self):
        return list(self.listStaticNames()) + self.listDynamicNames()

    def listEntities(self):
        return list(self.listStaticEntities()) + self.listDynamicEntities()

    def listDynamicNames(self):
        return []

    def listDynamicEntities(self, request=None):
        return []

    def getStaticEntity(self, name):
        return self.children.get(name)

    def getDynamicEntity(self, name, request):
        if name not in self.children:
            return self.getChild(name, request)
        else:
            return None

    def delEntity(self, name):
        del self.children[name]

    def reallyPutEntity(self, name, entity):
        self.children[name] = entity

    # Concrete HTTP interface

    def getChild(self, path, request):
        """
        Retrieve a 'child' resource from me.

        Implement this to create dynamic resource generation -- resources which
        are always available may be registered with self.putChild().

        This will not be called if the class-level variable 'isLeaf' is set in
        your subclass; instead, the 'postpath' attribute of the request will be
        left as a list of the remaining path elements.

        For example, the URL /foo/bar/baz will normally be::

          | site.resource.getChild('foo').getChild('bar').getChild('baz').

        However, if the resource returned by 'bar' has isLeaf set to true, then
        the getChild call will never be made on it.

        Parameters and return value have the same meaning and requirements as
        those defined by L{IResource.getChildWithDefault}.
        """
        return _UnsafeNoResource()

    def getChildWithDefault(self, path, request):
        """
        Retrieve a static or dynamically generated child resource from me.

        First checks if a resource was added manually by putChild, and then
        call getChild to check for dynamic resources. Only override if you want
        to affect behaviour of all child lookups, rather than just dynamic
        ones.

        This will check to see if I have a pre-registered child resource of the
        given name, and call getChild if I do not.

        @see: L{IResource.getChildWithDefault}
        """
        if path in self.children:
            return self.children[path]
        return self.getChild(path, request)

    def getChildForRequest(self, request):
        """
        Deprecated in favor of L{getChildForRequest}.

        @see: L{twisted.web.resource.getChildForRequest}.
        """
        warnings.warn(
            "Please use module level getChildForRequest.", DeprecationWarning, 2
        )
        return getChildForRequest(self, request)

    def putChild(self, path: bytes, child: IResource) -> None:
        """
        Register a static child.

        You almost certainly don't want '/' in your path. If you
        intended to have the root of a folder, e.g. /foo/, you want
        path to be ''.

        @param path: A single path component.

        @param child: The child resource to register.

        @see: L{IResource.putChild}
        """
        if not isinstance(path, bytes):
            raise TypeError(f"Path segment must be bytes, but {path!r} is {type(path)}")

        self.children[path] = child
        # IResource is incomplete and doesn't mention this server attribute, see
        # https://github.com/twisted/twisted/issues/11717
        child.server = self.server  # type: ignore[attr-defined]

    def render(self, request):
        """
        Render a given resource. See L{IResource}'s render method.

        I delegate to methods of self with the form 'render_METHOD'
        where METHOD is the HTTP that was used to make the
        request. Examples: render_GET, render_HEAD, render_POST, and
        so on. Generally you should implement those methods instead of
        overriding this one.

        render_METHOD methods are expected to return a byte string which will be
        the rendered page, unless the return value is C{server.NOT_DONE_YET}, in
        which case it is this class's responsibility to write the results using
        C{request.write(data)} and then call C{request.finish()}.

        Old code that overrides render() directly is likewise expected
        to return a byte string or NOT_DONE_YET.

        @see: L{IResource.render}
        """
        m = getattr(self, "render_" + nativeString(request.method), None)
        if not m:
            try:
                allowedMethods = self.allowedMethods
            except AttributeError:
                allowedMethods = _computeAllowedMethods(self)
            raise UnsupportedMethod(allowedMethods)
        return m(request)

    def render_HEAD(self, request):
        """
        Default handling of HEAD method.

        I just return self.render_GET(request). When method is HEAD,
        the framework will handle this correctly.
        """
        return self.render_GET(request)


def _computeAllowedMethods(resource):
    """
    Compute the allowed methods on a C{Resource} based on defined render_FOO
    methods. Used when raising C{UnsupportedMethod} but C{Resource} does
    not define C{allowedMethods} attribute.
    """
    allowedMethods = []
    for name in prefixedMethodNames(resource.__class__, "render_"):
        # Potentially there should be an API for encode('ascii') in this
        # situation - an API for taking a Python native string (bytes on Python
        # 2, text on Python 3) and returning a socket-compatible string type.
        allowedMethods.append(name.encode("ascii"))
    return allowedMethods


class _UnsafeErrorPage(Resource):
    """
    L{_UnsafeErrorPage}, publicly available via the deprecated alias
    C{ErrorPage}, is a resource which responds with a particular
    (parameterized) status and a body consisting of HTML containing some
    descriptive text.  This is useful for rendering simple error pages.

    Deprecated in Twisted 22.10.0 because it permits HTML injection; use
    L{twisted.web.pages.errorPage} instead.

    @ivar template: A native string which will have a dictionary interpolated
        into it to generate the response body.  The dictionary has the following
        keys:

          - C{"code"}: The status code passed to L{_UnsafeErrorPage.__init__}.
          - C{"brief"}: The brief description passed to
            L{_UnsafeErrorPage.__init__}.
          - C{"detail"}: The detailed description passed to
            L{_UnsafeErrorPage.__init__}.

    @ivar code: An integer status code which will be used for the response.
    @type code: C{int}

    @ivar brief: A short string which will be included in the response body as
        the page title.
    @type brief: C{str}

    @ivar detail: A longer string which will be included in the response body.
    @type detail: C{str}
    """

    template = """
<html>
  <head><title>%(code)s - %(brief)s</title></head>
  <body>
    <h1>%(brief)s</h1>
    <p>%(detail)s</p>
  </body>
</html>
"""

    def __init__(self, status, brief, detail):
        Resource.__init__(self)
        self.code = status
        self.brief = brief
        self.detail = detail

    def render(self, request):
        request.setResponseCode(self.code)
        request.setHeader(b"content-type", b"text/html; charset=utf-8")
        interpolated = self.template % dict(
            code=self.code, brief=self.brief, detail=self.detail
        )
        if isinstance(interpolated, str):
            return interpolated.encode("utf-8")
        return interpolated

    def getChild(self, chnam, request):
        return self


class _UnsafeNoResource(_UnsafeErrorPage):
    """
    L{_UnsafeNoResource}, publicly available via the deprecated alias
    C{NoResource}, is a specialization of L{_UnsafeErrorPage} which
    returns the HTTP response code I{NOT FOUND}.

    Deprecated in Twisted 22.10.0 because it permits HTML injection; use
    L{twisted.web.pages.notFound} instead.
    """

    def __init__(self, message="Sorry. No luck finding that resource."):
        _UnsafeErrorPage.__init__(self, NOT_FOUND, "No Such Resource", message)


class _UnsafeForbiddenResource(_UnsafeErrorPage):
    """
    L{_UnsafeForbiddenResource}, publicly available via the deprecated alias
    C{ForbiddenResource} is a specialization of L{_UnsafeErrorPage} which
    returns the I{FORBIDDEN} HTTP response code.

    Deprecated in Twisted 22.10.0 because it permits HTML injection; use
    L{twisted.web.pages.forbidden} instead.
    """

    def __init__(self, message="Sorry, resource is forbidden."):
        _UnsafeErrorPage.__init__(self, FORBIDDEN, "Forbidden Resource", message)


# Deliberately undocumented public aliases. See GHSA-vg46-2rrj-3647.
ErrorPage = _UnsafeErrorPage
NoResource = _UnsafeNoResource
ForbiddenResource = _UnsafeForbiddenResource

deprecatedModuleAttribute(
    Version("Twisted", 22, 10, 0),
    "Use twisted.web.pages.errorPage instead, which properly escapes HTML.",
    __name__,
    "ErrorPage",
)

deprecatedModuleAttribute(
    Version("Twisted", 22, 10, 0),
    "Use twisted.web.pages.notFound instead, which properly escapes HTML.",
    __name__,
    "NoResource",
)

deprecatedModuleAttribute(
    Version("Twisted", 22, 10, 0),
    "Use twisted.web.pages.forbidden instead, which properly escapes HTML.",
    __name__,
    "ForbiddenResource",
)


class _IEncodingResource(Interface):
    """
    A resource which knows about L{_IRequestEncoderFactory}.

    @since: 12.3
    """

    def getEncoder(request):
        """
        Parse the request and return an encoder if applicable, using
        L{_IRequestEncoderFactory.encoderForRequest}.

        @return: A L{_IRequestEncoder}, or L{None}.
        """


@implementer(_IEncodingResource)
class EncodingResourceWrapper(proxyForInterface(IResource)):  # type: ignore[misc]
    """
    Wrap a L{IResource}, potentially applying an encoding to the response body
    generated.

    Note that the returned children resources won't be wrapped, so you have to
    explicitly wrap them if you want the encoding to be applied.

    @ivar encoders: A list of
        L{_IRequestEncoderFactory<twisted.web.iweb._IRequestEncoderFactory>}
        returning L{_IRequestEncoder<twisted.web.iweb._IRequestEncoder>} that
        may transform the data passed to C{Request.write}. The list must be
        sorted in order of priority: the first encoder factory handling the
        request will prevent the others from doing the same.
    @type encoders: C{list}.

    @since: 12.3
    """

    def __init__(self, original, encoders):
        super().__init__(original)
        self._encoders = encoders

    def getEncoder(self, request):
        """
        Browser the list of encoders looking for one applicable encoder.
        """
        for encoderFactory in self._encoders:
            encoder = encoderFactory.encoderForRequest(request)
            if encoder is not None:
                return encoder
