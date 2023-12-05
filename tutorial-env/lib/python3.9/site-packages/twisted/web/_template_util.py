# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
twisted.web.util and twisted.web.template merged to avoid cyclic deps
"""

import io
import linecache
import warnings
from collections import OrderedDict
from html import escape
from typing import (
    IO,
    Any,
    AnyStr,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Tuple,
    Union,
    cast,
)
from xml.sax import handler, make_parser
from xml.sax.xmlreader import Locator

from zope.interface import implementer

from twisted.internet.defer import Deferred
from twisted.logger import Logger
from twisted.python import urlpath
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.python.reflect import fullyQualifiedName
from twisted.web import resource
from twisted.web._element import Element, renderer
from twisted.web._flatten import Flattenable, flatten, flattenString
from twisted.web._stan import CDATA, Comment, Tag, slot
from twisted.web.iweb import IRenderable, IRequest, ITemplateLoader


def _PRE(text):
    """
    Wraps <pre> tags around some text and HTML-escape it.

    This is here since once twisted.web.html was deprecated it was hard to
    migrate the html.PRE from current code to twisted.web.template.

    For new code consider using twisted.web.template.

    @return: Escaped text wrapped in <pre> tags.
    @rtype: C{str}
    """
    return f"<pre>{escape(text)}</pre>"


def redirectTo(URL: bytes, request: IRequest) -> bytes:
    """
    Generate a redirect to the given location.

    @param URL: A L{bytes} giving the location to which to redirect.

    @param request: The request object to use to generate the redirect.
    @type request: L{IRequest<twisted.web.iweb.IRequest>} provider

    @raise TypeError: If the type of C{URL} a L{str} instead of L{bytes}.

    @return: A L{bytes} containing HTML which tries to convince the client
        agent
        to visit the new location even if it doesn't respect the I{FOUND}
        response code.  This is intended to be returned from a render method,
        eg::

            def render_GET(self, request):
                return redirectTo(b"http://example.com/", request)
    """
    if not isinstance(URL, bytes):
        raise TypeError("URL must be bytes")
    request.setHeader(b"Content-Type", b"text/html; charset=utf-8")
    request.redirect(URL)
    # FIXME: The URL should be HTML-escaped.
    # https://twistedmatrix.com/trac/ticket/9839
    content = b"""
<html>
    <head>
        <meta http-equiv=\"refresh\" content=\"0;URL=%(url)s\">
    </head>
    <body bgcolor=\"#FFFFFF\" text=\"#000000\">
    <a href=\"%(url)s\">click here</a>
    </body>
</html>
""" % {
        b"url": URL
    }
    return content


class Redirect(resource.Resource):
    """
    Resource that redirects to a specific URL.

    @ivar url: Redirect target URL to put in the I{Location} response header.
    @type url: L{bytes}
    """

    isLeaf = True

    def __init__(self, url: bytes):
        super().__init__()
        self.url = url

    def render(self, request):
        return redirectTo(self.url, request)

    def getChild(self, name, request):
        return self


# FIXME: This is totally broken, see https://twistedmatrix.com/trac/ticket/9838
class ChildRedirector(Redirect):
    isLeaf = False

    def __init__(self, url):
        # XXX is this enough?
        if (
            (url.find("://") == -1)
            and (not url.startswith(".."))
            and (not url.startswith("/"))
        ):
            raise ValueError(
                (
                    "It seems you've given me a redirect (%s) that is a child of"
                    " myself! That's not good, it'll cause an infinite redirect."
                )
                % url
            )
        Redirect.__init__(self, url)

    def getChild(self, name, request):
        newUrl = self.url
        if not newUrl.endswith("/"):
            newUrl += "/"
        newUrl += name
        return ChildRedirector(newUrl)


class ParentRedirect(resource.Resource):
    """
    Redirect to the nearest directory and strip any query string.

    This generates redirects like::

        /              \u2192  /
        /foo           \u2192  /
        /foo?bar       \u2192  /
        /foo/          \u2192  /foo/
        /foo/bar       \u2192  /foo/
        /foo/bar?baz   \u2192  /foo/

    However, the generated I{Location} header contains an absolute URL rather
    than a path.

    The response is the same regardless of HTTP method.
    """

    isLeaf = 1

    def render(self, request: IRequest) -> bytes:
        """
        Respond to all requests by redirecting to nearest directory.
        """
        here = str(urlpath.URLPath.fromRequest(request).here()).encode("ascii")
        return redirectTo(here, request)


class DeferredResource(resource.Resource):
    """
    I wrap up a Deferred that will eventually result in a Resource
    object.
    """

    isLeaf = 1

    def __init__(self, d):
        resource.Resource.__init__(self)
        self.d = d

    def getChild(self, name, request):
        return self

    def render(self, request):
        self.d.addCallback(self._cbChild, request).addErrback(self._ebChild, request)
        from twisted.web.server import NOT_DONE_YET

        return NOT_DONE_YET

    def _cbChild(self, child, request):
        request.render(resource.getChildForRequest(child, request))

    def _ebChild(self, reason, request):
        request.processingFailed(reason)


class _SourceLineElement(Element):
    """
    L{_SourceLineElement} is an L{IRenderable} which can render a single line of
    source code.

    @ivar number: A C{int} giving the line number of the source code to be
        rendered.
    @ivar source: A C{str} giving the source code to be rendered.
    """

    def __init__(self, loader, number, source):
        Element.__init__(self, loader)
        self.number = number
        self.source = source

    @renderer
    def sourceLine(self, request, tag):
        """
        Render the line of source as a child of C{tag}.
        """
        return tag(self.source.replace("  ", " \N{NO-BREAK SPACE}"))

    @renderer
    def lineNumber(self, request, tag):
        """
        Render the line number as a child of C{tag}.
        """
        return tag(str(self.number))


class _SourceFragmentElement(Element):
    """
    L{_SourceFragmentElement} is an L{IRenderable} which can render several lines
    of source code near the line number of a particular frame object.

    @ivar frame: A L{Failure<twisted.python.failure.Failure>}-style frame object
        for which to load a source line to render.  This is really a tuple
        holding some information from a frame object.  See
        L{Failure.frames<twisted.python.failure.Failure>} for specifics.
    """

    def __init__(self, loader, frame):
        Element.__init__(self, loader)
        self.frame = frame

    def _getSourceLines(self):
        """
        Find the source line references by C{self.frame} and yield, in source
        line order, it and the previous and following lines.

        @return: A generator which yields two-tuples.  Each tuple gives a source
            line number and the contents of that source line.
        """
        filename = self.frame[1]
        lineNumber = self.frame[2]
        for snipLineNumber in range(lineNumber - 1, lineNumber + 2):
            yield (snipLineNumber, linecache.getline(filename, snipLineNumber).rstrip())

    @renderer
    def sourceLines(self, request, tag):
        """
        Render the source line indicated by C{self.frame} and several
        surrounding lines.  The active line will be given a I{class} of
        C{"snippetHighlightLine"}.  Other lines will be given a I{class} of
        C{"snippetLine"}.
        """
        for (lineNumber, sourceLine) in self._getSourceLines():
            newTag = tag.clone()
            if lineNumber == self.frame[2]:
                cssClass = "snippetHighlightLine"
            else:
                cssClass = "snippetLine"
            loader = TagLoader(newTag(**{"class": cssClass}))
            yield _SourceLineElement(loader, lineNumber, sourceLine)


class _FrameElement(Element):
    """
    L{_FrameElement} is an L{IRenderable} which can render details about one
    frame from a L{Failure<twisted.python.failure.Failure>}.

    @ivar frame: A L{Failure<twisted.python.failure.Failure>}-style frame object
        for which to load a source line to render.  This is really a tuple
        holding some information from a frame object.  See
        L{Failure.frames<twisted.python.failure.Failure>} for specifics.
    """

    def __init__(self, loader, frame):
        Element.__init__(self, loader)
        self.frame = frame

    @renderer
    def filename(self, request, tag):
        """
        Render the name of the file this frame references as a child of C{tag}.
        """
        return tag(self.frame[1])

    @renderer
    def lineNumber(self, request, tag):
        """
        Render the source line number this frame references as a child of
        C{tag}.
        """
        return tag(str(self.frame[2]))

    @renderer
    def function(self, request, tag):
        """
        Render the function name this frame references as a child of C{tag}.
        """
        return tag(self.frame[0])

    @renderer
    def source(self, request, tag):
        """
        Render the source code surrounding the line this frame references,
        replacing C{tag}.
        """
        return _SourceFragmentElement(TagLoader(tag), self.frame)


class _StackElement(Element):
    """
    L{_StackElement} renders an L{IRenderable} which can render a list of frames.
    """

    def __init__(self, loader, stackFrames):
        Element.__init__(self, loader)
        self.stackFrames = stackFrames

    @renderer
    def frames(self, request, tag):
        """
        Render the list of frames in this L{_StackElement}, replacing C{tag}.
        """
        return [
            _FrameElement(TagLoader(tag.clone()), frame) for frame in self.stackFrames
        ]


class _NSContext:
    """
    A mapping from XML namespaces onto their prefixes in the document.
    """

    def __init__(self, parent: Optional["_NSContext"] = None):
        """
        Pull out the parent's namespaces, if there's no parent then default to
        XML.
        """
        self.parent = parent
        if parent is not None:
            self.nss: Dict[Optional[str], Optional[str]] = OrderedDict(parent.nss)
        else:
            self.nss = {"http://www.w3.org/XML/1998/namespace": "xml"}

    def get(self, k: Optional[str], d: Optional[str] = None) -> Optional[str]:
        """
        Get a prefix for a namespace.

        @param d: The default prefix value.
        """
        return self.nss.get(k, d)

    def __setitem__(self, k: Optional[str], v: Optional[str]) -> None:
        """
        Proxy through to setting the prefix for the namespace.
        """
        self.nss.__setitem__(k, v)

    def __getitem__(self, k: Optional[str]) -> Optional[str]:
        """
        Proxy through to getting the prefix for the namespace.
        """
        return self.nss.__getitem__(k)


TEMPLATE_NAMESPACE = "http://twistedmatrix.com/ns/twisted.web.template/0.1"


class _ToStan(handler.ContentHandler, handler.EntityResolver):
    """
    A SAX parser which converts an XML document to the Twisted STAN
    Document Object Model.
    """

    def __init__(self, sourceFilename: Optional[str]):
        """
        @param sourceFilename: the filename the XML was loaded out of.
        """
        self.sourceFilename = sourceFilename
        self.prefixMap = _NSContext()
        self.inCDATA = False

    def setDocumentLocator(self, locator: Locator) -> None:
        """
        Set the document locator, which knows about line and character numbers.
        """
        self.locator = locator

    def startDocument(self) -> None:
        """
        Initialise the document.
        """
        # Depending on our active context, the element type can be Tag, slot
        # or str. Since mypy doesn't understand that context, it would be
        # a pain to not use Any here.
        self.document: List[Any] = []
        self.current = self.document
        self.stack: List[Any] = []
        self.xmlnsAttrs: List[Tuple[str, str]] = []

    def endDocument(self) -> None:
        """
        Document ended.
        """

    def processingInstruction(self, target: str, data: str) -> None:
        """
        Processing instructions are ignored.
        """

    def startPrefixMapping(self, prefix: Optional[str], uri: str) -> None:
        """
        Set up the prefix mapping, which maps fully qualified namespace URIs
        onto namespace prefixes.

        This gets called before startElementNS whenever an C{xmlns} attribute
        is seen.
        """

        self.prefixMap = _NSContext(self.prefixMap)
        self.prefixMap[uri] = prefix

        # Ignore the template namespace; we'll replace those during parsing.
        if uri == TEMPLATE_NAMESPACE:
            return

        # Add to a list that will be applied once we have the element.
        if prefix is None:
            self.xmlnsAttrs.append(("xmlns", uri))
        else:
            self.xmlnsAttrs.append(("xmlns:%s" % prefix, uri))

    def endPrefixMapping(self, prefix: Optional[str]) -> None:
        """
        "Pops the stack" on the prefix mapping.

        Gets called after endElementNS.
        """
        parent = self.prefixMap.parent
        assert parent is not None, "More prefix mapping ends than starts"
        self.prefixMap = parent

    def startElementNS(
        self,
        namespaceAndName: Tuple[str, str],
        qname: Optional[str],
        attrs: Mapping[Tuple[Optional[str], str], str],
    ) -> None:
        """
        Gets called when we encounter a new xmlns attribute.

        @param namespaceAndName: a (namespace, name) tuple, where name
            determines which type of action to take, if the namespace matches
            L{TEMPLATE_NAMESPACE}.
        @param qname: ignored.
        @param attrs: attributes on the element being started.
        """

        filename = self.sourceFilename
        lineNumber = self.locator.getLineNumber()
        columnNumber = self.locator.getColumnNumber()

        ns, name = namespaceAndName
        if ns == TEMPLATE_NAMESPACE:
            if name == "transparent":
                name = ""
            elif name == "slot":
                default: Optional[str]
                try:
                    # Try to get the default value for the slot
                    default = attrs[(None, "default")]
                except KeyError:
                    # If there wasn't one, then use None to indicate no
                    # default.
                    default = None
                sl = slot(
                    attrs[(None, "name")],
                    default=default,
                    filename=filename,
                    lineNumber=lineNumber,
                    columnNumber=columnNumber,
                )
                self.stack.append(sl)
                self.current.append(sl)
                self.current = sl.children
                return

        render = None

        attrs = OrderedDict(attrs)
        for k, v in list(attrs.items()):
            attrNS, justTheName = k
            if attrNS != TEMPLATE_NAMESPACE:
                continue
            if justTheName == "render":
                render = v
                del attrs[k]

        # nonTemplateAttrs is a dictionary mapping attributes that are *not* in
        # TEMPLATE_NAMESPACE to their values.  Those in TEMPLATE_NAMESPACE were
        # just removed from 'attrs' in the loop immediately above.  The key in
        # nonTemplateAttrs is either simply the attribute name (if it was not
        # specified as having a namespace in the template) or prefix:name,
        # preserving the xml namespace prefix given in the document.

        nonTemplateAttrs = OrderedDict()
        for (attrNs, attrName), v in attrs.items():
            nsPrefix = self.prefixMap.get(attrNs)
            if nsPrefix is None:
                attrKey = attrName
            else:
                attrKey = f"{nsPrefix}:{attrName}"
            nonTemplateAttrs[attrKey] = v

        if ns == TEMPLATE_NAMESPACE and name == "attr":
            if not self.stack:
                # TODO: define a better exception for this?
                raise AssertionError(
                    f"<{{{TEMPLATE_NAMESPACE}}}attr> as top-level element"
                )
            if "name" not in nonTemplateAttrs:
                # TODO: same here
                raise AssertionError(
                    f"<{{{TEMPLATE_NAMESPACE}}}attr> requires a name attribute"
                )
            el = Tag(
                "",
                render=render,
                filename=filename,
                lineNumber=lineNumber,
                columnNumber=columnNumber,
            )
            self.stack[-1].attributes[nonTemplateAttrs["name"]] = el
            self.stack.append(el)
            self.current = el.children
            return

        # Apply any xmlns attributes
        if self.xmlnsAttrs:
            nonTemplateAttrs.update(OrderedDict(self.xmlnsAttrs))
            self.xmlnsAttrs = []

        # Add the prefix that was used in the parsed template for non-template
        # namespaces (which will not be consumed anyway).
        if ns != TEMPLATE_NAMESPACE and ns is not None:
            prefix = self.prefixMap[ns]
            if prefix is not None:
                name = f"{self.prefixMap[ns]}:{name}"
        el = Tag(
            name,
            attributes=OrderedDict(
                cast(Mapping[Union[bytes, str], str], nonTemplateAttrs)
            ),
            render=render,
            filename=filename,
            lineNumber=lineNumber,
            columnNumber=columnNumber,
        )
        self.stack.append(el)
        self.current.append(el)
        self.current = el.children

    def characters(self, ch: str) -> None:
        """
        Called when we receive some characters.  CDATA characters get passed
        through as is.
        """
        if self.inCDATA:
            self.stack[-1].append(ch)
            return
        self.current.append(ch)

    def endElementNS(self, name: Tuple[str, str], qname: Optional[str]) -> None:
        """
        A namespace tag is closed.  Pop the stack, if there's anything left in
        it, otherwise return to the document's namespace.
        """
        self.stack.pop()
        if self.stack:
            self.current = self.stack[-1].children
        else:
            self.current = self.document

    def startDTD(self, name: str, publicId: str, systemId: str) -> None:
        """
        DTDs are ignored.
        """

    def endDTD(self, *args: object) -> None:
        """
        DTDs are ignored.
        """

    def startCDATA(self) -> None:
        """
        We're starting to be in a CDATA element, make a note of this.
        """
        self.inCDATA = True
        self.stack.append([])

    def endCDATA(self) -> None:
        """
        We're no longer in a CDATA element.  Collect up the characters we've
        parsed and put them in a new CDATA object.
        """
        self.inCDATA = False
        comment = "".join(self.stack.pop())
        self.current.append(CDATA(comment))

    def comment(self, content: str) -> None:
        """
        Add an XML comment which we've encountered.
        """
        self.current.append(Comment(content))


def _flatsaxParse(fl: Union[IO[AnyStr], str]) -> List["Flattenable"]:
    """
    Perform a SAX parse of an XML document with the _ToStan class.

    @param fl: The XML document to be parsed.

    @return: a C{list} of Stan objects.
    """
    parser = make_parser()
    parser.setFeature(handler.feature_validation, 0)
    parser.setFeature(handler.feature_namespaces, 1)
    parser.setFeature(handler.feature_external_ges, 0)
    parser.setFeature(handler.feature_external_pes, 0)

    s = _ToStan(getattr(fl, "name", None))
    parser.setContentHandler(s)
    parser.setEntityResolver(s)
    parser.setProperty(handler.property_lexical_handler, s)

    parser.parse(fl)

    return s.document


@implementer(ITemplateLoader)
class XMLString:
    """
    An L{ITemplateLoader} that loads and parses XML from a string.
    """

    def __init__(self, s: Union[str, bytes]):
        """
        Run the parser on a L{io.StringIO} copy of the string.

        @param s: The string from which to load the XML.
        @type s: L{str}, or a UTF-8 encoded L{bytes}.
        """
        if not isinstance(s, str):
            s = s.decode("utf8")

        self._loadedTemplate: List["Flattenable"] = _flatsaxParse(io.StringIO(s))
        """The loaded document."""

    def load(self) -> List["Flattenable"]:
        """
        Return the document.

        @return: the loaded document.
        """
        return self._loadedTemplate


class FailureElement(Element):
    """
    L{FailureElement} is an L{IRenderable} which can render detailed information
    about a L{Failure<twisted.python.failure.Failure>}.

    @ivar failure: The L{Failure<twisted.python.failure.Failure>} instance which
        will be rendered.

    @since: 12.1
    """

    loader = XMLString(
        """
<div xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">
  <style type="text/css">
    div.error {
      color: red;
      font-family: Verdana, Arial, helvetica, sans-serif;
      font-weight: bold;
    }

    div {
      font-family: Verdana, Arial, helvetica, sans-serif;
    }

    div.stackTrace {
    }

    div.frame {
      padding: 1em;
      background: white;
      border-bottom: thin black dashed;
    }

    div.frame:first-child {
      padding: 1em;
      background: white;
      border-top: thin black dashed;
      border-bottom: thin black dashed;
    }

    div.location {
    }

    span.function {
      font-weight: bold;
      font-family: "Courier New", courier, monospace;
    }

    div.snippet {
      margin-bottom: 0.5em;
      margin-left: 1em;
      background: #FFFFDD;
    }

    div.snippetHighlightLine {
      color: red;
    }

    span.code {
      font-family: "Courier New", courier, monospace;
    }
  </style>

  <div class="error">
    <span t:render="type" />: <span t:render="value" />
  </div>
  <div class="stackTrace" t:render="traceback">
    <div class="frame" t:render="frames">
      <div class="location">
        <span t:render="filename" />:<span t:render="lineNumber" /> in
        <span class="function" t:render="function" />
      </div>
      <div class="snippet" t:render="source">
        <div t:render="sourceLines">
          <span class="lineno" t:render="lineNumber" />
          <code class="code" t:render="sourceLine" />
        </div>
      </div>
    </div>
  </div>
  <div class="error">
    <span t:render="type" />: <span t:render="value" />
  </div>
</div>
"""
    )

    def __init__(self, failure, loader=None):
        Element.__init__(self, loader)
        self.failure = failure

    @renderer
    def type(self, request, tag):
        """
        Render the exception type as a child of C{tag}.
        """
        return tag(fullyQualifiedName(self.failure.type))

    @renderer
    def value(self, request, tag):
        """
        Render the exception value as a child of C{tag}.
        """
        return tag(str(self.failure.value).encode("utf8"))

    @renderer
    def traceback(self, request, tag):
        """
        Render all the frames in the wrapped
        L{Failure<twisted.python.failure.Failure>}'s traceback stack, replacing
        C{tag}.
        """
        return _StackElement(TagLoader(tag), self.failure.frames)


def formatFailure(myFailure):
    """
    Construct an HTML representation of the given failure.

    Consider using L{FailureElement} instead.

    @type myFailure: L{Failure<twisted.python.failure.Failure>}

    @rtype: L{bytes}
    @return: A string containing the HTML representation of the given failure.
    """
    result = []
    flattenString(None, FailureElement(myFailure)).addBoth(result.append)
    if isinstance(result[0], bytes):
        # Ensure the result string is all ASCII, for compatibility with the
        # default encoding expected by browsers.
        return result[0].decode("utf-8").encode("ascii", "xmlcharrefreplace")
    result[0].raiseException()


# Go read the definition of NOT_DONE_YET. For lulz. This is totally
# equivalent. And this turns out to be necessary, because trying to import
# NOT_DONE_YET in this module causes a circular import which we cannot escape
# from. From which we cannot escape. Etc. glyph is okay with this solution for
# now, and so am I, as long as this comment stays to explain to future
# maintainers what it means. ~ C.
#
# See http://twistedmatrix.com/trac/ticket/5557 for progress on fixing this.
NOT_DONE_YET = 1
_moduleLog = Logger()


@implementer(ITemplateLoader)
class TagLoader:
    """
    An L{ITemplateLoader} that loads an existing flattenable object.
    """

    def __init__(self, tag: "Flattenable"):
        """
        @param tag: The object which will be loaded.
        """

        self.tag: "Flattenable" = tag
        """The object which will be loaded."""

    def load(self) -> List["Flattenable"]:
        return [self.tag]


@implementer(ITemplateLoader)
class XMLFile:
    """
    An L{ITemplateLoader} that loads and parses XML from a file.
    """

    def __init__(self, path: FilePath):
        """
        Run the parser on a file.

        @param path: The file from which to load the XML.
        """
        if not isinstance(path, FilePath):
            warnings.warn(  # type: ignore[unreachable]
                "Passing filenames or file objects to XMLFile is deprecated "
                "since Twisted 12.1.  Pass a FilePath instead.",
                category=DeprecationWarning,
                stacklevel=2,
            )

        self._loadedTemplate: Optional[List["Flattenable"]] = None
        """The loaded document, or L{None}, if not loaded."""

        self._path: FilePath = path
        """The file that is being loaded from."""

    def _loadDoc(self) -> List["Flattenable"]:
        """
        Read and parse the XML.

        @return: the loaded document.
        """
        if not isinstance(self._path, FilePath):
            return _flatsaxParse(self._path)  # type: ignore[unreachable]
        else:
            with self._path.open("r") as f:
                return _flatsaxParse(f)

    def __repr__(self) -> str:
        return f"<XMLFile of {self._path!r}>"

    def load(self) -> List["Flattenable"]:
        """
        Return the document, first loading it if necessary.

        @return: the loaded document.
        """
        if self._loadedTemplate is None:
            self._loadedTemplate = self._loadDoc()
        return self._loadedTemplate


# Last updated October 2011, using W3Schools as a reference. Link:
# http://www.w3schools.com/html5/html5_reference.asp
# Note that <xmp> is explicitly omitted; its semantics do not work with
# t.w.template and it is officially deprecated.
VALID_HTML_TAG_NAMES = {
    "a",
    "abbr",
    "acronym",
    "address",
    "applet",
    "area",
    "article",
    "aside",
    "audio",
    "b",
    "base",
    "basefont",
    "bdi",
    "bdo",
    "big",
    "blockquote",
    "body",
    "br",
    "button",
    "canvas",
    "caption",
    "center",
    "cite",
    "code",
    "col",
    "colgroup",
    "command",
    "datalist",
    "dd",
    "del",
    "details",
    "dfn",
    "dir",
    "div",
    "dl",
    "dt",
    "em",
    "embed",
    "fieldset",
    "figcaption",
    "figure",
    "font",
    "footer",
    "form",
    "frame",
    "frameset",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hgroup",
    "hr",
    "html",
    "i",
    "iframe",
    "img",
    "input",
    "ins",
    "isindex",
    "keygen",
    "kbd",
    "label",
    "legend",
    "li",
    "link",
    "map",
    "mark",
    "menu",
    "meta",
    "meter",
    "nav",
    "noframes",
    "noscript",
    "object",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "param",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "script",
    "section",
    "select",
    "small",
    "source",
    "span",
    "strike",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "tt",
    "u",
    "ul",
    "var",
    "video",
    "wbr",
}


class _TagFactory:
    """
    A factory for L{Tag} objects; the implementation of the L{tags} object.

    This allows for the syntactic convenience of C{from twisted.web.template
    import tags; tags.a(href="linked-page.html")}, where 'a' can be basically
    any HTML tag.

    The class is not exposed publicly because you only ever need one of these,
    and we already made it for you.

    @see: L{tags}
    """

    def __getattr__(self, tagName: str) -> Tag:
        if tagName == "transparent":
            return Tag("")
        # allow for E.del as E.del_
        tagName = tagName.rstrip("_")
        if tagName not in VALID_HTML_TAG_NAMES:
            raise AttributeError(f"unknown tag {tagName!r}")
        return Tag(tagName)


tags = _TagFactory()


def renderElement(
    request: IRequest,
    element: IRenderable,
    doctype: Optional[bytes] = b"<!DOCTYPE html>",
    _failElement: Optional[Callable[[Failure], "Element"]] = None,
) -> object:
    """
    Render an element or other L{IRenderable}.

    @param request: The L{IRequest} being rendered to.
    @param element: An L{IRenderable} which will be rendered.
    @param doctype: A L{bytes} which will be written as the first line of
        the request, or L{None} to disable writing of a doctype.  The argument
        should not include a trailing newline and will default to the HTML5
        doctype C{'<!DOCTYPE html>'}.

    @returns: NOT_DONE_YET

    @since: 12.1
    """
    if doctype is not None:
        request.write(doctype)
        request.write(b"\n")

    if _failElement is None:
        _failElement = FailureElement

    d = flatten(request, element, request.write)

    def eb(failure: Failure) -> Optional[Deferred[None]]:
        _moduleLog.failure(
            "An error occurred while rendering the response.", failure=failure
        )
        site = getattr(request, "site", None)
        if site is not None and site.displayTracebacks:
            assert _failElement is not None
            return flatten(request, _failElement(failure), request.write)
        else:
            request.write(
                b'<div style="font-size:800%;'
                b"background-color:#FFF;"
                b"color:#F00"
                b'">An error occurred while rendering the response.</div>'
            )
            return None

    def finish(result: object, *, request: IRequest = request) -> object:
        request.finish()
        return result

    d.addErrback(eb)
    d.addBoth(finish)
    return NOT_DONE_YET
