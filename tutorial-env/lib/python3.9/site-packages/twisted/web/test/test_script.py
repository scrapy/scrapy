# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.script}.
"""

import os

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.web.http import NOT_FOUND
from twisted.web.script import PythonScript, ResourceScriptDirectory
from twisted.web.test._util import _render
from twisted.web.test.requesthelper import DummyRequest


class ResourceScriptDirectoryTests(TestCase):
    """
    Tests for L{ResourceScriptDirectory}.
    """

    def test_renderNotFound(self):
        """
        L{ResourceScriptDirectory.render} sets the HTTP response code to I{NOT
        FOUND}.
        """
        resource = ResourceScriptDirectory(self.mktemp())
        request = DummyRequest([b""])
        d = _render(resource, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, NOT_FOUND)

        d.addCallback(cbRendered)
        return d

    def test_notFoundChild(self):
        """
        L{ResourceScriptDirectory.getChild} returns a resource which renders an
        response with the HTTP I{NOT FOUND} status code if the indicated child
        does not exist as an entry in the directory used to initialized the
        L{ResourceScriptDirectory}.
        """
        path = self.mktemp()
        os.makedirs(path)
        resource = ResourceScriptDirectory(path)
        request = DummyRequest([b"foo"])
        child = resource.getChild("foo", request)
        d = _render(child, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, NOT_FOUND)

        d.addCallback(cbRendered)
        return d

    def test_render(self):
        """
        L{ResourceScriptDirectory.getChild} returns a resource which renders a
        response with the HTTP 200 status code and the content of the rpy's
        C{request} global.
        """
        tmp = FilePath(self.mktemp())
        tmp.makedirs()
        tmp.child("test.rpy").setContent(
            b"""
from twisted.web.resource import Resource
class TestResource(Resource):
    isLeaf = True
    def render_GET(self, request):
        return b'ok'
resource = TestResource()"""
        )
        resource = ResourceScriptDirectory(tmp._asBytesPath())
        request = DummyRequest([b""])
        child = resource.getChild(b"test.rpy", request)
        d = _render(child, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"ok")

        d.addCallback(cbRendered)
        return d


class PythonScriptTests(TestCase):
    """
    Tests for L{PythonScript}.
    """

    def test_notFoundRender(self):
        """
        If the source file a L{PythonScript} is initialized with doesn't exist,
        L{PythonScript.render} sets the HTTP response code to I{NOT FOUND}.
        """
        resource = PythonScript(self.mktemp(), None)
        request = DummyRequest([b""])
        d = _render(resource, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, NOT_FOUND)

        d.addCallback(cbRendered)
        return d

    def test_renderException(self):
        """
        L{ResourceScriptDirectory.getChild} returns a resource which renders a
        response with the HTTP 200 status code and the content of the rpy's
        C{request} global.
        """
        tmp = FilePath(self.mktemp())
        tmp.makedirs()
        child = tmp.child("test.epy")
        child.setContent(b'raise Exception("nooo")')
        resource = PythonScript(child._asBytesPath(), None)
        request = DummyRequest([b""])
        d = _render(resource, request)

        def cbRendered(ignored):
            self.assertIn(b"nooo", b"".join(request.written))

        d.addCallback(cbRendered)
        return d
