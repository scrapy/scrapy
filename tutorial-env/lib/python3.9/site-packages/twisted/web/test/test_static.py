# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.static}.
"""
import errno
import inspect
import mimetypes
import os
import re
import sys
import warnings
from io import BytesIO as StringIO
from unittest import skipIf

from zope.interface.verify import verifyObject

from twisted.internet import abstract, interfaces
from twisted.python import compat, log
from twisted.python.compat import networkString
from twisted.python.filepath import FilePath
from twisted.python.runtime import platform
from twisted.trial.unittest import TestCase
from twisted.web import http, resource, script, static
from twisted.web._responses import FOUND
from twisted.web.server import UnsupportedMethod
from twisted.web.test._util import _render
from twisted.web.test.requesthelper import DummyRequest


class StaticDataTests(TestCase):
    """
    Tests for L{Data}.
    """

    def test_headRequest(self):
        """
        L{Data.render} returns an empty response body for a I{HEAD} request.
        """
        data = static.Data(b"foo", "bar")
        request = DummyRequest([""])
        request.method = b"HEAD"
        d = _render(data, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"")

        d.addCallback(cbRendered)
        return d

    def test_invalidMethod(self):
        """
        L{Data.render} raises L{UnsupportedMethod} in response to a non-I{GET},
        non-I{HEAD} request.
        """
        data = static.Data(b"foo", b"bar")
        request = DummyRequest([b""])
        request.method = b"POST"
        self.assertRaises(UnsupportedMethod, data.render, request)


class StaticFileTests(TestCase):
    """
    Tests for the basic behavior of L{File}.
    """

    def _render(self, resource, request):
        return _render(resource, request)

    def test_ignoredExtTrue(self):
        """
        Passing C{1} as the value to L{File}'s C{ignoredExts} argument
        issues a warning and sets the ignored extensions to the
        wildcard C{"*"}.
        """
        with warnings.catch_warnings(record=True) as caughtWarnings:
            file = static.File(self.mktemp(), ignoredExts=1)
            self.assertEqual(file.ignoredExts, ["*"])

        self.assertEqual(len(caughtWarnings), 1)

    def test_ignoredExtFalse(self):
        """
        Passing C{1} as the value to L{File}'s C{ignoredExts} argument
        issues a warning and sets the ignored extensions to the empty
        list.
        """
        with warnings.catch_warnings(record=True) as caughtWarnings:
            file = static.File(self.mktemp(), ignoredExts=0)
            self.assertEqual(file.ignoredExts, [])

        self.assertEqual(len(caughtWarnings), 1)

    def test_allowExt(self):
        """
        Passing C{1} as the value to L{File}'s C{allowExt} argument
        issues a warning and sets the ignored extensions to the
        wildcard C{*}.
        """
        with warnings.catch_warnings(record=True) as caughtWarnings:
            file = static.File(self.mktemp(), ignoredExts=True)
            self.assertEqual(file.ignoredExts, ["*"])

        self.assertEqual(len(caughtWarnings), 1)

    def test_invalidMethod(self):
        """
        L{File.render} raises L{UnsupportedMethod} in response to a non-I{GET},
        non-I{HEAD} request.
        """
        request = DummyRequest([b""])
        request.method = b"POST"
        path = FilePath(self.mktemp())
        path.setContent(b"foo")
        file = static.File(path.path)
        self.assertRaises(UnsupportedMethod, file.render, request)

    def test_notFound(self):
        """
        If a request is made which encounters a L{File} before a final segment
        which does not correspond to any file in the path the L{File} was
        created with, a not found response is sent.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        file = static.File(base.path)

        request = DummyRequest([b"foobar"])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, 404)

        d.addCallback(cbRendered)
        return d

    def test_emptyChild(self):
        """
        The C{''} child of a L{File} which corresponds to a directory in the
        filesystem is a L{DirectoryLister}.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        file = static.File(base.path)

        request = DummyRequest([b""])
        child = resource.getChildForRequest(file, request)
        self.assertIsInstance(child, static.DirectoryLister)
        self.assertEqual(child.path, base.path)

    def test_emptyChildUnicodeParent(self):
        """
        The C{u''} child of a L{File} which corresponds to a directory
        whose path is text is a L{DirectoryLister} that renders to a
        binary listing.

        @see: U{https://twistedmatrix.com/trac/ticket/9438}
        """
        textBase = FilePath(self.mktemp()).asTextMode()
        textBase.makedirs()
        textBase.child("text-file").open("w").close()
        textFile = static.File(textBase.path)

        request = DummyRequest([b""])
        child = resource.getChildForRequest(textFile, request)
        self.assertIsInstance(child, static.DirectoryLister)

        nativePath = compat.nativeString(textBase.path)
        self.assertEqual(child.path, nativePath)

        response = child.render(request)
        self.assertIsInstance(response, bytes)

    def test_securityViolationNotFound(self):
        """
        If a request is made which encounters a L{File} before a final segment
        which cannot be looked up in the filesystem due to security
        considerations, a not found response is sent.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        file = static.File(base.path)

        request = DummyRequest([b".."])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, 404)

        d.addCallback(cbRendered)
        return d

    @skipIf(platform.isWindows(), "Cannot remove read permission on Windows")
    def test_forbiddenResource(self):
        """
        If the file in the filesystem which would satisfy a request cannot be
        read, L{File.render} sets the HTTP response code to I{FORBIDDEN}.
        """
        base = FilePath(self.mktemp())
        base.setContent(b"")
        # Make sure we can delete the file later.
        self.addCleanup(base.chmod, 0o700)

        # Get rid of our own read permission.
        base.chmod(0)

        file = static.File(base.path)
        request = DummyRequest([b""])
        d = self._render(file, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, 403)

        d.addCallback(cbRendered)
        return d

    def test_undecodablePath(self):
        """
        A request whose path cannot be decoded as UTF-8 receives a not
        found response, and the failure is logged.
        """
        path = self.mktemp()
        if isinstance(path, bytes):
            path = path.decode("ascii")
        base = FilePath(path)
        base.makedirs()

        file = static.File(base.path)
        request = DummyRequest([b"\xff"])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, 404)
            self.assertEqual(len(self.flushLoggedErrors(UnicodeDecodeError)), 1)

        d.addCallback(cbRendered)
        return d

    def test_forbiddenResource_default(self):
        """
        L{File.forbidden} defaults to L{resource.ForbiddenResource}.
        """
        self.assertIsInstance(static.File(b".").forbidden, resource.ForbiddenResource)

    def test_forbiddenResource_customize(self):
        """
        The resource rendered for forbidden requests is stored as a class
        member so that users can customize it.
        """
        base = FilePath(self.mktemp())
        base.setContent(b"")
        markerResponse = b"custom-forbidden-response"

        def failingOpenForReading():
            raise OSError(errno.EACCES, "")

        class CustomForbiddenResource(resource.Resource):
            def render(self, request):
                return markerResponse

        class CustomStaticFile(static.File):
            forbidden = CustomForbiddenResource()

        fileResource = CustomStaticFile(base.path)
        fileResource.openForReading = failingOpenForReading
        request = DummyRequest([b""])

        result = fileResource.render(request)

        self.assertEqual(markerResponse, result)

    def test_indexNames(self):
        """
        If a request is made which encounters a L{File} before a final empty
        segment, a file in the L{File} instance's C{indexNames} list which
        exists in the path the L{File} was created with is served as the
        response to the request.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        base.child("foo.bar").setContent(b"baz")
        file = static.File(base.path)
        file.indexNames = ["foo.bar"]

        request = DummyRequest([b""])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"baz")
            self.assertEqual(
                request.responseHeaders.getRawHeaders(b"content-length")[0], b"3"
            )

        d.addCallback(cbRendered)
        return d

    def test_staticFile(self):
        """
        If a request is made which encounters a L{File} before a final segment
        which names a file in the path the L{File} was created with, that file
        is served as the response to the request.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        base.child("foo.bar").setContent(b"baz")
        file = static.File(base.path)

        request = DummyRequest([b"foo.bar"])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"baz")
            self.assertEqual(
                request.responseHeaders.getRawHeaders(b"content-length")[0], b"3"
            )

        d.addCallback(cbRendered)
        return d

    @skipIf(
        sys.getfilesystemencoding().lower() not in ("utf-8", "mcbs"),
        "Cannot write unicode filenames with file system encoding of"
        " {}".format(sys.getfilesystemencoding()),
    )
    def test_staticFileUnicodeFileName(self):
        """
        A request for a existing unicode file path encoded as UTF-8
        returns the contents of that file.
        """
        name = "\N{GREEK SMALL LETTER ETA WITH PERISPOMENI}"
        content = b"content"

        base = FilePath(self.mktemp())
        base.makedirs()
        base.child(name).setContent(content)
        file = static.File(base.path)

        request = DummyRequest([name.encode("utf-8")])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), content)
            self.assertEqual(
                request.responseHeaders.getRawHeaders(b"content-length")[0],
                networkString(str(len(content))),
            )

        d.addCallback(cbRendered)
        return d

    def test_staticFileDeletedGetChild(self):
        """
        A L{static.File} created for a directory which does not exist should
        return childNotFound from L{static.File.getChild}.
        """
        staticFile = static.File(self.mktemp())
        request = DummyRequest([b"foo.bar"])
        child = staticFile.getChild(b"foo.bar", request)
        self.assertEqual(child, staticFile.childNotFound)

    def test_staticFileDeletedRender(self):
        """
        A L{static.File} created for a file which does not exist should render
        its C{childNotFound} page.
        """
        staticFile = static.File(self.mktemp())
        request = DummyRequest([b"foo.bar"])
        request2 = DummyRequest([b"foo.bar"])
        d = self._render(staticFile, request)
        d2 = self._render(staticFile.childNotFound, request2)

        def cbRendered2(ignored):
            def cbRendered(ignored):
                self.assertEqual(b"".join(request.written), b"".join(request2.written))

            d.addCallback(cbRendered)
            return d

        d2.addCallback(cbRendered2)
        return d2

    def test_getChildChildNotFound_customize(self):
        """
        The resource rendered for child not found requests can be customize
        using a class member.
        """
        base = FilePath(self.mktemp())
        base.setContent(b"")
        markerResponse = b"custom-child-not-found-response"

        class CustomChildNotFoundResource(resource.Resource):
            def render(self, request):
                return markerResponse

        class CustomStaticFile(static.File):
            childNotFound = CustomChildNotFoundResource()

        fileResource = CustomStaticFile(base.path)
        request = DummyRequest([b"no-child.txt"])

        child = fileResource.getChild(b"no-child.txt", request)
        result = child.render(request)

        self.assertEqual(markerResponse, result)

    def test_headRequest(self):
        """
        L{static.File.render} returns an empty response body for I{HEAD}
        requests.
        """
        path = FilePath(self.mktemp())
        path.setContent(b"foo")
        file = static.File(path.path)
        request = DummyRequest([b""])
        request.method = b"HEAD"
        d = _render(file, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"")

        d.addCallback(cbRendered)
        return d

    def test_processors(self):
        """
        If a request is made which encounters a L{File} before a final segment
        which names a file with an extension which is in the L{File}'s
        C{processors} mapping, the processor associated with that extension is
        used to serve the response to the request.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        base.child("foo.bar").setContent(
            b"from twisted.web.static import Data\n"
            b"resource = Data(b'dynamic world', 'text/plain')\n"
        )

        file = static.File(base.path)
        file.processors = {".bar": script.ResourceScript}
        request = DummyRequest([b"foo.bar"])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"dynamic world")
            self.assertEqual(
                request.responseHeaders.getRawHeaders(b"content-length")[0], b"13"
            )

        d.addCallback(cbRendered)
        return d

    def test_ignoreExt(self):
        """
        The list of ignored extensions can be set by passing a value to
        L{File.__init__} or by calling L{File.ignoreExt} later.
        """
        file = static.File(b".")
        self.assertEqual(file.ignoredExts, [])
        file.ignoreExt(".foo")
        file.ignoreExt(".bar")
        self.assertEqual(file.ignoredExts, [".foo", ".bar"])

        file = static.File(b".", ignoredExts=(".bar", ".baz"))
        self.assertEqual(file.ignoredExts, [".bar", ".baz"])

    def test_ignoredExtensionsIgnored(self):
        """
        A request for the I{base} child of a L{File} succeeds with a resource
        for the I{base<extension>} file in the path the L{File} was created
        with if such a file exists and the L{File} has been configured to
        ignore the I{<extension>} extension.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        base.child("foo.bar").setContent(b"baz")
        base.child("foo.quux").setContent(b"foobar")
        file = static.File(base.path, ignoredExts=(".bar",))

        request = DummyRequest([b"foo"])
        child = resource.getChildForRequest(file, request)

        d = self._render(child, request)

        def cbRendered(ignored):
            self.assertEqual(b"".join(request.written), b"baz")

        d.addCallback(cbRendered)
        return d

    def test_directoryWithoutTrailingSlashRedirects(self):
        """
        A request for a path which is a directory but does not have a trailing
        slash will be redirected to a URL which does have a slash by L{File}.
        """
        base = FilePath(self.mktemp())
        base.makedirs()
        base.child("folder").makedirs()
        file = static.File(base.path)

        request = DummyRequest([b"folder"])
        request.uri = b"http://dummy/folder#baz?foo=bar"
        child = resource.getChildForRequest(file, request)

        self.successResultOf(self._render(child, request))
        self.assertEqual(request.responseCode, FOUND)
        self.assertEqual(
            request.responseHeaders.getRawHeaders(b"location"),
            [b"http://dummy/folder/#baz?foo=bar"],
        )

    def _makeFilePathWithStringIO(self):
        """
        Create a L{File} that when opened for reading, returns a L{StringIO}.

        @return: 2-tuple of the opened "file" and the L{File}.
        @rtype: L{tuple}
        """
        fakeFile = StringIO()
        path = FilePath(self.mktemp())
        path.touch()
        file = static.File(path.path)
        # Open our file instead of a real one
        file.open = lambda: fakeFile
        return fakeFile, file

    def test_HEADClosesFile(self):
        """
        A HEAD request opens the file, gets the size, and then closes it after
        the request.
        """
        fakeFile, file = self._makeFilePathWithStringIO()
        request = DummyRequest([""])
        request.method = b"HEAD"
        self.successResultOf(_render(file, request))
        self.assertEqual(b"".join(request.written), b"")
        self.assertTrue(fakeFile.closed)

    def test_cachedRequestClosesFile(self):
        """
        A GET request that is cached closes the file after the request.
        """
        fakeFile, file = self._makeFilePathWithStringIO()
        request = DummyRequest([""])
        request.method = b"GET"
        # This request will always return saying that it is cached
        request.setLastModified = lambda _: http.CACHED
        self.successResultOf(_render(file, request))
        self.assertEqual(b"".join(request.written), b"")
        self.assertTrue(fakeFile.closed)


class StaticMakeProducerTests(TestCase):
    """
    Tests for L{File.makeProducer}.
    """

    def makeResourceWithContent(self, content, type=None, encoding=None):
        """
        Make a L{static.File} resource that has C{content} for its content.

        @param content: The L{bytes} to use as the contents of the resource.
        @param type: Optional value for the content type of the resource.
        """
        fileName = FilePath(self.mktemp())
        fileName.setContent(content)
        resource = static.File(fileName._asBytesPath())
        resource.encoding = encoding
        resource.type = type
        return resource

    def contentHeaders(self, request):
        """
        Extract the content-* headers from the L{DummyRequest} C{request}.

        This returns the subset of C{request.outgoingHeaders} of headers that
        start with 'content-'.
        """
        contentHeaders = {}
        for k, v in request.responseHeaders.getAllRawHeaders():
            if k.lower().startswith(b"content-"):
                contentHeaders[k.lower()] = v[0]
        return contentHeaders

    def test_noRangeHeaderGivesNoRangeStaticProducer(self):
        """
        makeProducer when no Range header is set returns an instance of
        NoRangeStaticProducer.
        """
        resource = self.makeResourceWithContent(b"")
        request = DummyRequest([])
        with resource.openForReading() as file:
            producer = resource.makeProducer(request, file)
            self.assertIsInstance(producer, static.NoRangeStaticProducer)

    def test_noRangeHeaderSets200OK(self):
        """
        makeProducer when no Range header is set sets the responseCode on the
        request to 'OK'.
        """
        resource = self.makeResourceWithContent(b"")
        request = DummyRequest([])
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(http.OK, request.responseCode)

    def test_noRangeHeaderSetsContentHeaders(self):
        """
        makeProducer when no Range header is set sets the Content-* headers
        for the response.
        """
        length = 123
        contentType = "text/plain"
        contentEncoding = "gzip"
        resource = self.makeResourceWithContent(
            b"a" * length, type=contentType, encoding=contentEncoding
        )
        request = DummyRequest([])
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(
                {
                    b"content-type": networkString(contentType),
                    b"content-length": b"%d" % (length,),
                    b"content-encoding": networkString(contentEncoding),
                },
                self.contentHeaders(request),
            )

    def test_singleRangeGivesSingleRangeStaticProducer(self):
        """
        makeProducer when the Range header requests a single byte range
        returns an instance of SingleRangeStaticProducer.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=1-3")
        resource = self.makeResourceWithContent(b"abcdef")
        with resource.openForReading() as file:
            producer = resource.makeProducer(request, file)
            self.assertIsInstance(producer, static.SingleRangeStaticProducer)

    def test_singleRangeSets206PartialContent(self):
        """
        makeProducer when the Range header requests a single, satisfiable byte
        range sets the response code on the request to 'Partial Content'.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=1-3")
        resource = self.makeResourceWithContent(b"abcdef")
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(http.PARTIAL_CONTENT, request.responseCode)

    def test_singleRangeSetsContentHeaders(self):
        """
        makeProducer when the Range header requests a single, satisfiable byte
        range sets the Content-* headers appropriately.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=1-3")
        contentType = "text/plain"
        contentEncoding = "gzip"
        resource = self.makeResourceWithContent(
            b"abcdef", type=contentType, encoding=contentEncoding
        )
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(
                {
                    b"content-type": networkString(contentType),
                    b"content-encoding": networkString(contentEncoding),
                    b"content-range": b"bytes 1-3/6",
                    b"content-length": b"3",
                },
                self.contentHeaders(request),
            )

    def test_singleUnsatisfiableRangeReturnsSingleRangeStaticProducer(self):
        """
        makeProducer still returns an instance of L{SingleRangeStaticProducer}
        when the Range header requests a single unsatisfiable byte range.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=4-10")
        resource = self.makeResourceWithContent(b"abc")
        with resource.openForReading() as file:
            producer = resource.makeProducer(request, file)
            self.assertIsInstance(producer, static.SingleRangeStaticProducer)

    def test_singleUnsatisfiableRangeSets416ReqestedRangeNotSatisfiable(self):
        """
        makeProducer sets the response code of the request to of 'Requested
        Range Not Satisfiable' when the Range header requests a single
        unsatisfiable byte range.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=4-10")
        resource = self.makeResourceWithContent(b"abc")
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(http.REQUESTED_RANGE_NOT_SATISFIABLE, request.responseCode)

    def test_singleUnsatisfiableRangeSetsContentHeaders(self):
        """
        makeProducer when the Range header requests a single, unsatisfiable
        byte range sets the Content-* headers appropriately.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=4-10")
        contentType = "text/plain"
        resource = self.makeResourceWithContent(b"abc", type=contentType)
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(
                {
                    b"content-type": b"text/plain",
                    b"content-length": b"0",
                    b"content-range": b"bytes */3",
                },
                self.contentHeaders(request),
            )

    def test_singlePartiallyOverlappingRangeSetsContentHeaders(self):
        """
        makeProducer when the Range header requests a single byte range that
        partly overlaps the resource sets the Content-* headers appropriately.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=2-10")
        contentType = "text/plain"
        resource = self.makeResourceWithContent(b"abc", type=contentType)
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(
                {
                    b"content-type": b"text/plain",
                    b"content-length": b"1",
                    b"content-range": b"bytes 2-2/3",
                },
                self.contentHeaders(request),
            )

    def test_multipleRangeGivesMultipleRangeStaticProducer(self):
        """
        makeProducer when the Range header requests a single byte range
        returns an instance of MultipleRangeStaticProducer.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=1-3,5-6")
        resource = self.makeResourceWithContent(b"abcdef")
        with resource.openForReading() as file:
            producer = resource.makeProducer(request, file)
            self.assertIsInstance(producer, static.MultipleRangeStaticProducer)

    def test_multipleRangeSets206PartialContent(self):
        """
        makeProducer when the Range header requests a multiple satisfiable
        byte ranges sets the response code on the request to 'Partial
        Content'.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=1-3,5-6")
        resource = self.makeResourceWithContent(b"abcdef")
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(http.PARTIAL_CONTENT, request.responseCode)

    def test_mutipleRangeSetsContentHeaders(self):
        """
        makeProducer when the Range header requests a single, satisfiable byte
        range sets the Content-* headers appropriately.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=1-3,5-6")
        resource = self.makeResourceWithContent(b"abcdefghijkl", encoding="gzip")
        with resource.openForReading() as file:
            producer = resource.makeProducer(request, file)
            contentHeaders = self.contentHeaders(request)
            # The only content-* headers set are content-type and content-length.
            self.assertEqual(
                {b"content-length", b"content-type"}, set(contentHeaders.keys())
            )
            # The content-length depends on the boundary used in the response.
            expectedLength = 5
            for boundary, offset, size in producer.rangeInfo:
                expectedLength += len(boundary)
            self.assertEqual(
                b"%d" % (expectedLength,), contentHeaders[b"content-length"]
            )
            # Content-type should be set to a value indicating a multipart
            # response and the boundary used to separate the parts.
            self.assertIn(b"content-type", contentHeaders)
            contentType = contentHeaders[b"content-type"]
            self.assertNotIdentical(
                None,
                re.match(br'multipart/byteranges; boundary="[^"]*"\Z', contentType),
            )
            # Content-encoding is not set in the response to a multiple range
            # response, which is a bit wussy but works well enough with the way
            # static.File does content-encodings...
            self.assertNotIn(b"content-encoding", contentHeaders)

    def test_multipleUnsatisfiableRangesReturnsMultipleRangeStaticProducer(self):
        """
        makeProducer still returns an instance of L{SingleRangeStaticProducer}
        when the Range header requests multiple ranges, none of which are
        satisfiable.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=10-12,15-20")
        resource = self.makeResourceWithContent(b"abc")
        with resource.openForReading() as file:
            producer = resource.makeProducer(request, file)
            self.assertIsInstance(producer, static.MultipleRangeStaticProducer)

    def test_multipleUnsatisfiableRangesSets416ReqestedRangeNotSatisfiable(self):
        """
        makeProducer sets the response code of the request to of 'Requested
        Range Not Satisfiable' when the Range header requests multiple ranges,
        none of which are satisfiable.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=10-12,15-20")
        resource = self.makeResourceWithContent(b"abc")
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(http.REQUESTED_RANGE_NOT_SATISFIABLE, request.responseCode)

    def test_multipleUnsatisfiableRangeSetsContentHeaders(self):
        """
        makeProducer when the Range header requests multiple ranges, none of
        which are satisfiable, sets the Content-* headers appropriately.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=4-10")
        contentType = "text/plain"
        request.requestHeaders.addRawHeader(b"range", b"bytes=10-12,15-20")
        resource = self.makeResourceWithContent(b"abc", type=contentType)
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(
                {
                    b"content-length": b"0",
                    b"content-range": b"bytes */3",
                    b"content-type": b"text/plain",
                },
                self.contentHeaders(request),
            )

    def test_oneSatisfiableRangeIsEnough(self):
        """
        makeProducer when the Range header requests multiple ranges, at least
        one of which matches, sets the response code to 'Partial Content'.
        """
        request = DummyRequest([])
        request.requestHeaders.addRawHeader(b"range", b"bytes=1-3,100-200")
        resource = self.makeResourceWithContent(b"abcdef")
        with resource.openForReading() as file:
            resource.makeProducer(request, file)
            self.assertEqual(http.PARTIAL_CONTENT, request.responseCode)


class StaticProducerTests(TestCase):
    """
    Tests for the abstract L{StaticProducer}.
    """

    def test_stopProducingClosesFile(self):
        """
        L{StaticProducer.stopProducing} closes the file object the producer is
        producing data from.
        """
        fileObject = StringIO()
        producer = static.StaticProducer(None, fileObject)
        producer.stopProducing()
        self.assertTrue(fileObject.closed)

    def test_stopProducingSetsRequestToNone(self):
        """
        L{StaticProducer.stopProducing} sets the request instance variable to
        None, which indicates to subclasses' resumeProducing methods that no
        more data should be produced.
        """
        fileObject = StringIO()
        producer = static.StaticProducer(DummyRequest([]), fileObject)
        producer.stopProducing()
        self.assertIdentical(None, producer.request)


class NoRangeStaticProducerTests(TestCase):
    """
    Tests for L{NoRangeStaticProducer}.
    """

    def test_implementsIPullProducer(self):
        """
        L{NoRangeStaticProducer} implements L{IPullProducer}.
        """
        verifyObject(interfaces.IPullProducer, static.NoRangeStaticProducer(None, None))

    def test_resumeProducingProducesContent(self):
        """
        L{NoRangeStaticProducer.resumeProducing} writes content from the
        resource to the request.
        """
        request = DummyRequest([])
        content = b"abcdef"
        producer = static.NoRangeStaticProducer(request, StringIO(content))
        # start calls registerProducer on the DummyRequest, which pulls all
        # output from the producer and so we just need this one call.
        producer.start()
        self.assertEqual(content, b"".join(request.written))

    def test_resumeProducingBuffersOutput(self):
        """
        L{NoRangeStaticProducer.start} writes at most
        C{abstract.FileDescriptor.bufferSize} bytes of content from the
        resource to the request at once.
        """
        request = DummyRequest([])
        bufferSize = abstract.FileDescriptor.bufferSize
        content = b"a" * (2 * bufferSize + 1)
        producer = static.NoRangeStaticProducer(request, StringIO(content))
        # start calls registerProducer on the DummyRequest, which pulls all
        # output from the producer and so we just need this one call.
        producer.start()
        expected = [
            content[0:bufferSize],
            content[bufferSize : 2 * bufferSize],
            content[2 * bufferSize :],
        ]
        self.assertEqual(expected, request.written)

    def test_finishCalledWhenDone(self):
        """
        L{NoRangeStaticProducer.resumeProducing} calls finish() on the request
        after it is done producing content.
        """
        request = DummyRequest([])
        finishDeferred = request.notifyFinish()
        callbackList = []
        finishDeferred.addCallback(callbackList.append)
        producer = static.NoRangeStaticProducer(request, StringIO(b"abcdef"))
        # start calls registerProducer on the DummyRequest, which pulls all
        # output from the producer and so we just need this one call.
        producer.start()
        self.assertEqual([None], callbackList)


class SingleRangeStaticProducerTests(TestCase):
    """
    Tests for L{SingleRangeStaticProducer}.
    """

    def test_implementsIPullProducer(self):
        """
        L{SingleRangeStaticProducer} implements L{IPullProducer}.
        """
        verifyObject(
            interfaces.IPullProducer,
            static.SingleRangeStaticProducer(None, None, None, None),
        )

    def test_resumeProducingProducesContent(self):
        """
        L{SingleRangeStaticProducer.resumeProducing} writes the given amount
        of content, starting at the given offset, from the resource to the
        request.
        """
        request = DummyRequest([])
        content = b"abcdef"
        producer = static.SingleRangeStaticProducer(request, StringIO(content), 1, 3)
        # DummyRequest.registerProducer pulls all output from the producer, so
        # we just need to call start.
        producer.start()
        self.assertEqual(content[1:4], b"".join(request.written))

    def test_resumeProducingBuffersOutput(self):
        """
        L{SingleRangeStaticProducer.start} writes at most
        C{abstract.FileDescriptor.bufferSize} bytes of content from the
        resource to the request at once.
        """
        request = DummyRequest([])
        bufferSize = abstract.FileDescriptor.bufferSize
        content = b"abc" * bufferSize
        producer = static.SingleRangeStaticProducer(
            request, StringIO(content), 1, bufferSize + 10
        )
        # DummyRequest.registerProducer pulls all output from the producer, so
        # we just need to call start.
        producer.start()
        expected = [
            content[1 : bufferSize + 1],
            content[bufferSize + 1 : bufferSize + 11],
        ]
        self.assertEqual(expected, request.written)

    def test_finishCalledWhenDone(self):
        """
        L{SingleRangeStaticProducer.resumeProducing} calls finish() on the
        request after it is done producing content.
        """
        request = DummyRequest([])
        finishDeferred = request.notifyFinish()
        callbackList = []
        finishDeferred.addCallback(callbackList.append)
        producer = static.SingleRangeStaticProducer(request, StringIO(b"abcdef"), 1, 1)
        # start calls registerProducer on the DummyRequest, which pulls all
        # output from the producer and so we just need this one call.
        producer.start()
        self.assertEqual([None], callbackList)


class MultipleRangeStaticProducerTests(TestCase):
    """
    Tests for L{MultipleRangeStaticProducer}.
    """

    def test_implementsIPullProducer(self):
        """
        L{MultipleRangeStaticProducer} implements L{IPullProducer}.
        """
        verifyObject(
            interfaces.IPullProducer,
            static.MultipleRangeStaticProducer(None, None, None),
        )

    def test_resumeProducingProducesContent(self):
        """
        L{MultipleRangeStaticProducer.resumeProducing} writes the requested
        chunks of content from the resource to the request, with the supplied
        boundaries in between each chunk.
        """
        request = DummyRequest([])
        content = b"abcdef"
        producer = static.MultipleRangeStaticProducer(
            request, StringIO(content), [(b"1", 1, 3), (b"2", 5, 1)]
        )
        # DummyRequest.registerProducer pulls all output from the producer, so
        # we just need to call start.
        producer.start()
        self.assertEqual(b"1bcd2f", b"".join(request.written))

    def test_resumeProducingBuffersOutput(self):
        """
        L{MultipleRangeStaticProducer.start} writes about
        C{abstract.FileDescriptor.bufferSize} bytes of content from the
        resource to the request at once.

        To be specific about the 'about' above: it can write slightly more,
        for example in the case where the first boundary plus the first chunk
        is less than C{bufferSize} but first boundary plus the first chunk
        plus the second boundary is more, but this is unimportant as in
        practice the boundaries are fairly small.  On the other side, it is
        important for performance to bundle up several small chunks into one
        call to request.write.
        """
        request = DummyRequest([])
        content = b"0123456789" * 2
        producer = static.MultipleRangeStaticProducer(
            request, StringIO(content), [(b"a", 0, 2), (b"b", 5, 10), (b"c", 0, 0)]
        )
        producer.bufferSize = 10
        # DummyRequest.registerProducer pulls all output from the producer, so
        # we just need to call start.
        producer.start()
        expected = [
            b"a" + content[0:2] + b"b" + content[5:11],
            content[11:15] + b"c",
        ]
        self.assertEqual(expected, request.written)

    def test_finishCalledWhenDone(self):
        """
        L{MultipleRangeStaticProducer.resumeProducing} calls finish() on the
        request after it is done producing content.
        """
        request = DummyRequest([])
        finishDeferred = request.notifyFinish()
        callbackList = []
        finishDeferred.addCallback(callbackList.append)
        producer = static.MultipleRangeStaticProducer(
            request, StringIO(b"abcdef"), [(b"", 1, 2)]
        )
        # start calls registerProducer on the DummyRequest, which pulls all
        # output from the producer and so we just need this one call.
        producer.start()
        self.assertEqual([None], callbackList)


class RangeTests(TestCase):
    """
    Tests for I{Range-Header} support in L{twisted.web.static.File}.

    @type file: L{file}
    @ivar file: Temporary (binary) file containing the content to be served.

    @type resource: L{static.File}
    @ivar resource: A leaf web resource using C{file} as content.

    @type request: L{DummyRequest}
    @ivar request: A fake request, requesting C{resource}.

    @type catcher: L{list}
    @ivar catcher: List which gathers all log information.
    """

    def setUp(self):
        """
        Create a temporary file with a fixed payload of 64 bytes.  Create a
        resource for that file and create a request which will be for that
        resource.  Each test can set a different range header to test different
        aspects of the implementation.
        """
        path = FilePath(self.mktemp())
        # This is just a jumble of random stuff.  It's supposed to be a good
        # set of data for this test, particularly in order to avoid
        # accidentally seeing the right result by having a byte sequence
        # repeated at different locations or by having byte values which are
        # somehow correlated with their position in the string.
        self.payload = (
            b"\xf8u\xf3E\x8c7\xce\x00\x9e\xb6a0y0S\xf0\xef\xac\xb7"
            b"\xbe\xb5\x17M\x1e\x136k{\x1e\xbe\x0c\x07\x07\t\xd0"
            b"\xbckY\xf5I\x0b\xb8\x88oZ\x1d\x85b\x1a\xcdk\xf2\x1d"
            b"&\xfd%\xdd\x82q/A\x10Y\x8b"
        )
        path.setContent(self.payload)
        self.file = path.open()
        self.resource = static.File(self.file.name)
        self.resource.isLeaf = 1
        self.request = DummyRequest([b""])
        self.request.uri = self.file.name
        self.catcher = []
        log.addObserver(self.catcher.append)

    def tearDown(self):
        """
        Clean up the resource file and the log observer.
        """
        self.file.close()
        log.removeObserver(self.catcher.append)

    def _assertLogged(self, expected):
        """
        Asserts that a given log message occurred with an expected message.
        """
        logItem = self.catcher.pop()
        self.assertEqual(logItem["message"][0], expected)
        self.assertEqual(self.catcher, [], f"An additional log occurred: {logItem!r}")

    def test_invalidRanges(self):
        """
        L{File._parseRangeHeader} raises L{ValueError} when passed
        syntactically invalid byte ranges.
        """
        f = self.resource._parseRangeHeader

        # there's no =
        self.assertRaises(ValueError, f, b"bytes")

        # unknown isn't a valid Bytes-Unit
        self.assertRaises(ValueError, f, b"unknown=1-2")

        # there's no - in =stuff
        self.assertRaises(ValueError, f, b"bytes=3")

        # both start and end are empty
        self.assertRaises(ValueError, f, b"bytes=-")

        # start isn't an integer
        self.assertRaises(ValueError, f, b"bytes=foo-")

        # end isn't an integer
        self.assertRaises(ValueError, f, b"bytes=-foo")

        # end isn't equal to or greater than start
        self.assertRaises(ValueError, f, b"bytes=5-4")

    def test_rangeMissingStop(self):
        """
        A single bytes range without an explicit stop position is parsed into a
        two-tuple giving the start position and L{None}.
        """
        self.assertEqual(self.resource._parseRangeHeader(b"bytes=0-"), [(0, None)])

    def test_rangeMissingStart(self):
        """
        A single bytes range without an explicit start position is parsed into
        a two-tuple of L{None} and the end position.
        """
        self.assertEqual(self.resource._parseRangeHeader(b"bytes=-3"), [(None, 3)])

    def test_range(self):
        """
        A single bytes range with explicit start and stop positions is parsed
        into a two-tuple of those positions.
        """
        self.assertEqual(self.resource._parseRangeHeader(b"bytes=2-5"), [(2, 5)])

    def test_rangeWithSpace(self):
        """
        A single bytes range with whitespace in allowed places is parsed in
        the same way as it would be without the whitespace.
        """
        self.assertEqual(self.resource._parseRangeHeader(b" bytes=1-2 "), [(1, 2)])
        self.assertEqual(self.resource._parseRangeHeader(b"bytes =1-2 "), [(1, 2)])
        self.assertEqual(self.resource._parseRangeHeader(b"bytes= 1-2"), [(1, 2)])
        self.assertEqual(self.resource._parseRangeHeader(b"bytes=1 -2"), [(1, 2)])
        self.assertEqual(self.resource._parseRangeHeader(b"bytes=1- 2"), [(1, 2)])
        self.assertEqual(self.resource._parseRangeHeader(b"bytes=1-2 "), [(1, 2)])

    def test_nullRangeElements(self):
        """
        If there are multiple byte ranges but only one is non-null, the
        non-null range is parsed and its start and stop returned.
        """
        self.assertEqual(
            self.resource._parseRangeHeader(b"bytes=1-2,\r\n, ,\t"), [(1, 2)]
        )

    def test_multipleRanges(self):
        """
        If multiple byte ranges are specified their starts and stops are
        returned.
        """
        self.assertEqual(
            self.resource._parseRangeHeader(b"bytes=1-2,3-4"), [(1, 2), (3, 4)]
        )

    def test_bodyLength(self):
        """
        A correct response to a range request is as long as the length of the
        requested range.
        """
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=0-43")
        self.resource.render(self.request)
        self.assertEqual(len(b"".join(self.request.written)), 44)

    def test_invalidRangeRequest(self):
        """
        An incorrect range request (RFC 2616 defines a correct range request as
        a Bytes-Unit followed by a '=' character followed by a specific range.
        Only 'bytes' is defined) results in the range header value being logged
        and a normal 200 response being sent.
        """
        range = b"foobar=0-43"
        self.request.requestHeaders.addRawHeader(b"range", range)
        self.resource.render(self.request)
        expected = f"Ignoring malformed Range header {range.decode()!r}"
        self._assertLogged(expected)
        self.assertEqual(b"".join(self.request.written), self.payload)
        self.assertEqual(self.request.responseCode, http.OK)
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-length")[0],
            b"%d" % (len(self.payload),),
        )

    def parseMultipartBody(self, body, boundary):
        """
        Parse C{body} as a multipart MIME response separated by C{boundary}.

        Note that this with fail the calling test on certain syntactic
        problems.
        """
        sep = b"\r\n--" + boundary
        parts = body.split(sep)
        self.assertEqual(b"", parts[0])
        self.assertEqual(b"--\r\n", parts[-1])
        parsed_parts = []
        for part in parts[1:-1]:
            before, header1, header2, blank, partBody = part.split(b"\r\n", 4)
            headers = header1 + b"\n" + header2
            self.assertEqual(b"", before)
            self.assertEqual(b"", blank)
            partContentTypeValue = re.search(
                b"^content-type: (.*)$", headers, re.I | re.M
            ).group(1)
            start, end, size = re.search(
                b"^content-range: bytes ([0-9]+)-([0-9]+)/([0-9]+)$",
                headers,
                re.I | re.M,
            ).groups()
            parsed_parts.append(
                {
                    b"contentType": partContentTypeValue,
                    b"contentRange": (start, end, size),
                    b"body": partBody,
                }
            )
        return parsed_parts

    def test_multipleRangeRequest(self):
        """
        The response to a request for multiple bytes ranges is a MIME-ish
        multipart response.
        """
        startEnds = [(0, 2), (20, 30), (40, 50)]
        rangeHeaderValue = b",".join(
            [networkString(f"{s}-{e}") for (s, e) in startEnds]
        )
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=" + rangeHeaderValue)
        self.resource.render(self.request)
        self.assertEqual(self.request.responseCode, http.PARTIAL_CONTENT)
        boundary = re.match(
            b'^multipart/byteranges; boundary="(.*)"$',
            self.request.responseHeaders.getRawHeaders(b"content-type")[0],
        ).group(1)
        parts = self.parseMultipartBody(b"".join(self.request.written), boundary)
        self.assertEqual(len(startEnds), len(parts))
        for part, (s, e) in zip(parts, startEnds):
            self.assertEqual(networkString(self.resource.type), part[b"contentType"])
            start, end, size = part[b"contentRange"]
            self.assertEqual(int(start), s)
            self.assertEqual(int(end), e)
            self.assertEqual(int(size), self.resource.getFileSize())
            self.assertEqual(self.payload[s : e + 1], part[b"body"])

    def test_multipleRangeRequestWithRangeOverlappingEnd(self):
        """
        The response to a request for multiple bytes ranges is a MIME-ish
        multipart response, even when one of the ranged falls off the end of
        the resource.
        """
        startEnds = [(0, 2), (40, len(self.payload) + 10)]
        rangeHeaderValue = b",".join(
            [networkString(f"{s}-{e}") for (s, e) in startEnds]
        )
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=" + rangeHeaderValue)
        self.resource.render(self.request)
        self.assertEqual(self.request.responseCode, http.PARTIAL_CONTENT)
        boundary = re.match(
            b'^multipart/byteranges; boundary="(.*)"$',
            self.request.responseHeaders.getRawHeaders(b"content-type")[0],
        ).group(1)
        parts = self.parseMultipartBody(b"".join(self.request.written), boundary)
        self.assertEqual(len(startEnds), len(parts))
        for part, (s, e) in zip(parts, startEnds):
            self.assertEqual(networkString(self.resource.type), part[b"contentType"])
            start, end, size = part[b"contentRange"]
            self.assertEqual(int(start), s)
            self.assertEqual(int(end), min(e, self.resource.getFileSize() - 1))
            self.assertEqual(int(size), self.resource.getFileSize())
            self.assertEqual(self.payload[s : e + 1], part[b"body"])

    def test_implicitEnd(self):
        """
        If the end byte position is omitted, then it is treated as if the
        length of the resource was specified by the end byte position.
        """
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=23-")
        self.resource.render(self.request)
        self.assertEqual(b"".join(self.request.written), self.payload[23:])
        self.assertEqual(len(b"".join(self.request.written)), 41)
        self.assertEqual(self.request.responseCode, http.PARTIAL_CONTENT)
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-range")[0],
            b"bytes 23-63/64",
        )
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-length")[0], b"41"
        )

    def test_implicitStart(self):
        """
        If the start byte position is omitted but the end byte position is
        supplied, then the range is treated as requesting the last -N bytes of
        the resource, where N is the end byte position.
        """
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=-17")
        self.resource.render(self.request)
        self.assertEqual(b"".join(self.request.written), self.payload[-17:])
        self.assertEqual(len(b"".join(self.request.written)), 17)
        self.assertEqual(self.request.responseCode, http.PARTIAL_CONTENT)
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-range")[0],
            b"bytes 47-63/64",
        )
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-length")[0], b"17"
        )

    def test_explicitRange(self):
        """
        A correct response to a bytes range header request from A to B starts
        with the A'th byte and ends with (including) the B'th byte. The first
        byte of a page is numbered with 0.
        """
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=3-43")
        self.resource.render(self.request)
        written = b"".join(self.request.written)
        self.assertEqual(written, self.payload[3:44])
        self.assertEqual(self.request.responseCode, http.PARTIAL_CONTENT)
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-range")[0],
            b"bytes 3-43/64",
        )
        self.assertEqual(
            b"%d" % (len(written),),
            self.request.responseHeaders.getRawHeaders(b"content-length")[0],
        )

    def test_explicitRangeOverlappingEnd(self):
        """
        A correct response to a bytes range header request from A to B when B
        is past the end of the resource starts with the A'th byte and ends
        with the last byte of the resource. The first byte of a page is
        numbered with 0.
        """
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=40-100")
        self.resource.render(self.request)
        written = b"".join(self.request.written)
        self.assertEqual(written, self.payload[40:])
        self.assertEqual(self.request.responseCode, http.PARTIAL_CONTENT)
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-range")[0],
            b"bytes 40-63/64",
        )
        self.assertEqual(
            b"%d" % (len(written),),
            self.request.responseHeaders.getRawHeaders(b"content-length")[0],
        )

    def test_statusCodeRequestedRangeNotSatisfiable(self):
        """
        If a range is syntactically invalid due to the start being greater than
        the end, the range header is ignored (the request is responded to as if
        it were not present).
        """
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=20-13")
        self.resource.render(self.request)
        self.assertEqual(self.request.responseCode, http.OK)
        self.assertEqual(b"".join(self.request.written), self.payload)
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-length")[0],
            b"%d" % (len(self.payload),),
        )

    def test_invalidStartBytePos(self):
        """
        If a range is unsatisfiable due to the start not being less than the
        length of the resource, the response is 416 (Requested range not
        satisfiable) and no data is written to the response body (RFC 2616,
        section 14.35.1).
        """
        self.request.requestHeaders.addRawHeader(b"range", b"bytes=67-108")
        self.resource.render(self.request)
        self.assertEqual(
            self.request.responseCode, http.REQUESTED_RANGE_NOT_SATISFIABLE
        )
        self.assertEqual(b"".join(self.request.written), b"")
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-length")[0], b"0"
        )
        # Sections 10.4.17 and 14.16
        self.assertEqual(
            self.request.responseHeaders.getRawHeaders(b"content-range")[0],
            networkString("bytes */%d" % (len(self.payload),)),
        )


class DirectoryListerTests(TestCase):
    """
    Tests for L{static.DirectoryLister}.
    """

    def _request(self, uri):
        request = DummyRequest([b""])
        request.uri = uri
        return request

    def test_renderHeader(self):
        """
        L{static.DirectoryLister} prints the request uri as header of the
        rendered content.
        """
        path = FilePath(self.mktemp())
        path.makedirs()

        lister = static.DirectoryLister(path.path)
        data = lister.render(self._request(b"foo"))
        self.assertIn(b"<h1>Directory listing for foo</h1>", data)
        self.assertIn(b"<title>Directory listing for foo</title>", data)

    def test_renderUnquoteHeader(self):
        """
        L{static.DirectoryLister} unquote the request uri before printing it.
        """
        path = FilePath(self.mktemp())
        path.makedirs()

        lister = static.DirectoryLister(path.path)
        data = lister.render(self._request(b"foo%20bar"))
        self.assertIn(b"<h1>Directory listing for foo bar</h1>", data)
        self.assertIn(b"<title>Directory listing for foo bar</title>", data)

    def test_escapeHeader(self):
        """
        L{static.DirectoryLister} escape "&", "<" and ">" after unquoting the
        request uri.
        """
        path = FilePath(self.mktemp())
        path.makedirs()

        lister = static.DirectoryLister(path.path)
        data = lister.render(self._request(b"foo%26bar"))
        self.assertIn(b"<h1>Directory listing for foo&amp;bar</h1>", data)
        self.assertIn(b"<title>Directory listing for foo&amp;bar</title>", data)

    def test_renderFiles(self):
        """
        L{static.DirectoryLister} is able to list all the files inside a
        directory.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        path.child("file1").setContent(b"content1")
        path.child("file2").setContent(b"content2" * 1000)

        lister = static.DirectoryLister(path.path)
        data = lister.render(self._request(b"foo"))
        body = b"""<tr class="odd">
    <td><a href="file1">file1</a></td>
    <td>8B</td>
    <td>[text/html]</td>
    <td></td>
</tr>
<tr class="even">
    <td><a href="file2">file2</a></td>
    <td>7K</td>
    <td>[text/html]</td>
    <td></td>
</tr>"""
        self.assertIn(body, data)

    def test_renderDirectories(self):
        """
        L{static.DirectoryLister} is able to list all the directories inside
        a directory.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        path.child("dir1").makedirs()
        path.child("dir2 & 3").makedirs()

        lister = static.DirectoryLister(path.path)
        data = lister.render(self._request(b"foo"))
        body = b"""<tr class="odd">
    <td><a href="dir1/">dir1/</a></td>
    <td></td>
    <td>[Directory]</td>
    <td></td>
</tr>
<tr class="even">
    <td><a href="dir2%20%26%203/">dir2 &amp; 3/</a></td>
    <td></td>
    <td>[Directory]</td>
    <td></td>
</tr>"""
        self.assertIn(body, data)

    def test_renderFiltered(self):
        """
        L{static.DirectoryLister} takes an optional C{dirs} argument that
        filter out the list of directories and files printed.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        path.child("dir1").makedirs()
        path.child("dir2").makedirs()
        path.child("dir3").makedirs()
        lister = static.DirectoryLister(path.path, dirs=["dir1", "dir3"])
        data = lister.render(self._request(b"foo"))
        body = b"""<tr class="odd">
    <td><a href="dir1/">dir1/</a></td>
    <td></td>
    <td>[Directory]</td>
    <td></td>
</tr>
<tr class="even">
    <td><a href="dir3/">dir3/</a></td>
    <td></td>
    <td>[Directory]</td>
    <td></td>
</tr>"""
        self.assertIn(body, data)

    def test_oddAndEven(self):
        """
        L{static.DirectoryLister} gives an alternate class for each odd and
        even rows in the table.
        """
        lister = static.DirectoryLister(None)
        elements = [
            {"href": "", "text": "", "size": "", "type": "", "encoding": ""}
            for i in range(5)
        ]
        content = lister._buildTableContent(elements)

        self.assertEqual(len(content), 5)
        self.assertTrue(content[0].startswith('<tr class="odd">'))
        self.assertTrue(content[1].startswith('<tr class="even">'))
        self.assertTrue(content[2].startswith('<tr class="odd">'))
        self.assertTrue(content[3].startswith('<tr class="even">'))
        self.assertTrue(content[4].startswith('<tr class="odd">'))

    def test_contentType(self):
        """
        L{static.DirectoryLister} produces a MIME-type that indicates that it is
        HTML, and includes its charset (UTF-8).
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        lister = static.DirectoryLister(path.path)
        req = self._request(b"")
        lister.render(req)
        self.assertEqual(
            req.responseHeaders.getRawHeaders(b"content-type")[0],
            b"text/html; charset=utf-8",
        )

    def test_mimeTypeAndEncodings(self):
        """
        L{static.DirectoryLister} is able to detect mimetype and encoding of
        listed files.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        path.child("file1.txt").setContent(b"file1")
        path.child("file2.py").setContent(b"python")
        path.child("file3.conf.gz").setContent(b"conf compressed")
        path.child("file4.diff.bz2").setContent(b"diff compressed")
        directory = os.listdir(path.path)
        directory.sort()

        contentTypes = {
            ".txt": "text/plain",
            ".py": "text/python",
            ".conf": "text/configuration",
            ".diff": "text/diff",
        }

        lister = static.DirectoryLister(path.path, contentTypes=contentTypes)
        dirs, files = lister._getFilesAndDirectories(directory)
        self.assertEqual(dirs, [])
        self.assertEqual(
            files,
            [
                {
                    "encoding": "",
                    "href": "file1.txt",
                    "size": "5B",
                    "text": "file1.txt",
                    "type": "[text/plain]",
                },
                {
                    "encoding": "",
                    "href": "file2.py",
                    "size": "6B",
                    "text": "file2.py",
                    "type": "[text/python]",
                },
                {
                    "encoding": "[gzip]",
                    "href": "file3.conf.gz",
                    "size": "15B",
                    "text": "file3.conf.gz",
                    "type": "[text/configuration]",
                },
                {
                    "encoding": "[bzip2]",
                    "href": "file4.diff.bz2",
                    "size": "15B",
                    "text": "file4.diff.bz2",
                    "type": "[text/diff]",
                },
            ],
        )

    @skipIf(not platform._supportsSymlinks(), "No symlink support")
    def test_brokenSymlink(self):
        """
        If on the file in the listing points to a broken symlink, it should not
        be returned by L{static.DirectoryLister._getFilesAndDirectories}.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        file1 = path.child("file1")
        file1.setContent(b"file1")
        file1.linkTo(path.child("file2"))
        file1.remove()

        lister = static.DirectoryLister(path.path)
        directory = os.listdir(path.path)
        directory.sort()
        dirs, files = lister._getFilesAndDirectories(directory)
        self.assertEqual(dirs, [])
        self.assertEqual(files, [])

    def test_childrenNotFound(self):
        """
        Any child resource of L{static.DirectoryLister} renders an HTTP
        I{NOT FOUND} response code.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        lister = static.DirectoryLister(path.path)
        request = self._request(b"")
        child = resource.getChildForRequest(lister, request)
        result = _render(child, request)

        def cbRendered(ignored):
            self.assertEqual(request.responseCode, http.NOT_FOUND)

        result.addCallback(cbRendered)
        return result

    def test_repr(self):
        """
        L{static.DirectoryLister.__repr__} gives the path of the lister.
        """
        path = FilePath(self.mktemp())
        lister = static.DirectoryLister(path.path)
        self.assertEqual(repr(lister), f"<DirectoryLister of {path.path!r}>")
        self.assertEqual(str(lister), f"<DirectoryLister of {path.path!r}>")

    def test_formatFileSize(self):
        """
        L{static.formatFileSize} format an amount of bytes into a more readable
        format.
        """
        self.assertEqual(static.formatFileSize(0), "0B")
        self.assertEqual(static.formatFileSize(123), "123B")
        self.assertEqual(static.formatFileSize(4567), "4K")
        self.assertEqual(static.formatFileSize(8900000), "8M")
        self.assertEqual(static.formatFileSize(1234000000), "1G")
        self.assertEqual(static.formatFileSize(1234567890000), "1149G")


class LoadMimeTypesTests(TestCase):
    """
    Tests for the MIME type loading routine.

    @cvar UNSET: A sentinel to signify that C{self.paths} has not been set by
        the mock init.
    """

    UNSET = object()

    def setUp(self):
        self.paths = self.UNSET

    def _fakeInit(self, paths):
        """
        A mock L{mimetypes.init} that records the value of the passed C{paths}
        argument.

        @param paths: The paths that will be recorded.
        """
        self.paths = paths

    def test_defaultArgumentIsNone(self):
        """
        By default, L{None} is passed to C{mimetypes.init}.
        """
        static.loadMimeTypes(init=self._fakeInit)
        self.assertIdentical(self.paths, None)

    def test_extraLocationsWork(self):
        """
        Passed MIME type files are passed to C{mimetypes.init}.
        """
        paths = ["x", "y", "z"]
        static.loadMimeTypes(paths, init=self._fakeInit)
        self.assertIdentical(self.paths, paths)

    def test_usesGlobalInitFunction(self):
        """
        By default, C{mimetypes.init} is called.
        """
        # Checking mimetypes.inited doesn't always work, because
        # something, somewhere, calls mimetypes.init. Yay global
        # mutable state :)
        if getattr(inspect, "signature", None):
            signature = inspect.signature(static.loadMimeTypes)
            self.assertIs(signature.parameters["init"].default, mimetypes.init)
        else:
            args, _, _, defaults = inspect.getargspec(static.loadMimeTypes)
            defaultInit = defaults[args.index("init")]
            self.assertIs(defaultInit, mimetypes.init)


class StaticDeprecationTests(TestCase):
    def test_addSlashDeprecated(self):
        """
        L{twisted.web.static.addSlash} is deprecated.
        """
        from twisted.web.static import addSlash

        addSlash(DummyRequest([b""]))

        warnings = self.flushWarnings([self.test_addSlashDeprecated])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0]["message"],
            "twisted.web.static.addSlash was deprecated in Twisted 16.0.0",
        )
