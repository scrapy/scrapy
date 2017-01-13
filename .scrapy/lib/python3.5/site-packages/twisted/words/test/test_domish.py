# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.words.xish.domish}, a DOM-like library for XMPP.
"""

from __future__ import absolute_import, division

from zope.interface.verify import verifyObject

from twisted.python.compat import _PY3, unicode
from twisted.python.reflect import requireModule
from twisted.trial import unittest
from twisted.words.xish import domish


class ElementTests(unittest.TestCase):
    """
    Tests for L{domish.Element}.
    """

    def test_interface(self):
        """
        L{domish.Element} implements L{domish.IElement}.
        """
        verifyObject(domish.IElement, domish.Element((None, u"foo")))


    def test_escaping(self):
        """
        The built-in entity references are properly encoded.
        """
        s = "&<>'\""
        self.assertEqual(domish.escapeToXml(s), "&amp;&lt;&gt;'\"")
        self.assertEqual(domish.escapeToXml(s, 1), "&amp;&lt;&gt;&apos;&quot;")


    def test_namespace(self):
        """
        An attribute on L{domish.Namespace} yields a qualified name.
        """
        ns = domish.Namespace("testns")
        self.assertEqual(ns.foo, ("testns", "foo"))


    def test_elementInit(self):
        """
        Basic L{domish.Element} initialization tests.
        """
        e = domish.Element((None, "foo"))
        self.assertEqual(e.name, "foo")
        self.assertEqual(e.uri, None)
        self.assertEqual(e.defaultUri, None)
        self.assertEqual(e.parent, None)

        e = domish.Element(("", "foo"))
        self.assertEqual(e.name, "foo")
        self.assertEqual(e.uri, "")
        self.assertEqual(e.defaultUri, "")
        self.assertEqual(e.parent, None)

        e = domish.Element(("testns", "foo"))
        self.assertEqual(e.name, "foo")
        self.assertEqual(e.uri, "testns")
        self.assertEqual(e.defaultUri, "testns")
        self.assertEqual(e.parent, None)

        e = domish.Element(("testns", "foo"), "test2ns")
        self.assertEqual(e.name, "foo")
        self.assertEqual(e.uri, "testns")
        self.assertEqual(e.defaultUri, "test2ns")


    def test_childOps(self):
        """
        Basic L{domish.Element} child tests.
        """
        e = domish.Element(("testns", "foo"))
        e.addContent(u"somecontent")
        b2 = e.addElement(("testns2", "bar2"))
        e["attrib1"] = "value1"
        e[("testns2", "attrib2")] = "value2"
        e.addElement("bar")
        e.addElement("bar")
        e.addContent(u"abc")
        e.addContent(u"123")

        # Check content merging
        self.assertEqual(e.children[-1], "abc123")

        # Check direct child accessor
        self.assertEqual(e.bar2, b2)
        e.bar2.addContent(u"subcontent")
        e.bar2["bar2value"] = "somevalue"

        # Check child ops
        self.assertEqual(e.children[1], e.bar2)
        self.assertEqual(e.children[2], e.bar)

        # Check attribute ops
        self.assertEqual(e["attrib1"], "value1")
        del e["attrib1"]
        self.assertEqual(e.hasAttribute("attrib1"), 0)
        self.assertEqual(e.hasAttribute("attrib2"), 0)
        self.assertEqual(e[("testns2", "attrib2")], "value2")


    def test_characterData(self):
        """
        Extract character data using L{unicode}.
        """
        element = domish.Element((u"testns", u"foo"))
        element.addContent(u"somecontent")

        text = unicode(element)
        self.assertEqual(u"somecontent", text)
        self.assertIsInstance(text, unicode)


    def test_characterDataNativeString(self):
        """
        Extract ascii character data using L{str}.
        """
        element = domish.Element((u"testns", u"foo"))
        element.addContent(u"somecontent")

        text = str(element)
        self.assertEqual("somecontent", text)
        self.assertIsInstance(text, str)


    def test_characterDataUnicode(self):
        """
        Extract character data using L{unicode}.
        """
        element = domish.Element((u"testns", u"foo"))
        element.addContent(u"\N{SNOWMAN}")

        text = unicode(element)
        self.assertEqual(u"\N{SNOWMAN}", text)
        self.assertIsInstance(text, unicode)


    def test_characterDataBytes(self):
        """
        Extract character data as UTF-8 using L{bytes}.
        """
        element = domish.Element((u"testns", u"foo"))
        element.addContent(u"\N{SNOWMAN}")

        text = bytes(element)
        self.assertEqual(u"\N{SNOWMAN}".encode('utf-8'), text)
        self.assertIsInstance(text, bytes)


    def test_characterDataMixed(self):
        """
        Mixing addChild with cdata and element, the first cdata is returned.
        """
        element = domish.Element((u"testns", u"foo"))
        element.addChild(u"abc")
        element.addElement("bar")
        element.addChild(u"def")
        self.assertEqual(u"abc", unicode(element))


    def test_addContent(self):
        """
        Unicode strings passed to C{addContent} become the character data.
        """
        element = domish.Element((u"testns", u"foo"))
        element.addContent(u'unicode')
        self.assertEqual(u"unicode", unicode(element))


    def test_addContentNativeStringASCII(self):
        """
        ASCII native strings passed to C{addContent} become the character data.
        """
        element = domish.Element((u"testns", u"foo"))
        element.addContent('native')
        self.assertEqual(u"native", unicode(element))


    def test_addContentBytes(self):
        """
        Byte strings passed to C{addContent} are not acceptable on Python 3.
        """
        element = domish.Element((u"testns", u"foo"))
        self.assertRaises(TypeError, element.addContent, b'bytes')
    if not _PY3:
        test_addContentBytes.skip = (
            "Bytes behavior of addContent only provided on Python 2.")


    def test_addContentBytesNonASCII(self):
        """
        Non-ASCII byte strings passed to C{addContent} yield L{UnicodeError}.
        """
        element = domish.Element((u"testns", u"foo"))
        self.assertRaises(UnicodeError, element.addContent, b'\xe2\x98\x83')
    if _PY3:
        test_addContentBytesNonASCII.skip = (
            "Bytes behavior of addContent only provided on Python 2.")


    def test_addElementContent(self):
        """
        Content passed to addElement becomes character data on the new child.
        """
        element = domish.Element((u"testns", u"foo"))
        child = element.addElement("bar", content=u"abc")
        self.assertEqual(u"abc", unicode(child))


    def test_elements(self):
        """
        Calling C{elements} without arguments on a L{domish.Element} returns
        all child elements, whatever the qualified name.
        """
        e = domish.Element((u"testns", u"foo"))
        c1 = e.addElement(u"name")
        c2 = e.addElement((u"testns2", u"baz"))
        c3 = e.addElement(u"quux")
        c4 = e.addElement((u"testns", u"name"))

        elts = list(e.elements())

        self.assertIn(c1, elts)
        self.assertIn(c2, elts)
        self.assertIn(c3, elts)
        self.assertIn(c4, elts)


    def test_elementsWithQN(self):
        """
        Calling C{elements} with a namespace and local name on a
        L{domish.Element} returns all child elements with that qualified name.
        """
        e = domish.Element((u"testns", u"foo"))
        c1 = e.addElement(u"name")
        c2 = e.addElement((u"testns2", u"baz"))
        c3 = e.addElement(u"quux")
        c4 = e.addElement((u"testns", u"name"))

        elts = list(e.elements(u"testns", u"name"))

        self.assertIn(c1, elts)
        self.assertNotIn(c2, elts)
        self.assertNotIn(c3, elts)
        self.assertIn(c4, elts)



class DomishStreamTestsMixin:
    """
    Mixin defining tests for different stream implementations.

    @ivar streamClass: A no-argument callable which will be used to create an
        XML parser which can produce a stream of elements from incremental
        input.
    """
    def setUp(self):
        self.doc_started = False
        self.doc_ended = False
        self.root = None
        self.elements = []
        self.stream = self.streamClass()
        self.stream.DocumentStartEvent = self._docStarted
        self.stream.ElementEvent = self.elements.append
        self.stream.DocumentEndEvent = self._docEnded

    def _docStarted(self, root):
        self.root = root
        self.doc_started = True

    def _docEnded(self):
        self.doc_ended = True

    def doTest(self, xml):
        self.stream.parse(xml)

    def testHarness(self):
        xml = b"<root><child/><child2/></root>"
        self.stream.parse(xml)
        self.assertEqual(self.doc_started, True)
        self.assertEqual(self.root.name, 'root')
        self.assertEqual(self.elements[0].name, 'child')
        self.assertEqual(self.elements[1].name, 'child2')
        self.assertEqual(self.doc_ended, True)

    def testBasic(self):
        xml = b"<stream:stream xmlns:stream='etherx' xmlns='jabber'>\n" + \
              b"  <message to='bar'>" + \
              b"    <x xmlns='xdelay'>some&amp;data&gt;</x>" + \
              b"  </message>" + \
              b"</stream:stream>"

        self.stream.parse(xml)
        self.assertEqual(self.root.name, 'stream')
        self.assertEqual(self.root.uri, 'etherx')
        self.assertEqual(self.elements[0].name, 'message')
        self.assertEqual(self.elements[0].uri, 'jabber')
        self.assertEqual(self.elements[0]['to'], 'bar')
        self.assertEqual(self.elements[0].x.uri, 'xdelay')
        self.assertEqual(unicode(self.elements[0].x), 'some&data>')

    def testNoRootNS(self):
        xml = b"<stream><error xmlns='etherx'/></stream>"

        self.stream.parse(xml)
        self.assertEqual(self.root.uri, '')
        self.assertEqual(self.elements[0].uri, 'etherx')

    def testNoDefaultNS(self):
        xml = b"<stream:stream xmlns:stream='etherx'><error/></stream:stream>"

        self.stream.parse(xml)
        self.assertEqual(self.root.uri, 'etherx')
        self.assertEqual(self.root.defaultUri, '')
        self.assertEqual(self.elements[0].uri, '')
        self.assertEqual(self.elements[0].defaultUri, '')

    def testChildDefaultNS(self):
        xml = b"<root xmlns='testns'><child/></root>"

        self.stream.parse(xml)
        self.assertEqual(self.root.uri, 'testns')
        self.assertEqual(self.elements[0].uri, 'testns')

    def testEmptyChildNS(self):
        xml = b"""<root xmlns='testns'>
                    <child1><child2 xmlns=''/></child1>
                  </root>"""

        self.stream.parse(xml)
        self.assertEqual(self.elements[0].child2.uri, '')


    def test_namespaceWithWhitespace(self):
        """
        Whitespace in an xmlns value is preserved in the resulting node's C{uri}
        attribute.
        """
        xml = b"<root xmlns:foo=' bar baz '><foo:bar foo:baz='quux'/></root>"
        self.stream.parse(xml)
        self.assertEqual(self.elements[0].uri, " bar baz ")
        self.assertEqual(
            self.elements[0].attributes, {(" bar baz ", "baz"): "quux"})


    def testChildPrefix(self):
        xml = b"<root xmlns='testns' xmlns:foo='testns2'><foo:child/></root>"

        self.stream.parse(xml)
        self.assertEqual(self.root.localPrefixes['foo'], 'testns2')
        self.assertEqual(self.elements[0].uri, 'testns2')

    def testUnclosedElement(self):
        self.assertRaises(domish.ParserError, self.stream.parse,
                                              b"<root><error></root>")

    def test_namespaceReuse(self):
        """
        Test that reuse of namespaces does affect an element's serialization.

        When one element uses a prefix for a certain namespace, this is
        stored in the C{localPrefixes} attribute of the element. We want
        to make sure that elements created after such use, won't have this
        prefix end up in their C{localPrefixes} attribute, too.
        """

        xml = b"""<root>
                    <foo:child1 xmlns:foo='testns'/>
                    <child2 xmlns='testns'/>
                  </root>"""

        self.stream.parse(xml)
        self.assertEqual('child1', self.elements[0].name)
        self.assertEqual('testns', self.elements[0].uri)
        self.assertEqual('', self.elements[0].defaultUri)
        self.assertEqual({'foo': 'testns'}, self.elements[0].localPrefixes)
        self.assertEqual('child2', self.elements[1].name)
        self.assertEqual('testns', self.elements[1].uri)
        self.assertEqual('testns', self.elements[1].defaultUri)
        self.assertEqual({}, self.elements[1].localPrefixes)



class DomishExpatStreamTests(DomishStreamTestsMixin, unittest.TestCase):
    """
    Tests for L{domish.ExpatElementStream}, the expat-based element stream
    implementation.
    """
    streamClass = domish.ExpatElementStream

    if requireModule('pyexpat', default=None) is None:
        skip = "pyexpat is required for ExpatElementStream tests."
    else:
        skip = None



class DomishSuxStreamTests(DomishStreamTestsMixin, unittest.TestCase):
    """
    Tests for L{domish.SuxElementStream}, the L{twisted.web.sux}-based element
    stream implementation.
    """
    streamClass = domish.SuxElementStream

    if _PY3:
        skip = "twisted.web.sux has not been ported to Python 3, yet."
    elif domish.SuxElementStream is None:
        skip = "twisted.web is required for SuxElementStream tests."



class SerializerTests(unittest.TestCase):
    def testNoNamespace(self):
        e = domish.Element((None, "foo"))
        self.assertEqual(e.toXml(), "<foo/>")
        self.assertEqual(e.toXml(closeElement = 0), "<foo>")

    def testDefaultNamespace(self):
        e = domish.Element(("testns", "foo"))
        self.assertEqual(e.toXml(), "<foo xmlns='testns'/>")

    def testOtherNamespace(self):
        e = domish.Element(("testns", "foo"), "testns2")
        self.assertEqual(e.toXml({'testns': 'bar'}),
                          "<bar:foo xmlns:bar='testns' xmlns='testns2'/>")

    def testChildDefaultNamespace(self):
        e = domish.Element(("testns", "foo"))
        e.addElement("bar")
        self.assertEqual(e.toXml(), "<foo xmlns='testns'><bar/></foo>")

    def testChildSameNamespace(self):
        e = domish.Element(("testns", "foo"))
        e.addElement(("testns", "bar"))
        self.assertEqual(e.toXml(), "<foo xmlns='testns'><bar/></foo>")

    def testChildSameDefaultNamespace(self):
        e = domish.Element(("testns", "foo"))
        e.addElement("bar", "testns")
        self.assertEqual(e.toXml(), "<foo xmlns='testns'><bar/></foo>")

    def testChildOtherDefaultNamespace(self):
        e = domish.Element(("testns", "foo"))
        e.addElement(("testns2", "bar"), 'testns2')
        self.assertEqual(e.toXml(), "<foo xmlns='testns'><bar xmlns='testns2'/></foo>")

    def testOnlyChildDefaultNamespace(self):
        e = domish.Element((None, "foo"))
        e.addElement(("ns2", "bar"), 'ns2')
        self.assertEqual(e.toXml(), "<foo><bar xmlns='ns2'/></foo>")

    def testOnlyChildDefaultNamespace2(self):
        e = domish.Element((None, "foo"))
        e.addElement("bar")
        self.assertEqual(e.toXml(), "<foo><bar/></foo>")

    def testChildInDefaultNamespace(self):
        e = domish.Element(("testns", "foo"), "testns2")
        e.addElement(("testns2", "bar"))
        self.assertEqual(e.toXml(), "<xn0:foo xmlns:xn0='testns' xmlns='testns2'><bar/></xn0:foo>")

    def testQualifiedAttribute(self):
        e = domish.Element((None, "foo"),
                           attribs = {("testns2", "bar"): "baz"})
        self.assertEqual(e.toXml(), "<foo xmlns:xn0='testns2' xn0:bar='baz'/>")

    def testQualifiedAttributeDefaultNS(self):
        e = domish.Element(("testns", "foo"),
                           attribs = {("testns", "bar"): "baz"})
        self.assertEqual(e.toXml(), "<foo xmlns='testns' xmlns:xn0='testns' xn0:bar='baz'/>")

    def testTwoChilds(self):
        e = domish.Element(('', "foo"))
        child1 = e.addElement(("testns", "bar"), "testns2")
        child1.addElement(('testns2', 'quux'))
        child2 = e.addElement(("testns3", "baz"), "testns4")
        child2.addElement(('testns', 'quux'))
        self.assertEqual(e.toXml(), "<foo><xn0:bar xmlns:xn0='testns' xmlns='testns2'><quux/></xn0:bar><xn1:baz xmlns:xn1='testns3' xmlns='testns4'><xn0:quux xmlns:xn0='testns'/></xn1:baz></foo>")

    def testXMLNamespace(self):
        e = domish.Element((None, "foo"),
                           attribs = {("http://www.w3.org/XML/1998/namespace",
                                       "lang"): "en_US"})
        self.assertEqual(e.toXml(), "<foo xml:lang='en_US'/>")

    def testQualifiedAttributeGivenListOfPrefixes(self):
        e = domish.Element((None, "foo"),
                           attribs = {("testns2", "bar"): "baz"})
        self.assertEqual(e.toXml({"testns2": "qux"}),
                          "<foo xmlns:qux='testns2' qux:bar='baz'/>")

    def testNSPrefix(self):
        e = domish.Element((None, "foo"),
                           attribs = {("testns2", "bar"): "baz"})
        c = e.addElement(("testns2", "qux"))
        c[("testns2", "bar")] = "quux"

        self.assertEqual(e.toXml(), "<foo xmlns:xn0='testns2' xn0:bar='baz'><xn0:qux xn0:bar='quux'/></foo>")

    def testDefaultNSPrefix(self):
        e = domish.Element((None, "foo"),
                           attribs = {("testns2", "bar"): "baz"})
        c = e.addElement(("testns2", "qux"))
        c[("testns2", "bar")] = "quux"
        c.addElement('foo')

        self.assertEqual(e.toXml(), "<foo xmlns:xn0='testns2' xn0:bar='baz'><xn0:qux xn0:bar='quux'><xn0:foo/></xn0:qux></foo>")

    def testPrefixScope(self):
        e = domish.Element(('testns', 'foo'))

        self.assertEqual(e.toXml(prefixes={'testns': 'bar'},
                                  prefixesInScope=['bar']),
                          "<bar:foo/>")

    def testLocalPrefixes(self):
        e = domish.Element(('testns', 'foo'), localPrefixes={'bar': 'testns'})
        self.assertEqual(e.toXml(), "<bar:foo xmlns:bar='testns'/>")

    def testLocalPrefixesWithChild(self):
        e = domish.Element(('testns', 'foo'), localPrefixes={'bar': 'testns'})
        e.addElement('baz')
        self.assertIdentical(e.baz.defaultUri, None)
        self.assertEqual(e.toXml(), "<bar:foo xmlns:bar='testns'><baz/></bar:foo>")

    def test_prefixesReuse(self):
        """
        Test that prefixes passed to serialization are not modified.

        This test makes sure that passing a dictionary of prefixes repeatedly
        to C{toXml} of elements does not cause serialization errors. A
        previous implementation changed the passed in dictionary internally,
        causing havoc later on.
        """
        prefixes = {'testns': 'foo'}

        # test passing of dictionary
        s = domish.SerializerClass(prefixes=prefixes)
        self.assertNotIdentical(prefixes, s.prefixes)

        # test proper serialization on prefixes reuse
        e = domish.Element(('testns2', 'foo'),
                           localPrefixes={'quux': 'testns2'})
        self.assertEqual("<quux:foo xmlns:quux='testns2'/>",
                          e.toXml(prefixes=prefixes))
        e = domish.Element(('testns2', 'foo'))
        self.assertEqual("<foo xmlns='testns2'/>",
                          e.toXml(prefixes=prefixes))

    def testRawXMLSerialization(self):
        e = domish.Element((None, "foo"))
        e.addRawXml("<abc123>")
        # The testcase below should NOT generate valid XML -- that's
        # the whole point of using the raw XML call -- it's the callers
        # responsibility to ensure that the data inserted is valid
        self.assertEqual(e.toXml(), "<foo><abc123></foo>")

    def testRawXMLWithUnicodeSerialization(self):
        e = domish.Element((None, "foo"))
        e.addRawXml(u"<degree>\u00B0</degree>")
        self.assertEqual(e.toXml(), u"<foo><degree>\u00B0</degree></foo>")

    def testUnicodeSerialization(self):
        e = domish.Element((None, "foo"))
        e["test"] = u"my value\u0221e"
        e.addContent(u"A degree symbol...\u00B0")
        self.assertEqual(e.toXml(),
                          u"<foo test='my value\u0221e'>A degree symbol...\u00B0</foo>")
