# -*- test-case-name: twisted.web.test.test_static -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Static resources for L{twisted.web}.
"""


import errno
import itertools
import mimetypes
import os
import time
import warnings
from html import escape
from typing import Any, Callable, Dict
from urllib.parse import quote, unquote

from zope.interface import implementer

from incremental import Version

from twisted.internet import abstract, interfaces
from twisted.python import components, filepath, log
from twisted.python.compat import nativeString, networkString
from twisted.python.deprecate import deprecated
from twisted.python.runtime import platformType
from twisted.python.url import URL
from twisted.python.util import InsensitiveDict
from twisted.web import http, resource, server
from twisted.web.util import redirectTo

dangerousPathError = resource._UnsafeNoResource("Invalid request URL.")


def isDangerous(path):
    return path == b".." or b"/" in path or networkString(os.sep) in path


class Data(resource.Resource):
    """
    This is a static, in-memory resource.
    """

    def __init__(self, data, type):
        """
        @param data: The bytes that make up this data resource.
        @type data: L{bytes}

        @param type: A native string giving the Internet media type for this
            content.
        @type type: L{str}
        """
        resource.Resource.__init__(self)
        self.data = data
        self.type = type

    def render_GET(self, request):
        request.setHeader(b"content-type", networkString(self.type))
        request.setHeader(b"content-length", b"%d" % (len(self.data),))
        if request.method == b"HEAD":
            return b""
        return self.data

    render_HEAD = render_GET


@deprecated(Version("Twisted", 16, 0, 0))
def addSlash(request):
    """
    Add a trailing slash to C{request}'s URI. Deprecated, do not use.
    """
    return _addSlash(request)


def _addSlash(request):
    """
    Add a trailing slash to C{request}'s URI.

    @param request: The incoming request to add the ending slash to.
    @type request: An object conforming to L{twisted.web.iweb.IRequest}

    @return: A URI with a trailing slash, with query and fragment preserved.
    @rtype: L{bytes}
    """
    url = URL.fromText(request.uri.decode("ascii"))
    # Add an empty path segment at the end, so that it adds a trailing slash
    url = url.replace(path=list(url.path) + [""])
    return url.asText().encode("ascii")


class Redirect(resource.Resource):
    def __init__(self, request):
        resource.Resource.__init__(self)
        self.url = _addSlash(request)

    def render(self, request):
        return redirectTo(self.url, request)


class Registry(components.Componentized):
    """
    I am a Componentized object that will be made available to internal Twisted
    file-based dynamic web content such as .rpy and .epy scripts.
    """

    def __init__(self):
        components.Componentized.__init__(self)
        self._pathCache = {}

    def cachePath(self, path, rsrc):
        self._pathCache[path] = rsrc

    def getCachedPath(self, path):
        return self._pathCache.get(path)


def loadMimeTypes(mimetype_locations=None, init=mimetypes.init):
    """
    Produces a mapping of extensions (with leading dot) to MIME types.

    It does this by calling the C{init} function of the L{mimetypes} module.
    This will have the side effect of modifying the global MIME types cache
    in that module.

    Multiple file locations containing mime-types can be passed as a list.
    The files will be sourced in that order, overriding mime-types from the
    files sourced beforehand, but only if a new entry explicitly overrides
    the current entry.

    @param mimetype_locations: Optional. List of paths to C{mime.types} style
        files that should be used.
    @type mimetype_locations: iterable of paths or L{None}
    @param init: The init function to call. Defaults to the global C{init}
        function of the C{mimetypes} module. For internal use (testing) only.
    @type init: callable
    """
    init(mimetype_locations)
    mimetypes.types_map.update(
        {
            ".conf": "text/plain",
            ".diff": "text/plain",
            ".flac": "audio/x-flac",
            ".java": "text/plain",
            ".oz": "text/x-oz",
            ".swf": "application/x-shockwave-flash",
            ".wml": "text/vnd.wap.wml",
            ".xul": "application/vnd.mozilla.xul+xml",
            ".patch": "text/plain",
        }
    )
    return mimetypes.types_map


def getTypeAndEncoding(filename, types, encodings, defaultType):
    p, ext = filepath.FilePath(filename).splitext()
    ext = filepath._coerceToFilesystemEncoding("", ext.lower())
    if ext in encodings:
        enc = encodings[ext]
        ext = os.path.splitext(p)[1].lower()
    else:
        enc = None
    type = types.get(ext, defaultType)
    return type, enc


class File(resource.Resource, filepath.FilePath):
    """
    File is a resource that represents a plain non-interpreted file
    (although it can look for an extension like .rpy or .cgi and hand the
    file to a processor for interpretation if you wish). Its constructor
    takes a file path.

    Alternatively, you can give a directory path to the constructor. In this
    case the resource will represent that directory, and its children will
    be files underneath that directory. This provides access to an entire
    filesystem tree with a single Resource.

    If you map the URL 'http://server/FILE' to a resource created as
    File('/tmp'), then http://server/FILE/ will return an HTML-formatted
    listing of the /tmp/ directory, and http://server/FILE/foo/bar.html will
    return the contents of /tmp/foo/bar.html .

    @cvar childNotFound: L{Resource} used to render 404 Not Found error pages.
    @cvar forbidden: L{Resource} used to render 403 Forbidden error pages.

    @ivar contentTypes: a mapping of extensions to MIME types used to set the
        default value for the Content-Type header.
        It is initialized with the values returned by L{loadMimeTypes}.
    @type contentTypes: C{dict}

    @ivar contentEncodings: a mapping of extensions to encoding types used to
        set default value for the Content-Encoding header.
    @type contentEncodings: C{dict}
    """

    contentTypes = loadMimeTypes()

    contentEncodings = {".gz": "gzip", ".bz2": "bzip2"}

    processors: Dict[str, Callable[[str, Any], Data]] = {}

    indexNames = ["index", "index.html", "index.htm", "index.rpy"]

    type = None

    def __init__(
        self, path, defaultType="text/html", ignoredExts=(), registry=None, allowExt=0
    ):
        """
        Create a file with the given path.

        @param path: The filename of the file from which this L{File} will
            serve data.
        @type path: C{str}

        @param defaultType: A I{major/minor}-style MIME type specifier
            indicating the I{Content-Type} with which this L{File}'s data
            will be served if a MIME type cannot be determined based on
            C{path}'s extension.
        @type defaultType: C{str}

        @param ignoredExts: A sequence giving the extensions of paths in the
            filesystem which will be ignored for the purposes of child
            lookup.  For example, if C{ignoredExts} is C{(".bar",)} and
            C{path} is a directory containing a file named C{"foo.bar"}, a
            request for the C{"foo"} child of this resource will succeed
            with a L{File} pointing to C{"foo.bar"}.

        @param registry: The registry object being used to handle this
            request.  If L{None}, one will be created.
        @type registry: L{Registry}

        @param allowExt: Ignored parameter, only present for backwards
            compatibility.  Do not pass a value for this parameter.
        """
        resource.Resource.__init__(self)
        filepath.FilePath.__init__(self, path)
        self.defaultType = defaultType
        if ignoredExts in (0, 1) or allowExt:
            warnings.warn("ignoredExts should receive a list, not a boolean")
            if ignoredExts or allowExt:
                self.ignoredExts = ["*"]
            else:
                self.ignoredExts = []
        else:
            self.ignoredExts = list(ignoredExts)
        self.registry = registry or Registry()

    def ignoreExt(self, ext):
        """Ignore the given extension.

        Serve file.ext if file is requested
        """
        self.ignoredExts.append(ext)

    childNotFound = resource._UnsafeNoResource("File not found.")
    forbidden = resource._UnsafeForbiddenResource()

    def directoryListing(self):
        """
        Return a resource that generates an HTML listing of the
        directory this path represents.

        @return: A resource that renders the directory to HTML.
        @rtype: L{DirectoryLister}
        """
        path = self.path
        names = self.listNames()
        return DirectoryLister(
            path, names, self.contentTypes, self.contentEncodings, self.defaultType
        )

    def getChild(self, path, request):
        """
        If this L{File}"s path refers to a directory, return a L{File}
        referring to the file named C{path} in that directory.

        If C{path} is the empty string, return a L{DirectoryLister}
        instead.

        @param path: The current path segment.
        @type path: L{bytes}

        @param request: The incoming request.
        @type request: An that provides L{twisted.web.iweb.IRequest}.

        @return: A resource representing the requested file or
            directory, or L{NoResource} if the path cannot be
            accessed.
        @rtype: An object that provides L{resource.IResource}.
        """
        if isinstance(path, bytes):
            try:
                # Request calls urllib.unquote on each path segment,
                # leaving us with raw bytes.
                path = path.decode("utf-8")
            except UnicodeDecodeError:
                log.err(None, f"Could not decode path segment as utf-8: {path!r}")
                return self.childNotFound

        self.restat(reraise=False)

        if not self.isdir():
            return self.childNotFound

        if path:
            try:
                fpath = self.child(path)
            except filepath.InsecurePath:
                return self.childNotFound
        else:
            fpath = self.childSearchPreauth(*self.indexNames)
            if fpath is None:
                return self.directoryListing()

        if not fpath.exists():
            fpath = fpath.siblingExtensionSearch(*self.ignoredExts)
            if fpath is None:
                return self.childNotFound

        extension = fpath.splitext()[1]
        if platformType == "win32":
            # don't want .RPY to be different than .rpy, since that would allow
            # source disclosure.
            processor = InsensitiveDict(self.processors).get(extension)
        else:
            processor = self.processors.get(extension)
        if processor:
            return resource.IResource(processor(fpath.path, self.registry))
        return self.createSimilarFile(fpath.path)

    # methods to allow subclasses to e.g. decrypt files on the fly:
    def openForReading(self):
        """Open a file and return it."""
        return self.open()

    def getFileSize(self):
        """Return file size."""
        return self.getsize()

    def _parseRangeHeader(self, range):
        """
        Parse the value of a Range header into (start, stop) pairs.

        In a given pair, either of start or stop can be None, signifying that
        no value was provided, but not both.

        @return: A list C{[(start, stop)]} of pairs of length at least one.

        @raise ValueError: if the header is syntactically invalid or if the
            Bytes-Unit is anything other than "bytes'.
        """
        try:
            kind, value = range.split(b"=", 1)
        except ValueError:
            raise ValueError("Missing '=' separator")
        kind = kind.strip()
        if kind != b"bytes":
            raise ValueError(f"Unsupported Bytes-Unit: {kind!r}")
        unparsedRanges = list(filter(None, map(bytes.strip, value.split(b","))))
        parsedRanges = []
        for byteRange in unparsedRanges:
            try:
                start, end = byteRange.split(b"-", 1)
            except ValueError:
                raise ValueError(f"Invalid Byte-Range: {byteRange!r}")
            if start:
                try:
                    start = int(start)
                except ValueError:
                    raise ValueError(f"Invalid Byte-Range: {byteRange!r}")
            else:
                start = None
            if end:
                try:
                    end = int(end)
                except ValueError:
                    raise ValueError(f"Invalid Byte-Range: {byteRange!r}")
            else:
                end = None
            if start is not None:
                if end is not None and start > end:
                    # Start must be less than or equal to end or it is invalid.
                    raise ValueError(f"Invalid Byte-Range: {byteRange!r}")
            elif end is None:
                # One or both of start and end must be specified.  Omitting
                # both is invalid.
                raise ValueError(f"Invalid Byte-Range: {byteRange!r}")
            parsedRanges.append((start, end))
        return parsedRanges

    def _rangeToOffsetAndSize(self, start, end):
        """
        Convert a start and end from a Range header to an offset and size.

        This method checks that the resulting range overlaps with the resource
        being served (and so has the value of C{getFileSize()} as an indirect
        input).

        Either but not both of start or end can be L{None}:

         - Omitted start means that the end value is actually a start value
           relative to the end of the resource.

         - Omitted end means the end of the resource should be the end of
           the range.

        End is interpreted as inclusive, as per RFC 2616.

        If this range doesn't overlap with any of this resource, C{(0, 0)} is
        returned, which is not otherwise a value return value.

        @param start: The start value from the header, or L{None} if one was
            not present.
        @param end: The end value from the header, or L{None} if one was not
            present.
        @return: C{(offset, size)} where offset is how far into this resource
            this resource the range begins and size is how long the range is,
            or C{(0, 0)} if the range does not overlap this resource.
        """
        size = self.getFileSize()
        if start is None:
            start = size - end
            end = size
        elif end is None:
            end = size
        elif end < size:
            end += 1
        elif end > size:
            end = size
        if start >= size:
            start = end = 0
        return start, (end - start)

    def _contentRange(self, offset, size):
        """
        Return a string suitable for the value of a Content-Range header for a
        range with the given offset and size.

        The offset and size are not sanity checked in any way.

        @param offset: How far into this resource the range begins.
        @param size: How long the range is.
        @return: The value as appropriate for the value of a Content-Range
            header.
        """
        return networkString(
            "bytes %d-%d/%d" % (offset, offset + size - 1, self.getFileSize())
        )

    def _doSingleRangeRequest(self, request, startAndEnd):
        """
        Set up the response for Range headers that specify a single range.

        This method checks if the request is satisfiable and sets the response
        code and Content-Range header appropriately.  The return value
        indicates which part of the resource to return.

        @param request: The Request object.
        @param startAndEnd: A 2-tuple of start of the byte range as specified by
            the header and the end of the byte range as specified by the header.
            At most one of the start and end may be L{None}.
        @return: A 2-tuple of the offset and size of the range to return.
            offset == size == 0 indicates that the request is not satisfiable.
        """
        start, end = startAndEnd
        offset, size = self._rangeToOffsetAndSize(start, end)
        if offset == size == 0:
            # This range doesn't overlap with any of this resource, so the
            # request is unsatisfiable.
            request.setResponseCode(http.REQUESTED_RANGE_NOT_SATISFIABLE)
            request.setHeader(
                b"content-range", networkString("bytes */%d" % (self.getFileSize(),))
            )
        else:
            request.setResponseCode(http.PARTIAL_CONTENT)
            request.setHeader(b"content-range", self._contentRange(offset, size))
        return offset, size

    def _doMultipleRangeRequest(self, request, byteRanges):
        """
        Set up the response for Range headers that specify a single range.

        This method checks if the request is satisfiable and sets the response
        code and Content-Type and Content-Length headers appropriately.  The
        return value, which is a little complicated, indicates which parts of
        the resource to return and the boundaries that should separate the
        parts.

        In detail, the return value is a tuple rangeInfo C{rangeInfo} is a
        list of 3-tuples C{(partSeparator, partOffset, partSize)}.  The
        response to this request should be, for each element of C{rangeInfo},
        C{partSeparator} followed by C{partSize} bytes of the resource
        starting at C{partOffset}.  Each C{partSeparator} includes the
        MIME-style boundary and the part-specific Content-type and
        Content-range headers.  It is convenient to return the separator as a
        concrete string from this method, because this method needs to compute
        the number of bytes that will make up the response to be able to set
        the Content-Length header of the response accurately.

        @param request: The Request object.
        @param byteRanges: A list of C{(start, end)} values as specified by
            the header.  For each range, at most one of C{start} and C{end}
            may be L{None}.
        @return: See above.
        """
        matchingRangeFound = False
        rangeInfo = []
        contentLength = 0
        boundary = networkString(f"{int(time.time() * 1000000):x}{os.getpid():x}")
        if self.type:
            contentType = self.type
        else:
            contentType = b"bytes"  # It's what Apache does...
        for start, end in byteRanges:
            partOffset, partSize = self._rangeToOffsetAndSize(start, end)
            if partOffset == partSize == 0:
                continue
            contentLength += partSize
            matchingRangeFound = True
            partContentRange = self._contentRange(partOffset, partSize)
            partSeparator = networkString(
                (
                    "\r\n"
                    "--%s\r\n"
                    "Content-type: %s\r\n"
                    "Content-range: %s\r\n"
                    "\r\n"
                )
                % (
                    nativeString(boundary),
                    nativeString(contentType),
                    nativeString(partContentRange),
                )
            )
            contentLength += len(partSeparator)
            rangeInfo.append((partSeparator, partOffset, partSize))
        if not matchingRangeFound:
            request.setResponseCode(http.REQUESTED_RANGE_NOT_SATISFIABLE)
            request.setHeader(b"content-length", b"0")
            request.setHeader(
                b"content-range", networkString("bytes */%d" % (self.getFileSize(),))
            )
            return [], b""
        finalBoundary = b"\r\n--" + boundary + b"--\r\n"
        rangeInfo.append((finalBoundary, 0, 0))
        request.setResponseCode(http.PARTIAL_CONTENT)
        request.setHeader(
            b"content-type",
            networkString(f'multipart/byteranges; boundary="{nativeString(boundary)}"'),
        )
        request.setHeader(
            b"content-length", b"%d" % (contentLength + len(finalBoundary),)
        )
        return rangeInfo

    def _setContentHeaders(self, request, size=None):
        """
        Set the Content-length and Content-type headers for this request.

        This method is not appropriate for requests for multiple byte ranges;
        L{_doMultipleRangeRequest} will set these headers in that case.

        @param request: The L{twisted.web.http.Request} object.
        @param size: The size of the response.  If not specified, default to
            C{self.getFileSize()}.
        """
        if size is None:
            size = self.getFileSize()
        request.setHeader(b"content-length", b"%d" % (size,))
        if self.type:
            request.setHeader(b"content-type", networkString(self.type))
        if self.encoding:
            request.setHeader(b"content-encoding", networkString(self.encoding))

    def makeProducer(self, request, fileForReading):
        """
        Make a L{StaticProducer} that will produce the body of this response.

        This method will also set the response code and Content-* headers.

        @param request: The L{twisted.web.http.Request} object.
        @param fileForReading: The file object containing the resource.
        @return: A L{StaticProducer}.  Calling C{.start()} on this will begin
            producing the response.
        """
        byteRange = request.getHeader(b"range")
        if byteRange is None:
            self._setContentHeaders(request)
            request.setResponseCode(http.OK)
            return NoRangeStaticProducer(request, fileForReading)
        try:
            parsedRanges = self._parseRangeHeader(byteRange)
        except ValueError:
            log.msg(f"Ignoring malformed Range header {byteRange.decode()!r}")
            self._setContentHeaders(request)
            request.setResponseCode(http.OK)
            return NoRangeStaticProducer(request, fileForReading)

        if len(parsedRanges) == 1:
            offset, size = self._doSingleRangeRequest(request, parsedRanges[0])
            self._setContentHeaders(request, size)
            return SingleRangeStaticProducer(request, fileForReading, offset, size)
        else:
            rangeInfo = self._doMultipleRangeRequest(request, parsedRanges)
            return MultipleRangeStaticProducer(request, fileForReading, rangeInfo)

    def render_GET(self, request):
        """
        Begin sending the contents of this L{File} (or a subset of the
        contents, based on the 'range' header) to the given request.
        """
        self.restat(False)

        if self.type is None:
            self.type, self.encoding = getTypeAndEncoding(
                self.basename(),
                self.contentTypes,
                self.contentEncodings,
                self.defaultType,
            )

        if not self.exists():
            return self.childNotFound.render(request)

        if self.isdir():
            return self.redirect(request)

        request.setHeader(b"accept-ranges", b"bytes")

        try:
            fileForReading = self.openForReading()
        except OSError as e:
            if e.errno == errno.EACCES:
                return self.forbidden.render(request)
            else:
                raise

        if request.setLastModified(self.getModificationTime()) is http.CACHED:
            # `setLastModified` also sets the response code for us, so if the
            # request is cached, we close the file now that we've made sure that
            # the request would otherwise succeed and return an empty body.
            fileForReading.close()
            return b""

        if request.method == b"HEAD":
            # Set the content headers here, rather than making a producer.
            self._setContentHeaders(request)
            # We've opened the file to make sure it's accessible, so close it
            # now that we don't need it.
            fileForReading.close()
            return b""

        producer = self.makeProducer(request, fileForReading)
        producer.start()

        # and make sure the connection doesn't get closed
        return server.NOT_DONE_YET

    render_HEAD = render_GET

    def redirect(self, request):
        return redirectTo(_addSlash(request), request)

    def listNames(self):
        if not self.isdir():
            return []
        directory = self.listdir()
        directory.sort()
        return directory

    def listEntities(self):
        return list(
            map(
                lambda fileName, self=self: self.createSimilarFile(
                    os.path.join(self.path, fileName)
                ),
                self.listNames(),
            )
        )

    def createSimilarFile(self, path):
        f = self.__class__(path, self.defaultType, self.ignoredExts, self.registry)
        # refactoring by steps, here - constructor should almost certainly take these
        f.processors = self.processors
        f.indexNames = self.indexNames[:]
        f.childNotFound = self.childNotFound
        return f


@implementer(interfaces.IPullProducer)
class StaticProducer:
    """
    Superclass for classes that implement the business of producing.

    @ivar request: The L{IRequest} to write the contents of the file to.
    @ivar fileObject: The file the contents of which to write to the request.
    """

    bufferSize = abstract.FileDescriptor.bufferSize

    def __init__(self, request, fileObject):
        """
        Initialize the instance.
        """
        self.request = request
        self.fileObject = fileObject

    def start(self):
        raise NotImplementedError(self.start)

    def resumeProducing(self):
        raise NotImplementedError(self.resumeProducing)

    def stopProducing(self):
        """
        Stop producing data.

        L{twisted.internet.interfaces.IProducer.stopProducing}
        is called when our consumer has died, and subclasses also call this
        method when they are done producing data.
        """
        self.fileObject.close()
        self.request = None


class NoRangeStaticProducer(StaticProducer):
    """
    A L{StaticProducer} that writes the entire file to the request.
    """

    def start(self):
        self.request.registerProducer(self, False)

    def resumeProducing(self):
        if not self.request:
            return
        data = self.fileObject.read(self.bufferSize)
        if data:
            # this .write will spin the reactor, calling .doWrite and then
            # .resumeProducing again, so be prepared for a re-entrant call
            self.request.write(data)
        else:
            self.request.unregisterProducer()
            self.request.finish()
            self.stopProducing()


class SingleRangeStaticProducer(StaticProducer):
    """
    A L{StaticProducer} that writes a single chunk of a file to the request.
    """

    def __init__(self, request, fileObject, offset, size):
        """
        Initialize the instance.

        @param request: See L{StaticProducer}.
        @param fileObject: See L{StaticProducer}.
        @param offset: The offset into the file of the chunk to be written.
        @param size: The size of the chunk to write.
        """
        StaticProducer.__init__(self, request, fileObject)
        self.offset = offset
        self.size = size

    def start(self):
        self.fileObject.seek(self.offset)
        self.bytesWritten = 0
        self.request.registerProducer(self, 0)

    def resumeProducing(self):
        if not self.request:
            return
        data = self.fileObject.read(min(self.bufferSize, self.size - self.bytesWritten))
        if data:
            self.bytesWritten += len(data)
            # this .write will spin the reactor, calling .doWrite and then
            # .resumeProducing again, so be prepared for a re-entrant call
            self.request.write(data)
        if self.request and self.bytesWritten == self.size:
            self.request.unregisterProducer()
            self.request.finish()
            self.stopProducing()


class MultipleRangeStaticProducer(StaticProducer):
    """
    A L{StaticProducer} that writes several chunks of a file to the request.
    """

    def __init__(self, request, fileObject, rangeInfo):
        """
        Initialize the instance.

        @param request: See L{StaticProducer}.
        @param fileObject: See L{StaticProducer}.
        @param rangeInfo: A list of tuples C{[(boundary, offset, size)]}
            where:
             - C{boundary} will be written to the request first.
             - C{offset} the offset into the file of chunk to write.
             - C{size} the size of the chunk to write.
        """
        StaticProducer.__init__(self, request, fileObject)
        self.rangeInfo = rangeInfo

    def start(self):
        self.rangeIter = iter(self.rangeInfo)
        self._nextRange()
        self.request.registerProducer(self, 0)

    def _nextRange(self):
        self.partBoundary, partOffset, self._partSize = next(self.rangeIter)
        self._partBytesWritten = 0
        self.fileObject.seek(partOffset)

    def resumeProducing(self):
        if not self.request:
            return
        data = []
        dataLength = 0
        done = False
        while dataLength < self.bufferSize:
            if self.partBoundary:
                dataLength += len(self.partBoundary)
                data.append(self.partBoundary)
                self.partBoundary = None
            p = self.fileObject.read(
                min(
                    self.bufferSize - dataLength,
                    self._partSize - self._partBytesWritten,
                )
            )
            self._partBytesWritten += len(p)
            dataLength += len(p)
            data.append(p)
            if self.request and self._partBytesWritten == self._partSize:
                try:
                    self._nextRange()
                except StopIteration:
                    done = True
                    break
        self.request.write(b"".join(data))
        if done:
            self.request.unregisterProducer()
            self.request.finish()
            self.stopProducing()


class ASISProcessor(resource.Resource):
    """
    Serve files exactly as responses without generating a status-line or any
    headers.  Inspired by Apache's mod_asis.
    """

    def __init__(self, path, registry=None):
        resource.Resource.__init__(self)
        self.path = path
        self.registry = registry or Registry()

    def render(self, request):
        request.startedWriting = 1
        res = File(self.path, registry=self.registry)
        return res.render(request)


def formatFileSize(size):
    """
    Format the given file size in bytes to human readable format.
    """
    if size < 1024:
        return "%iB" % size
    elif size < (1024 ** 2):
        return "%iK" % (size / 1024)
    elif size < (1024 ** 3):
        return "%iM" % (size / (1024 ** 2))
    else:
        return "%iG" % (size / (1024 ** 3))


class DirectoryLister(resource.Resource):
    """
    Print the content of a directory.

    @ivar template: page template used to render the content of the directory.
        It must contain the format keys B{header} and B{tableContent}.
    @type template: C{str}

    @ivar linePattern: template used to render one line in the listing table.
        It must contain the format keys B{class}, B{href}, B{text}, B{size},
        B{type} and B{encoding}.
    @type linePattern: C{str}

    @ivar contentTypes: a mapping of extensions to MIME types used to populate
        the information of a member of this directory.
        It is initialized with the value L{File.contentTypes}.
    @type contentTypes: C{dict}

    @ivar contentEncodings: a mapping of extensions to encoding types.
        It is initialized with the value L{File.contentEncodings}.
    @type contentEncodings: C{dict}

    @ivar defaultType: default type used when no mimetype is detected.
    @type defaultType: C{str}

    @ivar dirs: filtered content of C{path}, if the whole content should not be
        displayed (default to L{None}, which means the actual content of
        C{path} is printed).
    @type dirs: L{None} or C{list}

    @ivar path: directory which content should be listed.
    @type path: C{str}
    """

    template = """<html>
<head>
<title>%(header)s</title>
<style>
.even-dir { background-color: #efe0ef }
.even { background-color: #eee }
.odd-dir {background-color: #f0d0ef }
.odd { background-color: #dedede }
.icon { text-align: center }
.listing {
    margin-left: auto;
    margin-right: auto;
    width: 50%%;
    padding: 0.1em;
    }

body { border: 0; padding: 0; margin: 0; background-color: #efefef; }
h1 {padding: 0.1em; background-color: #777; color: white; border-bottom: thin white dashed;}

</style>
</head>

<body>
<h1>%(header)s</h1>

<table>
    <thead>
        <tr>
            <th>Filename</th>
            <th>Size</th>
            <th>Content type</th>
            <th>Content encoding</th>
        </tr>
    </thead>
    <tbody>
%(tableContent)s
    </tbody>
</table>

</body>
</html>
"""

    linePattern = """<tr class="%(class)s">
    <td><a href="%(href)s">%(text)s</a></td>
    <td>%(size)s</td>
    <td>%(type)s</td>
    <td>%(encoding)s</td>
</tr>
"""

    def __init__(
        self,
        pathname,
        dirs=None,
        contentTypes=File.contentTypes,
        contentEncodings=File.contentEncodings,
        defaultType="text/html",
    ):
        resource.Resource.__init__(self)
        self.contentTypes = contentTypes
        self.contentEncodings = contentEncodings
        self.defaultType = defaultType
        # dirs allows usage of the File to specify what gets listed
        self.dirs = dirs
        self.path = pathname

    def _getFilesAndDirectories(self, directory):
        """
        Helper returning files and directories in given directory listing, with
        attributes to be used to build a table content with
        C{self.linePattern}.

        @return: tuple of (directories, files)
        @rtype: C{tuple} of C{list}
        """
        files = []
        dirs = []

        for path in directory:
            if isinstance(path, bytes):
                path = path.decode("utf8")

            url = quote(path, "/")
            escapedPath = escape(path)
            childPath = filepath.FilePath(self.path).child(path)

            if childPath.isdir():
                dirs.append(
                    {
                        "text": escapedPath + "/",
                        "href": url + "/",
                        "size": "",
                        "type": "[Directory]",
                        "encoding": "",
                    }
                )
            else:
                mimetype, encoding = getTypeAndEncoding(
                    path, self.contentTypes, self.contentEncodings, self.defaultType
                )
                try:
                    size = childPath.getsize()
                except OSError:
                    continue
                files.append(
                    {
                        "text": escapedPath,
                        "href": url,
                        "type": "[%s]" % mimetype,
                        "encoding": (encoding and "[%s]" % encoding or ""),
                        "size": formatFileSize(size),
                    }
                )
        return dirs, files

    def _buildTableContent(self, elements):
        """
        Build a table content using C{self.linePattern} and giving elements odd
        and even classes.
        """
        tableContent = []
        rowClasses = itertools.cycle(["odd", "even"])
        for element, rowClass in zip(elements, rowClasses):
            element["class"] = rowClass
            tableContent.append(self.linePattern % element)
        return tableContent

    def render(self, request):
        """
        Render a listing of the content of C{self.path}.
        """
        request.setHeader(b"content-type", b"text/html; charset=utf-8")
        if self.dirs is None:
            directory = os.listdir(self.path)
            directory.sort()
        else:
            directory = self.dirs

        dirs, files = self._getFilesAndDirectories(directory)

        tableContent = "".join(self._buildTableContent(dirs + files))

        header = "Directory listing for {}".format(
            escape(unquote(nativeString(request.uri))),
        )

        done = self.template % {"header": header, "tableContent": tableContent}
        done = done.encode("utf8")

        return done

    def __repr__(self) -> str:
        return "<DirectoryLister of %r>" % self.path

    __str__ = __repr__
