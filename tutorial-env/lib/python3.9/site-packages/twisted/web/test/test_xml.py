# -*- test-case-name: twisted.web.test.test_xml -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Some fairly inadequate testcases for Twisted XML support.
"""

from io import BytesIO

from twisted.trial.unittest import TestCase
from twisted.web import domhelpers, microdom, sux


class Sux0r(sux.XMLParser):
    def __init__(self):
        self.tokens = []

    def getTagStarts(self):
        return [token for token in self.tokens if token[0] == "start"]

    def gotTagStart(self, name, attrs):
        self.tokens.append(("start", name, attrs))

    def gotText(self, text):
        self.tokens.append(("text", text))


class SUXTests(TestCase):
    def test_bork(self):
        s = b"<bork><bork><bork>"
        ms = Sux0r()
        ms.connectionMade()
        ms.dataReceived(s)
        self.assertEqual(len(ms.getTagStarts()), 3)


class MicroDOMTests(TestCase):
    def test_leadingTextDropping(self):
        """
        Make sure that if there's no top-level node lenient-mode won't
        drop leading text that's outside of any elements.
        """
        s = "Hi orders! <br>Well. <br>"
        d = microdom.parseString(s, beExtremelyLenient=True)
        self.assertEqual(
            d.firstChild().toxml(), "<html>Hi orders! <br />Well. <br /></html>"
        )
        byteStream = BytesIO()
        d.firstChild().writexml(byteStream, "", "", "", "", {}, "")
        self.assertEqual(
            byteStream.getvalue(), b"<html>Hi orders! <br />Well. <br /></html>"
        )

    def test_trailingTextDropping(self):
        """
        Ensure that no *trailing* text in a mal-formed
        no-top-level-element document(s) will not be dropped.
        """
        s = "<br>Hi orders!"
        d = microdom.parseString(s, beExtremelyLenient=True)
        self.assertEqual(d.firstChild().toxml(), "<html><br />Hi orders!</html>")
        byteStream = BytesIO()
        d.firstChild().writexml(byteStream, "", "", "", "", {}, "")
        self.assertEqual(byteStream.getvalue(), b"<html><br />Hi orders!</html>")

    def test_noTags(self):
        """
        A string with nothing that looks like a tag at all should just
        be parsed as body text.
        """
        s = "Hi orders!"
        d = microdom.parseString(s, beExtremelyLenient=True)
        self.assertEqual(d.firstChild().toxml(), "<html>Hi orders!</html>")

    def test_surroundingCrap(self):
        """
        If a document is surrounded by non-xml text, the text should
        be remain in the XML.
        """
        s = "Hi<br> orders!"
        d = microdom.parseString(s, beExtremelyLenient=True)
        self.assertEqual(d.firstChild().toxml(), "<html>Hi<br /> orders!</html>")

    def test_caseSensitiveSoonCloser(self):
        s = """
              <HTML><BODY>
              <P ALIGN="CENTER">
                <A HREF="http://www.apache.org/"><IMG SRC="/icons/apache_pb.gif"></A>
              </P>

              <P>
                This is an insane set of text nodes that should NOT be gathered under
                the A tag above.
              </P>
              </BODY></HTML>
            """
        d = microdom.parseString(s, beExtremelyLenient=1)
        l = domhelpers.findNodesNamed(d.documentElement, "a")
        n = domhelpers.gatherTextNodes(l[0], 1).replace("&nbsp;", " ")
        self.assertEqual(n.find("insane"), -1)

    def test_lenientParenting(self):
        """
        Test that C{parentNode} attributes are set to meaningful values when
        we are parsing HTML that lacks a root node.
        """
        # Spare the rod, ruin the child.
        s = "<br/><br/>"
        d = microdom.parseString(s, beExtremelyLenient=1)
        self.assertIdentical(
            d.documentElement, d.documentElement.firstChild().parentNode
        )

    def test_lenientParentSingle(self):
        """
        Test that the C{parentNode} attribute is set to a meaningful value
        when we parse an HTML document that has a non-Element root node.
        """
        s = "Hello"
        d = microdom.parseString(s, beExtremelyLenient=1)
        self.assertIdentical(
            d.documentElement, d.documentElement.firstChild().parentNode
        )

    def test_unEntities(self):
        s = """
                <HTML>
                    This HTML goes between Stupid <=CrAzY!=> Dumb.
                </HTML>
            """
        d = microdom.parseString(s, beExtremelyLenient=1)
        n = domhelpers.gatherTextNodes(d)
        self.assertNotEqual(n.find(">"), -1)

    def test_emptyError(self):
        self.assertRaises(sux.ParseError, microdom.parseString, "")

    def test_tameDocument(self):
        s = """
        <test>
         <it>
          <is>
           <a>
            test
           </a>
          </is>
         </it>
        </test>
        """
        d = microdom.parseString(s)
        self.assertEqual(domhelpers.gatherTextNodes(d.documentElement).strip(), "test")

    def test_awfulTagSoup(self):
        s = """
        <html>
        <head><title> I send you this message to have your advice!!!!</titl e
        </headd>

        <body bgcolor alink hlink vlink>

        <h1><BLINK>SALE</blINK> TWENTY MILLION EMAILS & FUR COAT NOW
        FREE WITH `ENLARGER'</h1>

        YES THIS WONDERFUL AWFER IS NOW HERER!!!

        <script LANGUAGE="javascript">
function give_answers() {
if (score < 70) {
alert("I hate you");
}}
        </script><a href=/foo.com/lalal name=foo>lalal</a>
        </body>
        </HTML>
        """
        d = microdom.parseString(s, beExtremelyLenient=1)
        l = domhelpers.findNodesNamed(d.documentElement, "blink")
        self.assertEqual(len(l), 1)

    def test_scriptLeniency(self):
        s = """
        <script>(foo < bar) and (bar > foo)</script>
        <script language="javascript">foo </scrip bar </script>
        <script src="foo">
        <script src="foo">baz</script>
        <script /><script></script>
        """
        d = microdom.parseString(s, beExtremelyLenient=1)
        self.assertEqual(
            d.firstChild().firstChild().firstChild().data, "(foo < bar) and (bar > foo)"
        )
        self.assertEqual(
            d.firstChild().getElementsByTagName("script")[1].firstChild().data,
            "foo </scrip bar ",
        )

    def test_scriptLeniencyIntelligence(self):
        # if there is comment or CDATA in script, the autoquoting in bEL mode
        # should not happen
        s = """<script><!-- lalal --></script>"""
        self.assertEqual(
            microdom.parseString(s, beExtremelyLenient=1).firstChild().toxml(), s
        )
        s = """<script><![CDATA[lalal]]></script>"""
        self.assertEqual(
            microdom.parseString(s, beExtremelyLenient=1).firstChild().toxml(), s
        )
        s = """<script> // <![CDATA[
        lalal
        //]]></script>"""
        self.assertEqual(
            microdom.parseString(s, beExtremelyLenient=1).firstChild().toxml(), s
        )

    def test_preserveCase(self):
        s = "<eNcApSuLaTe><sUxor></sUxor><bOrk><w00T>TeXt</W00t></BoRk></EnCaPsUlAtE>"
        s2 = s.lower().replace("text", "TeXt")
        # these are the only two option permutations that *can* parse the above
        d = microdom.parseString(s, caseInsensitive=1, preserveCase=1)
        d2 = microdom.parseString(s, caseInsensitive=1, preserveCase=0)
        # caseInsensitive=0 preserveCase=0 is not valid, it's converted to
        # caseInsensitive=0 preserveCase=1
        d3 = microdom.parseString(s2, caseInsensitive=0, preserveCase=1)
        d4 = microdom.parseString(s2, caseInsensitive=1, preserveCase=0)
        d5 = microdom.parseString(s2, caseInsensitive=1, preserveCase=1)
        # this is slightly contrived, toxml() doesn't need to be identical
        # for the documents to be equivalent (i.e. <b></b> to <b/>),
        # however this assertion tests preserving case for start and
        # end tags while still matching stuff like <bOrk></BoRk>
        self.assertEqual(d.documentElement.toxml(), s)
        self.assertTrue(d.isEqualToDocument(d2), f"{d.toxml()!r} != {d2.toxml()!r}")
        self.assertTrue(d2.isEqualToDocument(d3), f"{d2.toxml()!r} != {d3.toxml()!r}")
        # caseInsensitive=0 on the left, NOT perserveCase=1 on the right
        ## XXX THIS TEST IS TURNED OFF UNTIL SOMEONE WHO CARES ABOUT FIXING IT DOES
        # self.assertFalse(d3.isEqualToDocument(d2), "%r == %r" % (d3.toxml(), d2.toxml()))
        self.assertTrue(d3.isEqualToDocument(d4), f"{d3.toxml()!r} != {d4.toxml()!r}")
        self.assertTrue(d4.isEqualToDocument(d5), f"{d4.toxml()!r} != {d5.toxml()!r}")

    def test_differentQuotes(self):
        s = "<test a=\"a\" b='b' />"
        d = microdom.parseString(s)
        e = d.documentElement
        self.assertEqual(e.getAttribute("a"), "a")
        self.assertEqual(e.getAttribute("b"), "b")

    def test_Linebreaks(self):
        s = '<test \na="a"\n\tb="#b" />'
        d = microdom.parseString(s)
        e = d.documentElement
        self.assertEqual(e.getAttribute("a"), "a")
        self.assertEqual(e.getAttribute("b"), "#b")

    def test_mismatchedTags(self):
        for s in "<test>", "<test> </tset>", "</test>":
            self.assertRaises(microdom.MismatchedTags, microdom.parseString, s)

    def test_comment(self):
        s = "<bar><!--<foo />--></bar>"
        d = microdom.parseString(s)
        e = d.documentElement
        self.assertEqual(e.nodeName, "bar")
        c = e.childNodes[0]
        self.assertTrue(isinstance(c, microdom.Comment))
        self.assertEqual(c.value, "<foo />")
        c2 = c.cloneNode()
        self.assertTrue(c is not c2)
        self.assertEqual(c2.toxml(), "<!--<foo />-->")

    def test_text(self):
        d = microdom.parseString("<bar>xxxx</bar>").documentElement
        text = d.childNodes[0]
        self.assertTrue(isinstance(text, microdom.Text))
        self.assertEqual(text.value, "xxxx")
        clone = text.cloneNode()
        self.assertTrue(clone is not text)
        self.assertEqual(clone.toxml(), "xxxx")

    def test_entities(self):
        nodes = microdom.parseString("<b>&amp;&#12AB;</b>").documentElement.childNodes
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0].data, "&amp;")
        self.assertEqual(nodes[1].data, "&#12AB;")
        self.assertEqual(nodes[0].cloneNode().toxml(), "&amp;")
        for n in nodes:
            self.assertTrue(isinstance(n, microdom.EntityReference))

    def test_CData(self):
        s = "<x><![CDATA[</x>\r\n & foo]]></x>"
        cdata = microdom.parseString(s).documentElement.childNodes[0]
        self.assertTrue(isinstance(cdata, microdom.CDATASection))
        self.assertEqual(cdata.data, "</x>\r\n & foo")
        self.assertEqual(cdata.cloneNode().toxml(), "<![CDATA[</x>\r\n & foo]]>")

    def test_singletons(self):
        s = "<foo><b/><b /><b\n/></foo>"
        s2 = "<foo><b/><b/><b/></foo>"
        nodes = microdom.parseString(s).documentElement.childNodes
        nodes2 = microdom.parseString(s2).documentElement.childNodes
        self.assertEqual(len(nodes), 3)
        for (n, n2) in zip(nodes, nodes2):
            self.assertTrue(isinstance(n, microdom.Element))
            self.assertEqual(n.nodeName, "b")
            self.assertTrue(n.isEqualToNode(n2))

    def test_attributes(self):
        s = '<foo a="b" />'
        node = microdom.parseString(s).documentElement

        self.assertEqual(node.getAttribute("a"), "b")
        self.assertEqual(node.getAttribute("c"), None)
        self.assertTrue(node.hasAttribute("a"))
        self.assertTrue(not node.hasAttribute("c"))
        a = node.getAttributeNode("a")
        self.assertEqual(a.value, "b")

        node.setAttribute("foo", "bar")
        self.assertEqual(node.getAttribute("foo"), "bar")

    def test_children(self):
        s = "<foo><bar /><baz /><bax>foo</bax></foo>"
        d = microdom.parseString(s).documentElement
        self.assertEqual([n.nodeName for n in d.childNodes], ["bar", "baz", "bax"])
        self.assertEqual(d.lastChild().nodeName, "bax")
        self.assertEqual(d.firstChild().nodeName, "bar")
        self.assertTrue(d.hasChildNodes())
        self.assertTrue(not d.firstChild().hasChildNodes())

    def test_mutate(self):
        s = "<foo />"
        s1 = '<foo a="b"><bar/><foo/></foo>'
        s2 = '<foo a="b">foo</foo>'
        d = microdom.parseString(s).documentElement
        d1 = microdom.parseString(s1).documentElement
        d2 = microdom.parseString(s2).documentElement

        d.appendChild(d.cloneNode())
        d.setAttribute("a", "b")
        child = d.childNodes[0]
        self.assertEqual(child.getAttribute("a"), None)
        self.assertEqual(child.nodeName, "foo")

        d.insertBefore(microdom.Element("bar"), child)
        self.assertEqual(d.childNodes[0].nodeName, "bar")
        self.assertEqual(d.childNodes[1], child)
        for n in d.childNodes:
            self.assertEqual(n.parentNode, d)
        self.assertTrue(d.isEqualToNode(d1))

        d.removeChild(child)
        self.assertEqual(len(d.childNodes), 1)
        self.assertEqual(d.childNodes[0].nodeName, "bar")

        t = microdom.Text("foo")
        d.replaceChild(t, d.firstChild())
        self.assertEqual(d.firstChild(), t)
        self.assertTrue(d.isEqualToNode(d2))

    def test_replaceNonChild(self):
        """
        L{Node.replaceChild} raises L{ValueError} if the node given to be
        replaced is not a child of the node C{replaceChild} is called on.
        """
        parent = microdom.parseString("<foo />")
        orphan = microdom.parseString("<bar />")
        replacement = microdom.parseString("<baz />")

        self.assertRaises(ValueError, parent.replaceChild, replacement, orphan)

    def test_search(self):
        s = "<foo><bar id='me' /><baz><foo /></baz></foo>"
        s2 = "<fOo><bAr id='me' /><bAz><fOO /></bAz></fOo>"
        d = microdom.parseString(s)
        d2 = microdom.parseString(s2, caseInsensitive=0, preserveCase=1)
        d3 = microdom.parseString(s2, caseInsensitive=1, preserveCase=1)

        root = d.documentElement
        self.assertEqual(root.firstChild(), d.getElementById("me"))
        self.assertEqual(
            d.getElementsByTagName("foo"), [root, root.lastChild().firstChild()]
        )

        root = d2.documentElement
        self.assertEqual(root.firstChild(), d2.getElementById("me"))
        self.assertEqual(d2.getElementsByTagName("fOo"), [root])
        self.assertEqual(
            d2.getElementsByTagName("fOO"), [root.lastChild().firstChild()]
        )
        self.assertEqual(d2.getElementsByTagName("foo"), [])

        root = d3.documentElement
        self.assertEqual(root.firstChild(), d3.getElementById("me"))
        self.assertEqual(
            d3.getElementsByTagName("FOO"), [root, root.lastChild().firstChild()]
        )
        self.assertEqual(
            d3.getElementsByTagName("fOo"), [root, root.lastChild().firstChild()]
        )

    def test_doctype(self):
        s = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE foo PUBLIC "baz" "http://www.example.com/example.dtd">'
            "<foo></foo>"
        )
        s2 = "<foo/>"
        d = microdom.parseString(s)
        d2 = microdom.parseString(s2)
        self.assertEqual(
            d.doctype, 'foo PUBLIC "baz" "http://www.example.com/example.dtd"'
        )
        self.assertEqual(d.toxml(), s)
        self.assertFalse(d.isEqualToDocument(d2))
        self.assertTrue(d.documentElement.isEqualToNode(d2.documentElement))

    samples = [
        ("<img/>", "<img />"),
        ("<foo A='b'>x</foo>", '<foo A="b">x</foo>'),
        ("<foo><BAR /></foo>", "<foo><BAR></BAR></foo>"),
        ("<foo>hello there &amp; yoyoy</foo>", "<foo>hello there &amp; yoyoy</foo>"),
    ]

    def test_output(self):
        for s, out in self.samples:
            d = microdom.parseString(s, caseInsensitive=0)
            d2 = microdom.parseString(out, caseInsensitive=0)
            testOut = d.documentElement.toxml()
            self.assertEqual(out, testOut)
            self.assertTrue(d.isEqualToDocument(d2))

    def test_errors(self):
        for s in ["<foo>&am</foo>", "<foo", "<f>&</f>", "<() />"]:
            self.assertRaises(Exception, microdom.parseString, s)

    def test_caseInsensitive(self):
        s = "<foo a='b'><BAx>x</bax></FOO>"
        s2 = '<foo a="b"><bax>x</bax></foo>'
        s3 = "<FOO a='b'><BAx>x</BAx></FOO>"
        s4 = "<foo A='b'>x</foo>"
        d = microdom.parseString(s)
        d2 = microdom.parseString(s2)
        d3 = microdom.parseString(s3, caseInsensitive=1)
        d4 = microdom.parseString(s4, caseInsensitive=1, preserveCase=1)
        d5 = microdom.parseString(s4, caseInsensitive=1, preserveCase=0)
        d6 = microdom.parseString(s4, caseInsensitive=0, preserveCase=0)
        out = microdom.parseString(s).documentElement.toxml()
        self.assertRaises(
            microdom.MismatchedTags, microdom.parseString, s, caseInsensitive=0
        )
        self.assertEqual(out, s2)
        self.assertTrue(d.isEqualToDocument(d2))
        self.assertTrue(d.isEqualToDocument(d3))
        self.assertTrue(d4.documentElement.hasAttribute("a"))
        self.assertFalse(d6.documentElement.hasAttribute("a"))
        self.assertEqual(d4.documentElement.toxml(), '<foo A="b">x</foo>')
        self.assertEqual(d5.documentElement.toxml(), '<foo a="b">x</foo>')

    def test_eatingWhitespace(self):
        s = """<hello>
        </hello>"""
        d = microdom.parseString(s)
        self.assertTrue(
            not d.documentElement.hasChildNodes(), d.documentElement.childNodes
        )
        self.assertTrue(d.isEqualToDocument(microdom.parseString("<hello></hello>")))

    def test_lenientAmpersand(self):
        prefix = "<?xml version='1.0'?>"
        # we use <pre> so space will be preserved
        for i, o in [
            ("&", "&amp;"),
            ("& ", "&amp; "),
            ("&amp;", "&amp;"),
            ("&hello monkey", "&amp;hello monkey"),
        ]:
            d = microdom.parseString(f"{prefix}<pre>{i}</pre>", beExtremelyLenient=1)
            self.assertEqual(d.documentElement.toxml(), "<pre>%s</pre>" % o)
        # non-space preserving
        d = microdom.parseString("<t>hello & there</t>", beExtremelyLenient=1)
        self.assertEqual(d.documentElement.toxml(), "<t>hello &amp; there</t>")

    def test_insensitiveLenient(self):
        # testing issue #537
        d = microdom.parseString(
            "<?xml version='1.0'?><bar><xA><y>c</Xa> <foo></bar>", beExtremelyLenient=1
        )
        self.assertEqual(d.documentElement.firstChild().toxml(), "<xa><y>c</y></xa>")

    def test_laterCloserSimple(self):
        s = "<ul><li>foo<li>bar<li>baz</ul>"
        d = microdom.parseString(s, beExtremelyLenient=1)
        expected = "<ul><li>foo</li><li>bar</li><li>baz</li></ul>"
        actual = d.documentElement.toxml()
        self.assertEqual(expected, actual)

    def test_laterCloserCaseInsensitive(self):
        s = "<DL><p><DT>foo<DD>bar</DL>"
        d = microdom.parseString(s, beExtremelyLenient=1)
        expected = "<dl><p></p><dt>foo</dt><dd>bar</dd></dl>"
        actual = d.documentElement.toxml()
        self.assertEqual(expected, actual)

    def test_laterCloserDL(self):
        s = (
            "<dl>"
            "<dt>word<dd>definition"
            "<dt>word<dt>word<dd>definition<dd>definition"
            "</dl>"
        )
        expected = (
            "<dl>"
            "<dt>word</dt><dd>definition</dd>"
            "<dt>word</dt><dt>word</dt><dd>definition</dd><dd>definition</dd>"
            "</dl>"
        )
        d = microdom.parseString(s, beExtremelyLenient=1)
        actual = d.documentElement.toxml()
        self.assertEqual(expected, actual)

    def test_unicodeTolerance(self):
        import struct

        s = "<foo><bar><baz /></bar></foo>"
        j = (
            '<?xml version="1.0" encoding="UCS-2" ?>\r\n<JAPANESE>\r\n'
            "<TITLE>\u5c02\u9580\u5bb6\u30ea\u30b9\u30c8 </TITLE></JAPANESE>"
        )
        j2 = (
            b"\xff\xfe<\x00?\x00x\x00m\x00l\x00 \x00v\x00e\x00r\x00s\x00i\x00o"
            b'\x00n\x00=\x00"\x001\x00.\x000\x00"\x00 \x00e\x00n\x00c\x00o\x00d'
            b'\x00i\x00n\x00g\x00=\x00"\x00U\x00C\x00S\x00-\x002\x00"\x00 \x00?'
            b"\x00>\x00\r\x00\n\x00<\x00J\x00A\x00P\x00A\x00N\x00E\x00S\x00E"
            b"\x00>\x00\r\x00\n\x00<\x00T\x00I\x00T\x00L\x00E\x00>\x00\x02\\"
            b"\x80\x95\xb6[\xea0\xb90\xc80 \x00<\x00/\x00T\x00I\x00T\x00L\x00E"
            b"\x00>\x00<\x00/\x00J\x00A\x00P\x00A\x00N\x00E\x00S\x00E\x00>\x00"
        )

        def reverseBytes(s):
            fmt = str(len(s) // 2) + "H"
            return struct.pack("<" + fmt, *struct.unpack(">" + fmt, s))

        urd = microdom.parseString(reverseBytes(s.encode("UTF-16")))
        ud = microdom.parseString(s.encode("UTF-16"))
        sd = microdom.parseString(s)
        self.assertTrue(ud.isEqualToDocument(sd))
        self.assertTrue(ud.isEqualToDocument(urd))
        ud = microdom.parseString(j)
        urd = microdom.parseString(reverseBytes(j2))
        sd = microdom.parseString(j2)
        self.assertTrue(ud.isEqualToDocument(sd))
        self.assertTrue(ud.isEqualToDocument(urd))

        # test that raw text still gets encoded
        # test that comments get encoded
        j3 = microdom.parseString("<foo/>")
        hdr = '<?xml version="1.0"?>'
        div = microdom.lmx().text("\u221a", raw=1).node
        de = j3.documentElement
        de.appendChild(div)
        de.appendChild(j3.createComment("\u221a"))
        self.assertEqual(
            j3.toxml(), (hdr + "<foo><div>\u221a</div><!--\u221a--></foo>")
        )

    def test_namedChildren(self):
        tests = {
            "<foo><bar /><bar unf='1' /><bar>asdfadsf</bar>" "<bam/></foo>": 3,
            "<foo>asdf</foo>": 0,
            "<foo><bar><bar></bar></bar></foo>": 1,
        }
        for t in tests.keys():
            node = microdom.parseString(t).documentElement
            result = domhelpers.namedChildren(node, "bar")
            self.assertEqual(len(result), tests[t])
            if result:
                self.assertTrue(hasattr(result[0], "tagName"))

    def test_cloneNode(self):
        s = '<foo a="b"><bax>x</bax></foo>'
        node = microdom.parseString(s).documentElement
        clone = node.cloneNode(deep=1)
        self.failIfEquals(node, clone)
        self.assertEqual(len(node.childNodes), len(clone.childNodes))
        c1, c2 = node.firstChild(), clone.firstChild()
        self.failIfEquals(c1, c2)
        self.assertEqual(len(c1.childNodes), len(c2.childNodes))
        self.failIfEquals(c1.firstChild(), c2.firstChild())
        self.assertEqual(s, clone.toxml())
        self.assertEqual(node.namespace, clone.namespace)

    def test_cloneDocument(self):
        s = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"'
            '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><foo></foo>'
        )

        node = microdom.parseString(s)
        clone = node.cloneNode(deep=1)
        self.failIfEquals(node, clone)
        self.assertEqual(len(node.childNodes), len(clone.childNodes))
        self.assertEqual(s, clone.toxml())

        self.assertTrue(clone.isEqualToDocument(node))
        self.assertTrue(node.isEqualToDocument(clone))

    def test_LMX(self):
        n = microdom.Element("p")
        lmx = microdom.lmx(n)
        lmx.text("foo")
        b = lmx.b(a="c")
        b.foo()["z"] = "foo"
        b.foo()
        b.add("bar", c="y")

        s = '<p>foo<b a="c"><foo z="foo"></foo><foo></foo><bar c="y"></bar></b></p>'
        self.assertEqual(s, n.toxml())

    def test_dict(self):
        """
        Returns a dictionary which is hashable.
        """
        n = microdom.Element("p")
        hash(n)

    def test_escaping(self):
        # issue 590
        raw = "&'some \"stuff\"', <what up?>"
        cooked = "&amp;'some &quot;stuff&quot;', &lt;what up?&gt;"
        esc1 = microdom.escape(raw)
        self.assertEqual(esc1, cooked)
        self.assertEqual(microdom.unescape(esc1), raw)

    def test_namespaces(self):
        s = """
        <x xmlns="base">
        <y />
        <y q="1" x:q="2" y:q="3" />
        <y:y xml:space="1">here is    some space </y:y>
        <y:y />
        <x:y />
        </x>
        """
        d = microdom.parseString(s)
        # at least make sure it doesn't traceback
        s2 = d.toprettyxml()
        self.assertEqual(d.documentElement.namespace, "base")
        self.assertEqual(
            d.documentElement.getElementsByTagName("y")[0].namespace, "base"
        )
        self.assertEqual(
            d.documentElement.getElementsByTagName("y")[1].getAttributeNS("base", "q"),
            "1",
        )

        d2 = microdom.parseString(s2)
        self.assertEqual(d2.documentElement.namespace, "base")
        self.assertEqual(
            d2.documentElement.getElementsByTagName("y")[0].namespace, "base"
        )
        self.assertEqual(
            d2.documentElement.getElementsByTagName("y")[1].getAttributeNS("base", "q"),
            "1",
        )

    def test_namespaceDelete(self):
        """
        Test that C{toxml} can support xml structures that remove namespaces.
        """
        s1 = (
            '<?xml version="1.0"?><html xmlns="http://www.w3.org/TR/REC-html40">'
            '<body xmlns=""></body></html>'
        )
        s2 = microdom.parseString(s1).toxml()
        self.assertEqual(s1, s2)

    def test_namespaceInheritance(self):
        """
        Check that unspecified namespace is a thing separate from undefined
        namespace. This test added after discovering some weirdness in Lore.
        """
        # will only work if childNodes is mutated. not sure why.
        child = microdom.Element("ol")
        parent = microdom.Element("div", namespace="http://www.w3.org/1999/xhtml")
        parent.childNodes = [child]
        self.assertEqual(
            parent.toxml(), '<div xmlns="http://www.w3.org/1999/xhtml"><ol></ol></div>'
        )

    def test_prefixedTags(self):
        """
        XML elements with a prefixed name as per upper level tag definition
        have a start-tag of C{"<prefix:tag>"} and an end-tag of
        C{"</prefix:tag>"}.

        Refer to U{http://www.w3.org/TR/xml-names/#ns-using} for details.
        """
        outerNamespace = "http://example.com/outer"
        innerNamespace = "http://example.com/inner"

        document = microdom.Document()
        # Create the root in one namespace.  Microdom will probably make this
        # the default namespace.
        root = document.createElement("root", namespace=outerNamespace)

        # Give the root some prefixes to use.
        root.addPrefixes({innerNamespace: "inner"})

        # Append a child to the root from the namespace that prefix is bound
        # to.
        tag = document.createElement("tag", namespace=innerNamespace)

        # Give that tag a child too.  This way we test rendering of tags with
        # children and without children.
        child = document.createElement("child", namespace=innerNamespace)

        tag.appendChild(child)
        root.appendChild(tag)
        document.appendChild(root)

        # ok, the xml should appear like this
        xmlOk = (
            '<?xml version="1.0"?>'
            '<root xmlns="http://example.com/outer" '
            'xmlns:inner="http://example.com/inner">'
            "<inner:tag><inner:child></inner:child></inner:tag>"
            "</root>"
        )

        xmlOut = document.toxml()
        self.assertEqual(xmlOut, xmlOk)

    def test_prefixPropagation(self):
        """
        Children of prefixed tags respect the default namespace at the point
        where they are rendered.  Specifically, they are not influenced by the
        prefix of their parent as that prefix has no bearing on them.

        See U{http://www.w3.org/TR/xml-names/#scoping} for details.

        To further clarify the matter, the following::

            <root xmlns="http://example.com/ns/test">
                <mytag xmlns="http://example.com/ns/mytags">
                    <mysubtag xmlns="http://example.com/ns/mytags">
                        <element xmlns="http://example.com/ns/test"></element>
                    </mysubtag>
                </mytag>
            </root>

        Should become this after all the namespace declarations have been
        I{moved up}::

            <root xmlns="http://example.com/ns/test"
                  xmlns:mytags="http://example.com/ns/mytags">
                <mytags:mytag>
                    <mytags:mysubtag>
                        <element></element>
                    </mytags:mysubtag>
                </mytags:mytag>
            </root>
        """
        outerNamespace = "http://example.com/outer"
        innerNamespace = "http://example.com/inner"

        document = microdom.Document()
        # creates a root element
        root = document.createElement("root", namespace=outerNamespace)
        document.appendChild(root)

        # Create a child with a specific namespace with a prefix bound to it.
        root.addPrefixes({innerNamespace: "inner"})
        mytag = document.createElement("mytag", namespace=innerNamespace)
        root.appendChild(mytag)

        # Create a child of that which has the outer namespace.
        mysubtag = document.createElement("mysubtag", namespace=outerNamespace)
        mytag.appendChild(mysubtag)

        xmlOk = (
            '<?xml version="1.0"?>'
            '<root xmlns="http://example.com/outer" '
            'xmlns:inner="http://example.com/inner">'
            "<inner:mytag>"
            "<mysubtag></mysubtag>"
            "</inner:mytag>"
            "</root>"
        )
        xmlOut = document.toxml()
        self.assertEqual(xmlOut, xmlOk)


class BrokenHTMLTests(TestCase):
    """
    Tests for when microdom encounters very bad HTML and C{beExtremelyLenient}
    is enabled. These tests are inspired by some HTML generated in by a mailer,
    which breaks up very long lines by splitting them with '!\\n '.
    The expected behaviour is loosely modelled on the way Firefox treats very
    bad HTML.
    """

    def checkParsed(self, input, expected, beExtremelyLenient=1):
        """
        Check that C{input}, when parsed, produces a DOM where the XML
        of the document element is equal to C{expected}.
        """
        output = microdom.parseString(input, beExtremelyLenient=beExtremelyLenient)
        self.assertEqual(output.documentElement.toxml(), expected)

    def test_brokenAttributeName(self):
        """
        Check that microdom does its best to handle broken attribute names.
        The important thing is that it doesn't raise an exception.
        """
        input = '<body><h1><div al!\n ign="center">Foo</div></h1></body>'
        expected = '<body><h1><div al="True" ign="center">' "Foo</div></h1></body>"
        self.checkParsed(input, expected)

    def test_brokenAttributeValue(self):
        """
        Check that microdom encompasses broken attribute values.
        """
        input = '<body><h1><div align="cen!\n ter">Foo</div></h1></body>'
        expected = '<body><h1><div align="cen!\n ter">Foo</div></h1></body>'
        self.checkParsed(input, expected)

    def test_brokenOpeningTag(self):
        """
        Check that microdom does its best to handle broken opening tags.
        The important thing is that it doesn't raise an exception.
        """
        input = "<body><h1><sp!\n an>Hello World!</span></h1></body>"
        expected = '<body><h1><sp an="True">Hello World!</sp></h1></body>'
        self.checkParsed(input, expected)

    def test_brokenSelfClosingTag(self):
        """
        Check that microdom does its best to handle broken self-closing tags
        The important thing is that it doesn't raise an exception.
        """
        self.checkParsed("<body><span /!\n></body>", "<body><span></span></body>")
        self.checkParsed("<span!\n />", "<span></span>")

    def test_brokenClosingTag(self):
        """
        Check that microdom does its best to handle broken closing tags.
        The important thing is that it doesn't raise an exception.
        """
        input = "<body><h1><span>Hello World!</sp!\nan></h1></body>"
        expected = "<body><h1><span>Hello World!</span></h1></body>"
        self.checkParsed(input, expected)
        input = "<body><h1><span>Hello World!</!\nspan></h1></body>"
        self.checkParsed(input, expected)
        input = "<body><h1><span>Hello World!</span!\n></h1></body>"
        self.checkParsed(input, expected)
        input = "<body><h1><span>Hello World!<!\n/span></h1></body>"
        expected = "<body><h1><span>Hello World!<!></!></span></h1></body>"
        self.checkParsed(input, expected)


class NodeTests(TestCase):
    """
    Tests for L{Node}.
    """

    def test_isNodeEqualTo(self):
        """
        L{Node.isEqualToNode} returns C{True} if and only if passed a L{Node}
        with the same children.
        """
        # A node is equal to itself
        node = microdom.Node(object())
        self.assertTrue(node.isEqualToNode(node))
        another = microdom.Node(object())
        # Two nodes with no children are equal
        self.assertTrue(node.isEqualToNode(another))
        node.appendChild(microdom.Node(object()))
        # A node with no children is not equal to a node with a child
        self.assertFalse(node.isEqualToNode(another))
        another.appendChild(microdom.Node(object()))
        # A node with a child and no grandchildren is equal to another node
        # with a child and no grandchildren.
        self.assertTrue(node.isEqualToNode(another))
        # A node with a child and a grandchild is not equal to another node
        # with a child and no grandchildren.
        node.firstChild().appendChild(microdom.Node(object()))
        self.assertFalse(node.isEqualToNode(another))
        # A node with a child and a grandchild is equal to another node with a
        # child and a grandchild.
        another.firstChild().appendChild(microdom.Node(object()))
        self.assertTrue(node.isEqualToNode(another))

    def test_validChildInstance(self):
        """
        Children of L{Node} instances must also be L{Node} instances.
        """
        node = microdom.Node()
        child = microdom.Node()
        # Node.appendChild() only accepts Node instances.
        node.appendChild(child)
        self.assertRaises(TypeError, node.appendChild, None)
        # Node.insertBefore() only accepts Node instances.
        self.assertRaises(TypeError, node.insertBefore, child, None)
        self.assertRaises(TypeError, node.insertBefore, None, child)
        self.assertRaises(TypeError, node.insertBefore, None, None)
        # Node.removeChild() only accepts Node instances.
        node.removeChild(child)
        self.assertRaises(TypeError, node.removeChild, None)
        # Node.replaceChild() only accepts Node instances.
        self.assertRaises(TypeError, node.replaceChild, child, None)
        self.assertRaises(TypeError, node.replaceChild, None, child)
        self.assertRaises(TypeError, node.replaceChild, None, None)


class DocumentTests(TestCase):
    """
    Tests for L{Document}.
    """

    doctype = 'foo PUBLIC "baz" "http://www.example.com/example.dtd"'

    def test_isEqualToNode(self):
        """
        L{Document.isEqualToNode} returns C{True} if and only if passed a
        L{Document} with the same C{doctype} and C{documentElement}.
        """
        # A document is equal to itself
        document = microdom.Document()
        self.assertTrue(document.isEqualToNode(document))
        # A document without a doctype or documentElement is equal to another
        # document without a doctype or documentElement.
        another = microdom.Document()
        self.assertTrue(document.isEqualToNode(another))
        # A document with a doctype is not equal to a document without a
        # doctype.
        document.doctype = self.doctype
        self.assertFalse(document.isEqualToNode(another))
        # Two documents with the same doctype are equal
        another.doctype = self.doctype
        self.assertTrue(document.isEqualToNode(another))
        # A document with a documentElement is not equal to a document without
        # a documentElement
        document.appendChild(microdom.Node(object()))
        self.assertFalse(document.isEqualToNode(another))
        # Two documents with equal documentElements are equal.
        another.appendChild(microdom.Node(object()))
        self.assertTrue(document.isEqualToNode(another))
        # Two documents with documentElements which are not equal are not
        # equal.
        document.documentElement.appendChild(microdom.Node(object()))
        self.assertFalse(document.isEqualToNode(another))

    def test_childRestriction(self):
        """
        L{Document.appendChild} raises L{ValueError} if the document already
        has a child.
        """
        document = microdom.Document()
        child = microdom.Node()
        another = microdom.Node()
        document.appendChild(child)
        self.assertRaises(ValueError, document.appendChild, another)


class EntityReferenceTests(TestCase):
    """
    Tests for L{EntityReference}.
    """

    def test_isEqualToNode(self):
        """
        L{EntityReference.isEqualToNode} returns C{True} if and only if passed
        a L{EntityReference} with the same C{eref}.
        """
        self.assertTrue(
            microdom.EntityReference("quot").isEqualToNode(
                microdom.EntityReference("quot")
            )
        )
        self.assertFalse(
            microdom.EntityReference("quot").isEqualToNode(
                microdom.EntityReference("apos")
            )
        )


class CharacterDataTests(TestCase):
    """
    Tests for L{CharacterData}.
    """

    def test_isEqualToNode(self):
        """
        L{CharacterData.isEqualToNode} returns C{True} if and only if passed a
        L{CharacterData} with the same value.
        """
        self.assertTrue(
            microdom.CharacterData("foo").isEqualToNode(microdom.CharacterData("foo"))
        )
        self.assertFalse(
            microdom.CharacterData("foo").isEqualToNode(microdom.CharacterData("bar"))
        )


class CommentTests(TestCase):
    """
    Tests for L{Comment}.
    """

    def test_isEqualToNode(self):
        """
        L{Comment.isEqualToNode} returns C{True} if and only if passed a
        L{Comment} with the same value.
        """
        self.assertTrue(microdom.Comment("foo").isEqualToNode(microdom.Comment("foo")))
        self.assertFalse(microdom.Comment("foo").isEqualToNode(microdom.Comment("bar")))


class TextTests(TestCase):
    """
    Tests for L{Text}.
    """

    def test_isEqualToNode(self):
        """
        L{Text.isEqualToNode} returns C{True} if and only if passed a L{Text}
        which represents the same data.
        """
        self.assertTrue(
            microdom.Text("foo", raw=True).isEqualToNode(microdom.Text("foo", raw=True))
        )
        self.assertFalse(
            microdom.Text("foo", raw=True).isEqualToNode(
                microdom.Text("foo", raw=False)
            )
        )
        self.assertFalse(
            microdom.Text("foo", raw=True).isEqualToNode(microdom.Text("bar", raw=True))
        )


class CDATASectionTests(TestCase):
    """
    Tests for L{CDATASection}.
    """

    def test_isEqualToNode(self):
        """
        L{CDATASection.isEqualToNode} returns C{True} if and only if passed a
        L{CDATASection} which represents the same data.
        """
        self.assertTrue(
            microdom.CDATASection("foo").isEqualToNode(microdom.CDATASection("foo"))
        )
        self.assertFalse(
            microdom.CDATASection("foo").isEqualToNode(microdom.CDATASection("bar"))
        )


class ElementTests(TestCase):
    """
    Tests for L{Element}.
    """

    def test_isEqualToNode(self):
        """
        L{Element.isEqualToNode} returns C{True} if and only if passed a
        L{Element} with the same C{nodeName}, C{namespace}, C{childNodes}, and
        C{attributes}.
        """
        self.assertTrue(
            microdom.Element(
                "foo", {"a": "b"}, object(), namespace="bar"
            ).isEqualToNode(
                microdom.Element("foo", {"a": "b"}, object(), namespace="bar")
            )
        )

        # Elements with different nodeName values do not compare equal.
        self.assertFalse(
            microdom.Element(
                "foo", {"a": "b"}, object(), namespace="bar"
            ).isEqualToNode(
                microdom.Element("bar", {"a": "b"}, object(), namespace="bar")
            )
        )

        # Elements with different namespaces do not compare equal.
        self.assertFalse(
            microdom.Element(
                "foo", {"a": "b"}, object(), namespace="bar"
            ).isEqualToNode(
                microdom.Element("foo", {"a": "b"}, object(), namespace="baz")
            )
        )

        # Elements with different childNodes do not compare equal.
        one = microdom.Element("foo", {"a": "b"}, object(), namespace="bar")
        two = microdom.Element("foo", {"a": "b"}, object(), namespace="bar")
        two.appendChild(microdom.Node(object()))
        self.assertFalse(one.isEqualToNode(two))

        # Elements with different attributes do not compare equal.
        self.assertFalse(
            microdom.Element(
                "foo", {"a": "b"}, object(), namespace="bar"
            ).isEqualToNode(
                microdom.Element("foo", {"a": "c"}, object(), namespace="bar")
            )
        )
