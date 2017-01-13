# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.resource}.
"""

from twisted.trial.unittest import TestCase

from twisted.web.error import UnsupportedMethod
from twisted.web.resource import (
    NOT_FOUND, FORBIDDEN, Resource, ErrorPage, NoResource, ForbiddenResource,
    getChildForRequest)
from twisted.web.http_headers import Headers
from twisted.web.test.requesthelper import DummyRequest


class ErrorPageTests(TestCase):
    """
    Tests for L{ErrorPage}, L{NoResource}, and L{ForbiddenResource}.
    """

    errorPage = ErrorPage
    noResource = NoResource
    forbiddenResource = ForbiddenResource

    def test_getChild(self):
        """
        The C{getChild} method of L{ErrorPage} returns the L{ErrorPage} it is
        called on.
        """
        page = self.errorPage(321, "foo", "bar")
        self.assertIdentical(page.getChild(b"name", object()), page)


    def _pageRenderingTest(self, page, code, brief, detail):
        request = DummyRequest([b''])
        template = (
            u"\n"
            u"<html>\n"
            u"  <head><title>%s - %s</title></head>\n"
            u"  <body>\n"
            u"    <h1>%s</h1>\n"
            u"    <p>%s</p>\n"
            u"  </body>\n"
            u"</html>\n")
        expected = template % (code, brief, brief, detail)
        self.assertEqual(
            page.render(request), expected.encode('utf-8'))
        self.assertEqual(request.responseCode, code)
        self.assertEqual(
            request.responseHeaders,
            Headers({b'content-type': [b'text/html; charset=utf-8']}))


    def test_errorPageRendering(self):
        """
        L{ErrorPage.render} returns a C{bytes} describing the error defined by
        the response code and message passed to L{ErrorPage.__init__}.  It also
        uses that response code to set the response code on the L{Request}
        passed in.
        """
        code = 321
        brief = "brief description text"
        detail = "much longer text might go here"
        page = self.errorPage(code, brief, detail)
        self._pageRenderingTest(page, code, brief, detail)


    def test_noResourceRendering(self):
        """
        L{NoResource} sets the HTTP I{NOT FOUND} code.
        """
        detail = "long message"
        page = self.noResource(detail)
        self._pageRenderingTest(page, NOT_FOUND, "No Such Resource", detail)


    def test_forbiddenResourceRendering(self):
        """
        L{ForbiddenResource} sets the HTTP I{FORBIDDEN} code.
        """
        detail = "longer message"
        page = self.forbiddenResource(detail)
        self._pageRenderingTest(page, FORBIDDEN, "Forbidden Resource", detail)



class DynamicChild(Resource):
    """
    A L{Resource} to be created on the fly by L{DynamicChildren}.
    """
    def __init__(self, path, request):
        Resource.__init__(self)
        self.path = path
        self.request = request



class DynamicChildren(Resource):
    """
    A L{Resource} with dynamic children.
    """
    def getChild(self, path, request):
        return DynamicChild(path, request)



class BytesReturnedRenderable(Resource):
    """
    A L{Resource} with minimal capabilities to render a response.
    """
    def __init__(self, response):
        """
        @param response: A C{bytes} object giving the value to return from
            C{render_GET}.
        """
        Resource.__init__(self)
        self._response = response


    def render_GET(self, request):
        """
        Render a response to a I{GET} request by returning a short byte string
        to be written by the server.
        """
        return self._response



class ImplicitAllowedMethods(Resource):
    """
    A L{Resource} which implicitly defines its allowed methods by defining
    renderers to handle them.
    """
    def render_GET(self, request):
        pass


    def render_PUT(self, request):
        pass



class ResourceTests(TestCase):
    """
    Tests for L{Resource}.
    """
    def test_staticChildren(self):
        """
        L{Resource.putChild} adds a I{static} child to the resource.  That child
        is returned from any call to L{Resource.getChildWithDefault} for the
        child's path.
        """
        resource = Resource()
        child = Resource()
        sibling = Resource()
        resource.putChild(b"foo", child)
        resource.putChild(b"bar", sibling)
        self.assertIdentical(
            child, resource.getChildWithDefault(b"foo", DummyRequest([])))


    def test_dynamicChildren(self):
        """
        L{Resource.getChildWithDefault} delegates to L{Resource.getChild} when
        the requested path is not associated with any static child.
        """
        path = b"foo"
        request = DummyRequest([])
        resource = DynamicChildren()
        child = resource.getChildWithDefault(path, request)
        self.assertIsInstance(child, DynamicChild)
        self.assertEqual(child.path, path)
        self.assertIdentical(child.request, request)


    def test_defaultHEAD(self):
        """
        When not otherwise overridden, L{Resource.render} treats a I{HEAD}
        request as if it were a I{GET} request.
        """
        expected = b"insert response here"
        request = DummyRequest([])
        request.method = b'HEAD'
        resource = BytesReturnedRenderable(expected)
        self.assertEqual(expected, resource.render(request))


    def test_explicitAllowedMethods(self):
        """
        The L{UnsupportedMethod} raised by L{Resource.render} for an unsupported
        request method has a C{allowedMethods} attribute set to the value of the
        C{allowedMethods} attribute of the L{Resource}, if it has one.
        """
        expected = [b'GET', b'HEAD', b'PUT']
        resource = Resource()
        resource.allowedMethods = expected
        request = DummyRequest([])
        request.method = b'FICTIONAL'
        exc = self.assertRaises(UnsupportedMethod, resource.render, request)
        self.assertEqual(set(expected), set(exc.allowedMethods))


    def test_implicitAllowedMethods(self):
        """
        The L{UnsupportedMethod} raised by L{Resource.render} for an unsupported
        request method has a C{allowedMethods} attribute set to a list of the
        methods supported by the L{Resource}, as determined by the
        I{render_}-prefixed methods which it defines, if C{allowedMethods} is
        not explicitly defined by the L{Resource}.
        """
        expected = set([b'GET', b'HEAD', b'PUT'])
        resource = ImplicitAllowedMethods()
        request = DummyRequest([])
        request.method = b'FICTIONAL'
        exc = self.assertRaises(UnsupportedMethod, resource.render, request)
        self.assertEqual(expected, set(exc.allowedMethods))




class GetChildForRequestTests(TestCase):
    """
    Tests for L{getChildForRequest}.
    """
    def test_exhaustedPostPath(self):
        """
        L{getChildForRequest} returns whatever resource has been reached by the
        time the request's C{postpath} is empty.
        """
        request = DummyRequest([])
        resource = Resource()
        result = getChildForRequest(resource, request)
        self.assertIdentical(resource, result)


    def test_leafResource(self):
        """
        L{getChildForRequest} returns the first resource it encounters with a
        C{isLeaf} attribute set to C{True}.
        """
        request = DummyRequest([b"foo", b"bar"])
        resource = Resource()
        resource.isLeaf = True
        result = getChildForRequest(resource, request)
        self.assertIdentical(resource, result)


    def test_postPathToPrePath(self):
        """
        As path segments from the request are traversed, they are taken from
        C{postpath} and put into C{prepath}.
        """
        request = DummyRequest([b"foo", b"bar"])
        root = Resource()
        child = Resource()
        child.isLeaf = True
        root.putChild(b"foo", child)
        self.assertIdentical(child, getChildForRequest(root, request))
        self.assertEqual(request.prepath, [b"foo"])
        self.assertEqual(request.postpath, [b"bar"])
