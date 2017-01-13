# -*- test-case-name: twisted.web.test.test_template -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTML rendering for twisted.web.

@var VALID_HTML_TAG_NAMES: A list of recognized HTML tag names, used by the
    L{tag} object.

@var TEMPLATE_NAMESPACE: The XML namespace used to identify attributes and
    elements used by the templating system, which should be removed from the
    final output document.

@var tags: A convenience object which can produce L{Tag} objects on demand via
    attribute access.  For example: C{tags.div} is equivalent to C{Tag("div")}.
    Tags not specified in L{VALID_HTML_TAG_NAMES} will result in an
    L{AttributeError}.
"""

from __future__ import division, absolute_import

__all__ = [
    'TEMPLATE_NAMESPACE', 'VALID_HTML_TAG_NAMES', 'Element', 'TagLoader',
    'XMLString', 'XMLFile', 'renderer', 'flatten', 'flattenString', 'tags',
    'Comment', 'CDATA', 'Tag', 'slot', 'CharRef', 'renderElement'
    ]

import warnings

from collections import OrderedDict

from zope.interface import implementer

from xml.sax import make_parser, handler

from twisted.python import log
from twisted.python.compat import NativeStringIO, items
from twisted.python.filepath import FilePath
from twisted.web._stan import Tag, slot, Comment, CDATA, CharRef
from twisted.web.iweb import ITemplateLoader

TEMPLATE_NAMESPACE = 'http://twistedmatrix.com/ns/twisted.web.template/0.1'

# Go read the definition of NOT_DONE_YET. For lulz. This is totally
# equivalent. And this turns out to be necessary, because trying to import
# NOT_DONE_YET in this module causes a circular import which we cannot escape
# from. From which we cannot escape. Etc. glyph is okay with this solution for
# now, and so am I, as long as this comment stays to explain to future
# maintainers what it means. ~ C.
#
# See http://twistedmatrix.com/trac/ticket/5557 for progress on fixing this.
NOT_DONE_YET = 1


class _NSContext(object):
    """
    A mapping from XML namespaces onto their prefixes in the document.
    """

    def __init__(self, parent=None):
        """
        Pull out the parent's namespaces, if there's no parent then default to
        XML.
        """
        self.parent = parent
        if parent is not None:
            self.nss = OrderedDict(parent.nss)
        else:
            self.nss = {'http://www.w3.org/XML/1998/namespace':'xml'}


    def get(self, k, d=None):
        """
        Get a prefix for a namespace.

        @param d: The default prefix value.
        """
        return self.nss.get(k, d)


    def __setitem__(self, k, v):
        """
        Proxy through to setting the prefix for the namespace.
        """
        self.nss.__setitem__(k, v)


    def __getitem__(self, k):
        """
        Proxy through to getting the prefix for the namespace.
        """
        return self.nss.__getitem__(k)



class _ToStan(handler.ContentHandler, handler.EntityResolver):
    """
    A SAX parser which converts an XML document to the Twisted STAN
    Document Object Model.
    """

    def __init__(self, sourceFilename):
        """
        @param sourceFilename: the filename to load the XML out of.
        """
        self.sourceFilename = sourceFilename
        self.prefixMap = _NSContext()
        self.inCDATA = False


    def setDocumentLocator(self, locator):
        """
        Set the document locator, which knows about line and character numbers.
        """
        self.locator = locator


    def startDocument(self):
        """
        Initialise the document.
        """
        self.document = []
        self.current = self.document
        self.stack = []
        self.xmlnsAttrs = []


    def endDocument(self):
        """
        Document ended.
        """


    def processingInstruction(self, target, data):
        """
        Processing instructions are ignored.
        """


    def startPrefixMapping(self, prefix, uri):
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
            self.xmlnsAttrs.append(('xmlns',uri))
        else:
            self.xmlnsAttrs.append(('xmlns:%s'%prefix,uri))


    def endPrefixMapping(self, prefix):
        """
        "Pops the stack" on the prefix mapping.

        Gets called after endElementNS.
        """
        self.prefixMap = self.prefixMap.parent


    def startElementNS(self, namespaceAndName, qname, attrs):
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
            if name == 'transparent':
                name = ''
            elif name == 'slot':
                try:
                    # Try to get the default value for the slot
                    default = attrs[(None, 'default')]
                except KeyError:
                    # If there wasn't one, then use None to indicate no
                    # default.
                    default = None
                el = slot(
                    attrs[(None, 'name')], default=default,
                    filename=filename, lineNumber=lineNumber,
                    columnNumber=columnNumber)
                self.stack.append(el)
                self.current.append(el)
                self.current = el.children
                return

        render = None

        attrs = OrderedDict(attrs)
        for k, v in items(attrs):
            attrNS, justTheName = k
            if attrNS != TEMPLATE_NAMESPACE:
                continue
            if justTheName == 'render':
                render = v
                del attrs[k]

        # nonTemplateAttrs is a dictionary mapping attributes that are *not* in
        # TEMPLATE_NAMESPACE to their values.  Those in TEMPLATE_NAMESPACE were
        # just removed from 'attrs' in the loop immediately above.  The key in
        # nonTemplateAttrs is either simply the attribute name (if it was not
        # specified as having a namespace in the template) or prefix:name,
        # preserving the xml namespace prefix given in the document.

        nonTemplateAttrs = OrderedDict()
        for (attrNs, attrName), v in items(attrs):
            nsPrefix = self.prefixMap.get(attrNs)
            if nsPrefix is None:
                attrKey = attrName
            else:
                attrKey = '%s:%s' % (nsPrefix, attrName)
            nonTemplateAttrs[attrKey] = v

        if ns == TEMPLATE_NAMESPACE and name == 'attr':
            if not self.stack:
                # TODO: define a better exception for this?
                raise AssertionError(
                    '<{%s}attr> as top-level element' % (TEMPLATE_NAMESPACE,))
            if 'name' not in nonTemplateAttrs:
                # TODO: same here
                raise AssertionError(
                    '<{%s}attr> requires a name attribute' % (TEMPLATE_NAMESPACE,))
            el = Tag('', render=render, filename=filename,
                     lineNumber=lineNumber, columnNumber=columnNumber)
            self.stack[-1].attributes[nonTemplateAttrs['name']] = el
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
                name = '%s:%s' % (self.prefixMap[ns],name)
        el = Tag(
            name, attributes=OrderedDict(nonTemplateAttrs), render=render,
            filename=filename, lineNumber=lineNumber,
            columnNumber=columnNumber)
        self.stack.append(el)
        self.current.append(el)
        self.current = el.children


    def characters(self, ch):
        """
        Called when we receive some characters.  CDATA characters get passed
        through as is.

        @type ch: C{string}
        """
        if self.inCDATA:
            self.stack[-1].append(ch)
            return
        self.current.append(ch)


    def endElementNS(self, name, qname):
        """
        A namespace tag is closed.  Pop the stack, if there's anything left in
        it, otherwise return to the document's namespace.
        """
        self.stack.pop()
        if self.stack:
            self.current = self.stack[-1].children
        else:
            self.current = self.document


    def startDTD(self, name, publicId, systemId):
        """
        DTDs are ignored.
        """


    def endDTD(self, *args):
        """
        DTDs are ignored.
        """


    def startCDATA(self):
        """
        We're starting to be in a CDATA element, make a note of this.
        """
        self.inCDATA = True
        self.stack.append([])


    def endCDATA(self):
        """
        We're no longer in a CDATA element.  Collect up the characters we've
        parsed and put them in a new CDATA object.
        """
        self.inCDATA = False
        comment = ''.join(self.stack.pop())
        self.current.append(CDATA(comment))


    def comment(self, content):
        """
        Add an XML comment which we've encountered.
        """
        self.current.append(Comment(content))



def _flatsaxParse(fl):
    """
    Perform a SAX parse of an XML document with the _ToStan class.

    @param fl: The XML document to be parsed.
    @type fl: A file object or filename.

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
class TagLoader(object):
    """
    An L{ITemplateLoader} that loads existing L{IRenderable} providers.

    @ivar tag: The object which will be loaded.
    @type tag: An L{IRenderable} provider.
    """

    def __init__(self, tag):
        """
        @param tag: The object which will be loaded.
        @type tag: An L{IRenderable} provider.
        """
        self.tag = tag


    def load(self):
        return [self.tag]



@implementer(ITemplateLoader)
class XMLString(object):
    """
    An L{ITemplateLoader} that loads and parses XML from a string.

    @ivar _loadedTemplate: The loaded document.
    @type _loadedTemplate: a C{list} of Stan objects.
    """

    def __init__(self, s):
        """
        Run the parser on a L{NativeStringIO} copy of the string.

        @param s: The string from which to load the XML.
        @type s: C{str}, or a UTF-8 encoded L{bytes}.
        """
        if not isinstance(s, str):
            s = s.decode('utf8')

        self._loadedTemplate = _flatsaxParse(NativeStringIO(s))


    def load(self):
        """
        Return the document.

        @return: the loaded document.
        @rtype: a C{list} of Stan objects.
        """
        return self._loadedTemplate



@implementer(ITemplateLoader)
class XMLFile(object):
    """
    An L{ITemplateLoader} that loads and parses XML from a file.

    @ivar _loadedTemplate: The loaded document, or L{None}, if not loaded.
    @type _loadedTemplate: a C{list} of Stan objects, or L{None}.

    @ivar _path: The L{FilePath}, file object, or filename that is being
        loaded from.
    """

    def __init__(self, path):
        """
        Run the parser on a file.

        @param path: The file from which to load the XML.
        @type path: L{FilePath}
        """
        if not isinstance(path, FilePath):
            warnings.warn(
                "Passing filenames or file objects to XMLFile is deprecated "
                "since Twisted 12.1.  Pass a FilePath instead.",
                category=DeprecationWarning, stacklevel=2)
        self._loadedTemplate = None
        self._path = path


    def _loadDoc(self):
        """
        Read and parse the XML.

        @return: the loaded document.
        @rtype: a C{list} of Stan objects.
        """
        if not isinstance(self._path, FilePath):
            return _flatsaxParse(self._path)
        else:
            with self._path.open('r') as f:
                return _flatsaxParse(f)


    def __repr__(self):
        return '<XMLFile of %r>' % (self._path,)


    def load(self):
        """
        Return the document, first loading it if necessary.

        @return: the loaded document.
        @rtype: a C{list} of Stan objects.
        """
        if self._loadedTemplate is None:
            self._loadedTemplate = self._loadDoc()
        return self._loadedTemplate



# Last updated October 2011, using W3Schools as a reference. Link:
# http://www.w3schools.com/html5/html5_reference.asp
# Note that <xmp> is explicitly omitted; its semantics do not work with
# t.w.template and it is officially deprecated.
VALID_HTML_TAG_NAMES = set([
    'a', 'abbr', 'acronym', 'address', 'applet', 'area', 'article', 'aside',
    'audio', 'b', 'base', 'basefont', 'bdi', 'bdo', 'big', 'blockquote',
    'body', 'br', 'button', 'canvas', 'caption', 'center', 'cite', 'code',
    'col', 'colgroup', 'command', 'datalist', 'dd', 'del', 'details', 'dfn',
    'dir', 'div', 'dl', 'dt', 'em', 'embed', 'fieldset', 'figcaption',
    'figure', 'font', 'footer', 'form', 'frame', 'frameset', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'head', 'header', 'hgroup', 'hr', 'html', 'i', 'iframe',
    'img', 'input', 'ins', 'isindex', 'keygen', 'kbd', 'label', 'legend',
    'li', 'link', 'map', 'mark', 'menu', 'meta', 'meter', 'nav', 'noframes',
    'noscript', 'object', 'ol', 'optgroup', 'option', 'output', 'p', 'param',
    'pre', 'progress', 'q', 'rp', 'rt', 'ruby', 's', 'samp', 'script',
    'section', 'select', 'small', 'source', 'span', 'strike', 'strong',
    'style', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'textarea',
    'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'tt', 'u', 'ul', 'var',
    'video', 'wbr',
])



class _TagFactory(object):
    """
    A factory for L{Tag} objects; the implementation of the L{tags} object.

    This allows for the syntactic convenience of C{from twisted.web.html import
    tags; tags.a(href="linked-page.html")}, where 'a' can be basically any HTML
    tag.

    The class is not exposed publicly because you only ever need one of these,
    and we already made it for you.

    @see: L{tags}
    """
    def __getattr__(self, tagName):
        if tagName == 'transparent':
            return Tag('')
        # allow for E.del as E.del_
        tagName = tagName.rstrip('_')
        if tagName not in VALID_HTML_TAG_NAMES:
            raise AttributeError('unknown tag %r' % (tagName,))
        return Tag(tagName)



tags = _TagFactory()



def renderElement(request, element,
                  doctype=b'<!DOCTYPE html>', _failElement=None):
    """
    Render an element or other C{IRenderable}.

    @param request: The C{Request} being rendered to.
    @param element: An C{IRenderable} which will be rendered.
    @param doctype: A C{bytes} which will be written as the first line of
        the request, or L{None} to disable writing of a doctype.  The C{string}
        should not include a trailing newline and will default to the HTML5
        doctype C{'<!DOCTYPE html>'}.

    @returns: NOT_DONE_YET

    @since: 12.1
    """
    if doctype is not None:
        request.write(doctype)
        request.write(b'\n')

    if _failElement is None:
        _failElement = twisted.web.util.FailureElement

    d = flatten(request, element, request.write)

    def eb(failure):
        log.err(failure, "An error occurred while rendering the response.")
        if request.site.displayTracebacks:
            return flatten(request, _failElement(failure),
                           request.write).encode('utf8')
        else:
            request.write(
                (b'<div style="font-size:800%;'
                 b'background-color:#FFF;'
                 b'color:#F00'
                 b'">An error occurred while rendering the response.</div>'))

    d.addErrback(eb)
    d.addBoth(lambda _: request.finish())
    return NOT_DONE_YET



from twisted.web._element import Element, renderer
from twisted.web._flatten import flatten, flattenString
import twisted.web.util
