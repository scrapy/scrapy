# -*- test-case-name: twisted.words.test.test_domish -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
DOM-like XML processing support.

This module provides support for parsing XML into DOM-like object structures
and serializing such structures to an XML string representation, optimized
for use in streaming XML applications.
"""

from __future__ import absolute_import, division

from zope.interface import implementer, Interface, Attribute

from twisted.python.compat import (_PY3, StringType, _coercedUnicode,
                                   iteritems, itervalues, unicode)

def _splitPrefix(name):
    """ Internal method for splitting a prefixed Element name into its
        respective parts """
    ntok = name.split(":", 1)
    if len(ntok) == 2:
        return ntok
    else:
        return (None, ntok[0])

# Global map of prefixes that always get injected
# into the serializers prefix map (note, that doesn't
# mean they're always _USED_)
G_PREFIXES = { "http://www.w3.org/XML/1998/namespace":"xml" }

class _ListSerializer:
    """ Internal class which serializes an Element tree into a buffer """
    def __init__(self, prefixes=None, prefixesInScope=None):
        self.writelist = []
        self.prefixes = {}
        if prefixes:
            self.prefixes.update(prefixes)
        self.prefixes.update(G_PREFIXES)
        self.prefixStack = [G_PREFIXES.values()] + (prefixesInScope or [])
        self.prefixCounter = 0

    def getValue(self):
        return u"".join(self.writelist)

    def getPrefix(self, uri):
        if uri not in self.prefixes:
            self.prefixes[uri] = "xn%d" % (self.prefixCounter)
            self.prefixCounter = self.prefixCounter + 1
        return self.prefixes[uri]

    def prefixInScope(self, prefix):
        stack = self.prefixStack
        for i in range(-1, (len(self.prefixStack)+1) * -1, -1):
            if prefix in stack[i]:
                return True
        return False

    def serialize(self, elem, closeElement=1, defaultUri=''):
        # Optimization shortcuts
        write = self.writelist.append

        # Shortcut, check to see if elem is actually a chunk o' serialized XML
        if isinstance(elem, SerializedXML):
            write(elem)
            return

        # Shortcut, check to see if elem is actually a string (aka Cdata)
        if isinstance(elem, StringType):
            write(escapeToXml(elem))
            return

        # Further optimizations
        name = elem.name
        uri = elem.uri
        defaultUri, currentDefaultUri = elem.defaultUri, defaultUri

        for p, u in iteritems(elem.localPrefixes):
            self.prefixes[u] = p
        self.prefixStack.append(list(elem.localPrefixes.keys()))

        # Inherit the default namespace
        if defaultUri is None:
            defaultUri = currentDefaultUri

        if uri is None:
            uri = defaultUri

        prefix = None
        if uri != defaultUri or uri in self.prefixes:
            prefix = self.getPrefix(uri)
            inScope = self.prefixInScope(prefix)

        # Create the starttag

        if not prefix:
            write("<%s" % (name))
        else:
            write("<%s:%s" % (prefix, name))

            if not inScope:
                write(" xmlns:%s='%s'" % (prefix, uri))
                self.prefixStack[-1].append(prefix)
                inScope = True

        if defaultUri != currentDefaultUri and \
           (uri != defaultUri or not prefix or not inScope):
            write(" xmlns='%s'" % (defaultUri))

        for p, u in iteritems(elem.localPrefixes):
            write(" xmlns:%s='%s'" % (p, u))

        # Serialize attributes
        for k,v in elem.attributes.items():
            # If the attribute name is a tuple, it's a qualified attribute
            if isinstance(k, tuple):
                attr_uri, attr_name = k
                attr_prefix = self.getPrefix(attr_uri)

                if not self.prefixInScope(attr_prefix):
                    write(" xmlns:%s='%s'" % (attr_prefix, attr_uri))
                    self.prefixStack[-1].append(attr_prefix)

                write(" %s:%s='%s'" % (attr_prefix, attr_name,
                                       escapeToXml(v, 1)))
            else:
                write((" %s='%s'" % ( k, escapeToXml(v, 1))))

        # Shortcut out if this is only going to return
        # the element (i.e. no children)
        if closeElement == 0:
            write(">")
            return

        # Serialize children
        if len(elem.children) > 0:
            write(">")
            for c in elem.children:
                self.serialize(c, defaultUri=defaultUri)
            # Add closing tag
            if not prefix:
                write("</%s>" % (name))
            else:
                write("</%s:%s>" % (prefix, name))
        else:
            write("/>")

        self.prefixStack.pop()


SerializerClass = _ListSerializer

def escapeToXml(text, isattrib = 0):
    """ Escape text to proper XML form, per section 2.3 in the XML specification.

    @type text: C{str}
    @param text: Text to escape

    @type isattrib: C{bool}
    @param isattrib: Triggers escaping of characters necessary for use as
                     attribute values
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    if isattrib == 1:
        text = text.replace("'", "&apos;")
        text = text.replace("\"", "&quot;")
    return text

def unescapeFromXml(text):
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&apos;", "'")
    text = text.replace("&quot;", "\"")
    text = text.replace("&amp;", "&")
    return text

def generateOnlyInterface(list, int):
    """ Filters items in a list by class
    """
    for n in list:
        if int.providedBy(n):
            yield n

def generateElementsQNamed(list, name, uri):
    """ Filters Element items in a list with matching name and URI. """
    for n in list:
        if IElement.providedBy(n) and n.name == name and n.uri == uri:
            yield n

def generateElementsNamed(list, name):
    """ Filters Element items in a list with matching name, regardless of URI.
    """
    for n in list:
        if IElement.providedBy(n) and n.name == name:
            yield n


class SerializedXML(unicode):
    """ Marker class for pre-serialized XML in the DOM. """
    pass


class Namespace:
    """ Convenience object for tracking namespace declarations. """
    def __init__(self, uri):
        self._uri = uri
    def __getattr__(self, n):
        return (self._uri, n)
    def __getitem__(self, n):
        return (self._uri, n)

class IElement(Interface):
    """
    Interface to XML element nodes.

    See L{Element} for a detailed example of its general use.

    Warning: this Interface is not yet complete!
    """

    uri = Attribute(""" Element's namespace URI """)
    name = Attribute(""" Element's local name """)
    defaultUri = Attribute(""" Default namespace URI of child elements """)
    attributes = Attribute(""" Dictionary of element attributes """)
    children = Attribute(""" List of child nodes """)
    parent = Attribute(""" Reference to element's parent element """)
    localPrefixes = Attribute(""" Dictionary of local prefixes """)

    def toXml(prefixes=None, closeElement=1, defaultUri='',
              prefixesInScope=None):
        """ Serializes object to a (partial) XML document

        @param prefixes: dictionary that maps namespace URIs to suggested
                         prefix names.
        @type prefixes: L{dict}

        @param closeElement: flag that determines whether to include the
            closing tag of the element in the serialized string. A value of
            C{0} only generates the element's start tag. A value of C{1} yields
            a complete serialization.
        @type closeElement: L{int}

        @param defaultUri: Initial default namespace URI. This is most useful
            for partial rendering, where the logical parent element (of which
            the starttag was already serialized) declares a default namespace
            that should be inherited.
        @type defaultUri: L{unicode}

        @param prefixesInScope: list of prefixes that are assumed to be
            declared by ancestors.
        @type prefixesInScope: C{list}

        @return: (partial) serialized XML
        @rtype: C{unicode}
        """

    def addElement(name, defaultUri=None, content=None):
        """
        Create an element and add as child.

        The new element is added to this element as a child, and will have
        this element as its parent.

        @param name: element name. This can be either a L{unicode} object that
            contains the local name, or a tuple of (uri, local_name) for a
            fully qualified name. In the former case, the namespace URI is
            inherited from this element.
        @type name: L{unicode} or L{tuple} of (L{unicode}, L{unicode})

        @param defaultUri: default namespace URI for child elements. If
            L{None}, this is inherited from this element.
        @type defaultUri: L{unicode}

        @param content: text contained by the new element.
        @type content: L{unicode}

        @return: the created element
        @rtype: object providing L{IElement}
        """

    def addChild(node):
        """
        Adds a node as child of this element.

        The C{node} will be added to the list of childs of this element, and
        will have this element set as its parent when C{node} provides
        L{IElement}. If C{node} is a L{unicode} and the current last child is
        character data (L{unicode}), the text from C{node} is appended to the
        existing last child.

        @param node: the child node.
        @type node: L{unicode} or object implementing L{IElement}
        """

    def addContent(text):
        """
        Adds character data to this element.

        If the current last child of this element is a string, the text will
        be appended to that string. Otherwise, the text will be added as a new
        child.

        @param text: The character data to be added to this element.
        @type text: L{unicode}
        """


@implementer(IElement)
class Element(object):
    """ Represents an XML element node.

    An Element contains a series of attributes (name/value pairs), content
    (character data), and other child Element objects. When building a document
    with markup (such as HTML or XML), use this object as the starting point.

    Element objects fully support XML Namespaces. The fully qualified name of
    the XML Element it represents is stored in the C{uri} and C{name}
    attributes, where C{uri} holds the namespace URI. There is also a default
    namespace, for child elements. This is stored in the C{defaultUri}
    attribute. Note that C{''} means the empty namespace.

    Serialization of Elements through C{toXml()} will use these attributes
    for generating proper serialized XML. When both C{uri} and C{defaultUri}
    are not None in the Element and all of its descendents, serialization
    proceeds as expected:

      >>> from twisted.words.xish import domish
      >>> root = domish.Element(('myns', 'root'))
      >>> root.addElement('child', content='test')
      <twisted.words.xish.domish.Element object at 0x83002ac>
      >>> root.toXml()
      u"<root xmlns='myns'><child>test</child></root>"

    For partial serialization, needed for streaming XML, a special value for
    namespace URIs can be used: L{None}.

    Using L{None} as the value for C{uri} means: this element is in whatever
    namespace inherited by the closest logical ancestor when the complete XML
    document has been serialized. The serialized start tag will have a
    non-prefixed name, and no xmlns declaration will be generated.

    Similarly, L{None} for C{defaultUri} means: the default namespace for my
    child elements is inherited from the logical ancestors of this element,
    when the complete XML document has been serialized.

    To illustrate, an example from a Jabber stream. Assume the start tag of the
    root element of the stream has already been serialized, along with several
    complete child elements, and sent off, looking like this::

      <stream:stream xmlns:stream='http://etherx.jabber.org/streams'
                     xmlns='jabber:client' to='example.com'>
        ...

    Now suppose we want to send a complete element represented by an
    object C{message} created like:

      >>> message = domish.Element((None, 'message'))
      >>> message['to'] = 'user@example.com'
      >>> message.addElement('body', content='Hi!')
      <twisted.words.xish.domish.Element object at 0x8276e8c>
      >>> message.toXml()
      u"<message to='user@example.com'><body>Hi!</body></message>"

    As, you can see, this XML snippet has no xmlns declaration. When sent
    off, it inherits the C{jabber:client} namespace from the root element.
    Note that this renders the same as using C{''} instead of L{None}:

      >>> presence = domish.Element(('', 'presence'))
      >>> presence.toXml()
      u"<presence/>"

    However, if this object has a parent defined, the difference becomes
    clear:

      >>> child = message.addElement(('http://example.com/', 'envelope'))
      >>> child.addChild(presence)
      <twisted.words.xish.domish.Element object at 0x8276fac>
      >>> message.toXml()
      u"<message to='user@example.com'><body>Hi!</body><envelope xmlns='http://example.com/'><presence xmlns=''/></envelope></message>"

    As, you can see, the <presence/> element is now in the empty namespace, not
    in the default namespace of the parent or the streams'.

    @type uri: C{unicode} or None
    @ivar uri: URI of this Element's name

    @type name: C{unicode}
    @ivar name: Name of this Element

    @type defaultUri: C{unicode} or None
    @ivar defaultUri: URI this Element exists within

    @type children: C{list}
    @ivar children: List of child Elements and content

    @type parent: L{Element}
    @ivar parent: Reference to the parent Element, if any.

    @type attributes: L{dict}
    @ivar attributes: Dictionary of attributes associated with this Element.

    @type localPrefixes: L{dict}
    @ivar localPrefixes: Dictionary of namespace declarations on this
                         element. The key is the prefix to bind the
                         namespace uri to.
    """

    _idCounter = 0

    def __init__(self, qname, defaultUri=None, attribs=None,
                       localPrefixes=None):
        """
        @param qname: Tuple of (uri, name)
        @param defaultUri: The default URI of the element; defaults to the URI
                           specified in C{qname}
        @param attribs: Dictionary of attributes
        @param localPrefixes: Dictionary of namespace declarations on this
                              element. The key is the prefix to bind the
                              namespace uri to.
        """
        self.localPrefixes = localPrefixes or {}
        self.uri, self.name = qname
        if defaultUri is None and \
           self.uri not in itervalues(self.localPrefixes):
            self.defaultUri = self.uri
        else:
            self.defaultUri = defaultUri
        self.attributes = attribs or {}
        self.children = []
        self.parent = None

    def __getattr__(self, key):
        # Check child list for first Element with a name matching the key
        for n in self.children:
            if IElement.providedBy(n) and n.name == key:
                return n

        # Tweak the behaviour so that it's more friendly about not
        # finding elements -- we need to document this somewhere :)
        if key.startswith('_'):
            raise AttributeError(key)
        else:
            return None

    def __getitem__(self, key):
        return self.attributes[self._dqa(key)]

    def __delitem__(self, key):
        del self.attributes[self._dqa(key)];

    def __setitem__(self, key, value):
        self.attributes[self._dqa(key)] = value

    def __unicode__(self):
        """
        Retrieve the first CData (content) node
        """
        for n in self.children:
            if isinstance(n, StringType):
                return n
        return u""

    def __bytes__(self):
        """
        Retrieve the first character data node as UTF-8 bytes.
        """
        return unicode(self).encode('utf-8')

    if _PY3:
        __str__ = __unicode__
    else:
        __str__ = __bytes__

    def _dqa(self, attr):
        """ Dequalify an attribute key as needed """
        if isinstance(attr, tuple) and not attr[0]:
            return attr[1]
        else:
            return attr

    def getAttribute(self, attribname, default = None):
        """ Retrieve the value of attribname, if it exists """
        return self.attributes.get(attribname, default)

    def hasAttribute(self, attrib):
        """ Determine if the specified attribute exists """
        return self._dqa(attrib) in self.attributes

    def compareAttribute(self, attrib, value):
        """ Safely compare the value of an attribute against a provided value.

        L{None}-safe.
        """
        return self.attributes.get(self._dqa(attrib), None) == value

    def swapAttributeValues(self, left, right):
        """ Swap the values of two attribute. """
        d = self.attributes
        l = d[left]
        d[left] = d[right]
        d[right] = l

    def addChild(self, node):
        """ Add a child to this Element. """
        if IElement.providedBy(node):
            node.parent = self
        self.children.append(node)
        return node

    def addContent(self, text):
        """ Add some text data to this Element. """
        text = _coercedUnicode(text)
        c = self.children
        if len(c) > 0 and isinstance(c[-1], unicode):
            c[-1] = c[-1] + text
        else:
            c.append(text)
        return c[-1]

    def addElement(self, name, defaultUri = None, content = None):
        if isinstance(name, tuple):
            if defaultUri is None:
                defaultUri = name[0]
            child = Element(name, defaultUri)
        else:
            if defaultUri is None:
                defaultUri = self.defaultUri
            child = Element((defaultUri, name), defaultUri)

        self.addChild(child)

        if content:
            child.addContent(content)

        return child

    def addRawXml(self, rawxmlstring):
        """ Add a pre-serialized chunk o' XML as a child of this Element. """
        self.children.append(SerializedXML(rawxmlstring))

    def addUniqueId(self):
        """ Add a unique (across a given Python session) id attribute to this
            Element.
        """
        self.attributes["id"] = "H_%d" % Element._idCounter
        Element._idCounter = Element._idCounter + 1


    def elements(self, uri=None, name=None):
        """
        Iterate across all children of this Element that are Elements.

        Returns a generator over the child elements. If both the C{uri} and
        C{name} parameters are set, the returned generator will only yield
        on elements matching the qualified name.

        @param uri: Optional element URI.
        @type uri: C{unicode}
        @param name: Optional element name.
        @type name: C{unicode}
        @return: Iterator that yields objects implementing L{IElement}.
        """
        if name is None:
            return generateOnlyInterface(self.children, IElement)
        else:
            return generateElementsQNamed(self.children, name, uri)


    def toXml(self, prefixes=None, closeElement=1, defaultUri='',
                    prefixesInScope=None):
        """ Serialize this Element and all children to a string. """
        s = SerializerClass(prefixes=prefixes, prefixesInScope=prefixesInScope)
        s.serialize(self, closeElement=closeElement, defaultUri=defaultUri)
        return s.getValue()

    def firstChildElement(self):
        for c in self.children:
            if IElement.providedBy(c):
                return c
        return None


class ParserError(Exception):
    """ Exception thrown when a parsing error occurs """
    pass

def elementStream():
    """ Preferred method to construct an ElementStream

    Uses Expat-based stream if available, and falls back to Sux if necessary.
    """
    try:
        es = ExpatElementStream()
        return es
    except ImportError:
        if SuxElementStream is None:
            raise Exception("No parsers available :(")
        es = SuxElementStream()
        return es

try:
    from twisted.web import sux
except:
    SuxElementStream = None
else:
    class SuxElementStream(sux.XMLParser):
        def __init__(self):
            self.connectionMade()
            self.DocumentStartEvent = None
            self.ElementEvent = None
            self.DocumentEndEvent = None
            self.currElem = None
            self.rootElem = None
            self.documentStarted = False
            self.defaultNsStack = []
            self.prefixStack = []

        def parse(self, buffer):
            try:
                self.dataReceived(buffer)
            except sux.ParseError as e:
                raise ParserError(str(e))


        def findUri(self, prefix):
            # Walk prefix stack backwards, looking for the uri
            # matching the specified prefix
            stack = self.prefixStack
            for i in range(-1, (len(self.prefixStack)+1) * -1, -1):
                if prefix in stack[i]:
                    return stack[i][prefix]
            return None

        def gotTagStart(self, name, attributes):
            defaultUri = None
            localPrefixes = {}
            attribs = {}
            uri = None

            # Pass 1 - Identify namespace decls
            for k, v in list(attributes.items()):
                if k.startswith("xmlns"):
                    x, p = _splitPrefix(k)
                    if (x is None): # I.e.  default declaration
                        defaultUri = v
                    else:
                        localPrefixes[p] = v
                    del attributes[k]

            # Push namespace decls onto prefix stack
            self.prefixStack.append(localPrefixes)

            # Determine default namespace for this element; if there
            # is one
            if defaultUri is None:
                if len(self.defaultNsStack) > 0:
                    defaultUri = self.defaultNsStack[-1]
                else:
                    defaultUri = ''

            # Fix up name
            prefix, name = _splitPrefix(name)
            if prefix is None: # This element is in the default namespace
                uri = defaultUri
            else:
                # Find the URI for the prefix
                uri = self.findUri(prefix)

            # Pass 2 - Fix up and escape attributes
            for k, v in attributes.items():
                p, n = _splitPrefix(k)
                if p is None:
                    attribs[n] = v
                else:
                    attribs[(self.findUri(p)), n] = unescapeFromXml(v)

            # Construct the actual Element object
            e = Element((uri, name), defaultUri, attribs, localPrefixes)

            # Save current default namespace
            self.defaultNsStack.append(defaultUri)

            # Document already started
            if self.documentStarted:
                # Starting a new packet
                if self.currElem is None:
                    self.currElem = e
                # Adding to existing element
                else:
                    self.currElem = self.currElem.addChild(e)
            # New document
            else:
                self.rootElem = e
                self.documentStarted = True
                self.DocumentStartEvent(e)

        def gotText(self, data):
            if self.currElem != None:
                if isinstance(data, bytes):
                    data = data.decode('ascii')
                self.currElem.addContent(data)

        def gotCData(self, data):
            if self.currElem != None:
                if isinstance(data, bytes):
                    data = data.decode('ascii')
                self.currElem.addContent(data)

        def gotComment(self, data):
            # Ignore comments for the moment
            pass

        entities = { "amp" : "&",
                     "lt"  : "<",
                     "gt"  : ">",
                     "apos": "'",
                     "quot": "\"" }

        def gotEntityReference(self, entityRef):
            # If this is an entity we know about, add it as content
            # to the current element
            if entityRef in SuxElementStream.entities:
                data = SuxElementStream.entities[entityRef]
                if isinstance(data, bytes):
                    data = data.decode('ascii')
                self.currElem.addContent(data)

        def gotTagEnd(self, name):
            # Ensure the document hasn't already ended
            if self.rootElem is None:
                # XXX: Write more legible explanation
                raise ParserError("Element closed after end of document.")

            # Fix up name
            prefix, name = _splitPrefix(name)
            if prefix is None:
                uri = self.defaultNsStack[-1]
            else:
                uri = self.findUri(prefix)

            # End of document
            if self.currElem is None:
                # Ensure element name and uri matches
                if self.rootElem.name != name or self.rootElem.uri != uri:
                    raise ParserError("Mismatched root elements")
                self.DocumentEndEvent()
                self.rootElem = None

            # Other elements
            else:
                # Ensure the tag being closed matches the name of the current
                # element
                if self.currElem.name != name or self.currElem.uri != uri:
                    # XXX: Write more legible explanation
                    raise ParserError("Malformed element close")

                # Pop prefix and default NS stack
                self.prefixStack.pop()
                self.defaultNsStack.pop()

                # Check for parent null parent of current elem;
                # that's the top of the stack
                if self.currElem.parent is None:
                    self.currElem.parent = self.rootElem
                    self.ElementEvent(self.currElem)
                    self.currElem = None

                # Anything else is just some element wrapping up
                else:
                    self.currElem = self.currElem.parent


class ExpatElementStream:
    def __init__(self):
        import pyexpat
        self.DocumentStartEvent = None
        self.ElementEvent = None
        self.DocumentEndEvent = None
        self.error = pyexpat.error
        self.parser = pyexpat.ParserCreate("UTF-8", " ")
        self.parser.StartElementHandler = self._onStartElement
        self.parser.EndElementHandler = self._onEndElement
        self.parser.CharacterDataHandler = self._onCdata
        self.parser.StartNamespaceDeclHandler = self._onStartNamespace
        self.parser.EndNamespaceDeclHandler = self._onEndNamespace
        self.currElem = None
        self.defaultNsStack = ['']
        self.documentStarted = 0
        self.localPrefixes = {}

    def parse(self, buffer):
        try:
            self.parser.Parse(buffer)
        except self.error as e:
            raise ParserError(str(e))

    def _onStartElement(self, name, attrs):
        # Generate a qname tuple from the provided name.  See
        # http://docs.python.org/library/pyexpat.html#xml.parsers.expat.ParserCreate
        # for an explanation of the formatting of name.
        qname = name.rsplit(" ", 1)
        if len(qname) == 1:
            qname = ('', name)

        # Process attributes
        for k, v in attrs.items():
            if " " in k:
                aqname = k.rsplit(" ", 1)
                attrs[(aqname[0], aqname[1])] = v
                del attrs[k]

        # Construct the new element
        e = Element(qname, self.defaultNsStack[-1], attrs, self.localPrefixes)
        self.localPrefixes = {}

        # Document already started
        if self.documentStarted == 1:
            if self.currElem != None:
                self.currElem.children.append(e)
                e.parent = self.currElem
            self.currElem = e

        # New document
        else:
            self.documentStarted = 1
            self.DocumentStartEvent(e)

    def _onEndElement(self, _):
        # Check for null current elem; end of doc
        if self.currElem is None:
            self.DocumentEndEvent()

        # Check for parent that is None; that's
        # the top of the stack
        elif self.currElem.parent is None:
            self.ElementEvent(self.currElem)
            self.currElem = None

        # Anything else is just some element in the current
        # packet wrapping up
        else:
            self.currElem = self.currElem.parent

    def _onCdata(self, data):
        if self.currElem != None:
            self.currElem.addContent(data)

    def _onStartNamespace(self, prefix, uri):
        # If this is the default namespace, put
        # it on the stack
        if prefix is None:
            self.defaultNsStack.append(uri)
        else:
            self.localPrefixes[prefix] = uri

    def _onEndNamespace(self, prefix):
        # Remove last element on the stack
        if prefix is None:
            self.defaultNsStack.pop()

## class FileParser(ElementStream):
##     def __init__(self):
##         ElementStream.__init__(self)
##         self.DocumentStartEvent = self.docStart
##         self.ElementEvent = self.elem
##         self.DocumentEndEvent = self.docEnd
##         self.done = 0

##     def docStart(self, elem):
##         self.document = elem

##     def elem(self, elem):
##         self.document.addChild(elem)

##     def docEnd(self):
##         self.done = 1

##     def parse(self, filename):
##         with open(filename) as f:
##             for l in f.readlines():
##                 self.parser.Parse(l)
##         assert self.done == 1
##         return self.document

## def parseFile(filename):
##     return FileParser().parse(filename)


