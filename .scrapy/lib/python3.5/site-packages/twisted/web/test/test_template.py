# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.template}
"""

from __future__ import division, absolute_import

from zope.interface.verify import verifyObject

from twisted.internet.defer import succeed, gatherResults
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.trial.util import suppress as SUPPRESS
from twisted.web.template import (
    Element, TagLoader, renderer, tags, XMLFile, XMLString)
from twisted.web.iweb import ITemplateLoader

from twisted.web.error import (FlattenerError, MissingTemplateLoader,
    MissingRenderMethod)

from twisted.web.template import renderElement
from twisted.web._element import UnexposedMethodError
from twisted.web.test._util import FlattenTestCase
from twisted.web.test.test_web import DummyRequest
from twisted.web.server import NOT_DONE_YET

from twisted.python.compat import NativeStringIO as StringIO


_xmlFileSuppress = SUPPRESS(category=DeprecationWarning,
        message="Passing filenames or file objects to XMLFile is "
                "deprecated since Twisted 12.1.  Pass a FilePath instead.")


class TagFactoryTests(TestCase):
    """
    Tests for L{_TagFactory} through the publicly-exposed L{tags} object.
    """
    def test_lookupTag(self):
        """
        HTML tags can be retrieved through C{tags}.
        """
        tag = tags.a
        self.assertEqual(tag.tagName, "a")


    def test_lookupHTML5Tag(self):
        """
        Twisted supports the latest and greatest HTML tags from the HTML5
        specification.
        """
        tag = tags.video
        self.assertEqual(tag.tagName, "video")


    def test_lookupTransparentTag(self):
        """
        To support transparent inclusion in templates, there is a special tag,
        the transparent tag, which has no name of its own but is accessed
        through the "transparent" attribute.
        """
        tag = tags.transparent
        self.assertEqual(tag.tagName, "")


    def test_lookupInvalidTag(self):
        """
        Invalid tags which are not part of HTML cause AttributeErrors when
        accessed through C{tags}.
        """
        self.assertRaises(AttributeError, getattr, tags, "invalid")


    def test_lookupXMP(self):
        """
        As a special case, the <xmp> tag is simply not available through
        C{tags} or any other part of the templating machinery.
        """
        self.assertRaises(AttributeError, getattr, tags, "xmp")



class ElementTests(TestCase):
    """
    Tests for the awesome new L{Element} class.
    """
    def test_missingTemplateLoader(self):
        """
        L{Element.render} raises L{MissingTemplateLoader} if the C{loader}
        attribute is L{None}.
        """
        element = Element()
        err = self.assertRaises(MissingTemplateLoader, element.render, None)
        self.assertIdentical(err.element, element)


    def test_missingTemplateLoaderRepr(self):
        """
        A L{MissingTemplateLoader} instance can be repr()'d without error.
        """
        class PrettyReprElement(Element):
            def __repr__(self):
                return 'Pretty Repr Element'
        self.assertIn('Pretty Repr Element',
                      repr(MissingTemplateLoader(PrettyReprElement())))


    def test_missingRendererMethod(self):
        """
        When called with the name which is not associated with a render method,
        L{Element.lookupRenderMethod} raises L{MissingRenderMethod}.
        """
        element = Element()
        err = self.assertRaises(
            MissingRenderMethod, element.lookupRenderMethod, "foo")
        self.assertIdentical(err.element, element)
        self.assertEqual(err.renderName, "foo")


    def test_missingRenderMethodRepr(self):
        """
        A L{MissingRenderMethod} instance can be repr()'d without error.
        """
        class PrettyReprElement(Element):
            def __repr__(self):
                return 'Pretty Repr Element'
        s = repr(MissingRenderMethod(PrettyReprElement(),
                                     'expectedMethod'))
        self.assertIn('Pretty Repr Element', s)
        self.assertIn('expectedMethod', s)


    def test_definedRenderer(self):
        """
        When called with the name of a defined render method,
        L{Element.lookupRenderMethod} returns that render method.
        """
        class ElementWithRenderMethod(Element):
            @renderer
            def foo(self, request, tag):
                return "bar"
        foo = ElementWithRenderMethod().lookupRenderMethod("foo")
        self.assertEqual(foo(None, None), "bar")


    def test_render(self):
        """
        L{Element.render} loads a document from the C{loader} attribute and
        returns it.
        """
        class TemplateLoader(object):
            def load(self):
                return "result"

        class StubElement(Element):
            loader = TemplateLoader()

        element = StubElement()
        self.assertEqual(element.render(None), "result")


    def test_misuseRenderer(self):
        """
        If the L{renderer} decorator  is called without any arguments, it will
        raise a comprehensible exception.
        """
        te = self.assertRaises(TypeError, renderer)
        self.assertEqual(str(te),
                         "expose() takes at least 1 argument (0 given)")


    def test_renderGetDirectlyError(self):
        """
        Called directly, without a default, L{renderer.get} raises
        L{UnexposedMethodError} when it cannot find a renderer.
        """
        self.assertRaises(UnexposedMethodError, renderer.get, None,
                          "notARenderer")



class XMLFileReprTests(TestCase):
    """
    Tests for L{twisted.web.template.XMLFile}'s C{__repr__}.
    """
    def test_filePath(self):
        """
        An L{XMLFile} with a L{FilePath} returns a useful repr().
        """
        path = FilePath("/tmp/fake.xml")
        self.assertEqual('<XMLFile of %r>' % (path,), repr(XMLFile(path)))


    def test_filename(self):
        """
        An L{XMLFile} with a filename returns a useful repr().
        """
        fname = "/tmp/fake.xml"
        self.assertEqual('<XMLFile of %r>' % (fname,), repr(XMLFile(fname)))
    test_filename.suppress = [_xmlFileSuppress]


    def test_file(self):
        """
        An L{XMLFile} with a file object returns a useful repr().
        """
        fobj = StringIO("not xml")
        self.assertEqual('<XMLFile of %r>' % (fobj,), repr(XMLFile(fobj)))
    test_file.suppress = [_xmlFileSuppress]



class XMLLoaderTestsMixin(object):
    """
    @ivar templateString: Simple template to use to exercise the loaders.

    @ivar deprecatedUse: C{True} if this use of L{XMLFile} is deprecated and
        should emit a C{DeprecationWarning}.
    """

    loaderFactory = None
    templateString = '<p>Hello, world.</p>'
    def test_load(self):
        """
        Verify that the loader returns a tag with the correct children.
        """
        loader = self.loaderFactory()
        tag, = loader.load()

        warnings = self.flushWarnings(offendingFunctions=[self.loaderFactory])
        if self.deprecatedUse:
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]['category'], DeprecationWarning)
            self.assertEqual(
                warnings[0]['message'],
                "Passing filenames or file objects to XMLFile is "
                "deprecated since Twisted 12.1.  Pass a FilePath instead.")
        else:
            self.assertEqual(len(warnings), 0)

        self.assertEqual(tag.tagName, 'p')
        self.assertEqual(tag.children, [u'Hello, world.'])


    def test_loadTwice(self):
        """
        If {load()} can be called on a loader twice the result should be the
        same.
        """
        loader = self.loaderFactory()
        tags1 = loader.load()
        tags2 = loader.load()
        self.assertEqual(tags1, tags2)
    test_loadTwice.suppress = [_xmlFileSuppress]



class XMLStringLoaderTests(TestCase, XMLLoaderTestsMixin):
    """
    Tests for L{twisted.web.template.XMLString}
    """
    deprecatedUse = False
    def loaderFactory(self):
        """
        @return: an L{XMLString} constructed with C{self.templateString}.
        """
        return XMLString(self.templateString)



class XMLFileWithFilePathTests(TestCase, XMLLoaderTestsMixin):
    """
    Tests for L{twisted.web.template.XMLFile}'s L{FilePath} support.
    """
    deprecatedUse = False
    def loaderFactory(self):
        """
        @return: an L{XMLString} constructed with a L{FilePath} pointing to a
            file that contains C{self.templateString}.
        """
        fp = FilePath(self.mktemp())
        fp.setContent(self.templateString.encode("utf8"))
        return XMLFile(fp)



class XMLFileWithFileTests(TestCase, XMLLoaderTestsMixin):
    """
    Tests for L{twisted.web.template.XMLFile}'s deprecated file object support.
    """
    deprecatedUse = True
    def loaderFactory(self):
        """
        @return: an L{XMLString} constructed with a file object that contains
            C{self.templateString}.
        """
        return XMLFile(StringIO(self.templateString))



class XMLFileWithFilenameTests(TestCase, XMLLoaderTestsMixin):
    """
    Tests for L{twisted.web.template.XMLFile}'s deprecated filename support.
    """
    deprecatedUse = True
    def loaderFactory(self):
        """
        @return: an L{XMLString} constructed with a filename that points to a
            file containing C{self.templateString}.
        """
        fp = FilePath(self.mktemp())
        fp.setContent(self.templateString.encode('utf8'))
        return XMLFile(fp.path)



class FlattenIntegrationTests(FlattenTestCase):
    """
    Tests for integration between L{Element} and
    L{twisted.web._flatten.flatten}.
    """

    def test_roundTrip(self):
        """
        Given a series of parsable XML strings, verify that
        L{twisted.web._flatten.flatten} will flatten the L{Element} back to the
        input when sent on a round trip.
        """
        fragments = [
            b"<p>Hello, world.</p>",
            b"<p><!-- hello, world --></p>",
            b"<p><![CDATA[Hello, world.]]></p>",
            b'<test1 xmlns:test2="urn:test2">'
            b'<test2:test3></test2:test3></test1>',
            b'<test1 xmlns="urn:test2"><test3></test3></test1>',
            b'<p>\xe2\x98\x83</p>',
        ]
        deferreds = [
            self.assertFlattensTo(Element(loader=XMLString(xml)), xml)
            for xml in fragments]
        return gatherResults(deferreds)


    def test_entityConversion(self):
        """
        When flattening an HTML entity, it should flatten out to the utf-8
        representation if possible.
        """
        element = Element(loader=XMLString('<p>&#9731;</p>'))
        return self.assertFlattensTo(element, b'<p>\xe2\x98\x83</p>')


    def test_missingTemplateLoader(self):
        """
        Rendering an Element without a loader attribute raises the appropriate
        exception.
        """
        return self.assertFlatteningRaises(Element(), MissingTemplateLoader)


    def test_missingRenderMethod(self):
        """
        Flattening an L{Element} with a C{loader} which has a tag with a render
        directive fails with L{FlattenerError} if there is no available render
        method to satisfy that directive.
        """
        element = Element(loader=XMLString("""
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="unknownMethod" />
        """))
        return self.assertFlatteningRaises(element, MissingRenderMethod)


    def test_transparentRendering(self):
        """
        A C{transparent} element should be eliminated from the DOM and rendered as
        only its children.
        """
        element = Element(loader=XMLString(
            '<t:transparent '
            'xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
            'Hello, world.'
            '</t:transparent>'
        ))
        return self.assertFlattensTo(element, b"Hello, world.")


    def test_attrRendering(self):
        """
        An Element with an attr tag renders the vaule of its attr tag as an
        attribute of its containing tag.
        """
        element = Element(loader=XMLString(
            '<a xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
            '<t:attr name="href">http://example.com</t:attr>'
            'Hello, world.'
            '</a>'
        ))
        return self.assertFlattensTo(element,
            b'<a href="http://example.com">Hello, world.</a>')


    def test_errorToplevelAttr(self):
        """
        A template with a toplevel C{attr} tag will not load; it will raise
        L{AssertionError} if you try.
        """
        self.assertRaises(
            AssertionError,
            XMLString,
            """<t:attr
            xmlns:t='http://twistedmatrix.com/ns/twisted.web.template/0.1'
            name='something'
            >hello</t:attr>
            """)


    def test_errorUnnamedAttr(self):
        """
        A template with an C{attr} tag with no C{name} attribute will not load;
        it will raise L{AssertionError} if you try.
        """
        self.assertRaises(
            AssertionError,
            XMLString,
            """<html><t:attr
            xmlns:t='http://twistedmatrix.com/ns/twisted.web.template/0.1'
            >hello</t:attr></html>""")


    def test_lenientPrefixBehavior(self):
        """
        If the parser sees a prefix it doesn't recognize on an attribute, it
        will pass it on through to serialization.
        """
        theInput = (
            '<hello:world hello:sample="testing" '
            'xmlns:hello="http://made-up.example.com/ns/not-real">'
            'This is a made-up tag.</hello:world>')
        element = Element(loader=XMLString(theInput))
        self.assertFlattensTo(element, theInput.encode('utf8'))


    def test_deferredRendering(self):
        """
        An Element with a render method which returns a Deferred will render
        correctly.
        """
        class RenderfulElement(Element):
            @renderer
            def renderMethod(self, request, tag):
                return succeed("Hello, world.")
        element = RenderfulElement(loader=XMLString("""
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod">
            Goodbye, world.
        </p>
        """))
        return self.assertFlattensTo(element, b"Hello, world.")


    def test_loaderClassAttribute(self):
        """
        If there is a non-None loader attribute on the class of an Element
        instance but none on the instance itself, the class attribute is used.
        """
        class SubElement(Element):
            loader = XMLString("<p>Hello, world.</p>")
        return self.assertFlattensTo(SubElement(), b"<p>Hello, world.</p>")


    def test_directiveRendering(self):
        """
        An Element with a valid render directive has that directive invoked and
        the result added to the output.
        """
        renders = []
        class RenderfulElement(Element):
            @renderer
            def renderMethod(self, request, tag):
                renders.append((self, request))
                return tag("Hello, world.")
        element = RenderfulElement(loader=XMLString("""
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod" />
        """))
        return self.assertFlattensTo(element, b"<p>Hello, world.</p>")


    def test_directiveRenderingOmittingTag(self):
        """
        An Element with a render method which omits the containing tag
        successfully removes that tag from the output.
        """
        class RenderfulElement(Element):
            @renderer
            def renderMethod(self, request, tag):
                return "Hello, world."
        element = RenderfulElement(loader=XMLString("""
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod">
            Goodbye, world.
        </p>
        """))
        return self.assertFlattensTo(element, b"Hello, world.")


    def test_elementContainingStaticElement(self):
        """
        An Element which is returned by the render method of another Element is
        rendered properly.
        """
        class RenderfulElement(Element):
            @renderer
            def renderMethod(self, request, tag):
                return tag(Element(
                    loader=XMLString("<em>Hello, world.</em>")))
        element = RenderfulElement(loader=XMLString("""
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod" />
        """))
        return self.assertFlattensTo(element, b"<p><em>Hello, world.</em></p>")


    def test_elementUsingSlots(self):
        """
        An Element which is returned by the render method of another Element is
        rendered properly.
        """
        class RenderfulElement(Element):
            @renderer
            def renderMethod(self, request, tag):
                return tag.fillSlots(test2='world.')
        element = RenderfulElement(loader=XMLString(
            '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"'
            ' t:render="renderMethod">'
            '<t:slot name="test1" default="Hello, " />'
            '<t:slot name="test2" />'
            '</p>'
        ))
        return self.assertFlattensTo(element, b"<p>Hello, world.</p>")


    def test_elementContainingDynamicElement(self):
        """
        Directives in the document factory of an Element returned from a render
        method of another Element are satisfied from the correct object: the
        "inner" Element.
        """
        class OuterElement(Element):
            @renderer
            def outerMethod(self, request, tag):
                return tag(InnerElement(loader=XMLString("""
                <t:ignored
                  xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
                  t:render="innerMethod" />
                """)))
        class InnerElement(Element):
            @renderer
            def innerMethod(self, request, tag):
                return "Hello, world."
        element = OuterElement(loader=XMLString("""
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="outerMethod" />
        """))
        return self.assertFlattensTo(element, b"<p>Hello, world.</p>")


    def test_sameLoaderTwice(self):
        """
        Rendering the output of a loader, or even the same element, should
        return different output each time.
        """
        sharedLoader = XMLString(
            '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
            '<t:transparent t:render="classCounter" /> '
            '<t:transparent t:render="instanceCounter" />'
            '</p>')

        class DestructiveElement(Element):
            count = 0
            instanceCount = 0
            loader = sharedLoader

            @renderer
            def classCounter(self, request, tag):
                DestructiveElement.count += 1
                return tag(str(DestructiveElement.count))
            @renderer
            def instanceCounter(self, request, tag):
                self.instanceCount += 1
                return tag(str(self.instanceCount))

        e1 = DestructiveElement()
        e2 = DestructiveElement()
        self.assertFlattensImmediately(e1, b"<p>1 1</p>")
        self.assertFlattensImmediately(e1, b"<p>2 2</p>")
        self.assertFlattensImmediately(e2, b"<p>3 1</p>")



class TagLoaderTests(FlattenTestCase):
    """
    Tests for L{TagLoader}.
    """
    def setUp(self):
        self.loader = TagLoader(tags.i('test'))


    def test_interface(self):
        """
        An instance of L{TagLoader} provides L{ITemplateLoader}.
        """
        self.assertTrue(verifyObject(ITemplateLoader, self.loader))


    def test_loadsList(self):
        """
        L{TagLoader.load} returns a list, per L{ITemplateLoader}.
        """
        self.assertIsInstance(self.loader.load(), list)


    def test_flatten(self):
        """
        L{TagLoader} can be used in an L{Element}, and flattens as the tag used
        to construct the L{TagLoader} would flatten.
        """
        e = Element(self.loader)
        self.assertFlattensImmediately(e, b'<i>test</i>')



class TestElement(Element):
    """
    An L{Element} that can be rendered successfully.
    """
    loader = XMLString(
        '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
        'Hello, world.'
        '</p>')



class TestFailureElement(Element):
    """
    An L{Element} that can be used in place of L{FailureElement} to verify
    that L{renderElement} can render failures properly.
    """
    loader = XMLString(
        '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
        'I failed.'
        '</p>')

    def __init__(self, failure, loader=None):
        self.failure = failure



class FailingElement(Element):
    """
    An element that raises an exception when rendered.
    """
    def render(self, request):
        a = 42
        b = 0
        return a // b



class FakeSite(object):
    """
    A minimal L{Site} object that we can use to test displayTracebacks
    """
    displayTracebacks = False



class RenderElementTests(TestCase):
    """
    Test L{renderElement}
    """

    def setUp(self):
        """
        Set up a common L{DummyRequest} and L{FakeSite}.
        """
        self.request = DummyRequest([""])
        self.request.site = FakeSite()


    def test_simpleRender(self):
        """
        L{renderElement} returns NOT_DONE_YET and eventually
        writes the rendered L{Element} to the request before finishing the
        request.
        """
        element = TestElement()

        d = self.request.notifyFinish()

        def check(_):
            self.assertEqual(
                b"".join(self.request.written),
                b"<!DOCTYPE html>\n"
                b"<p>Hello, world.</p>")
            self.assertTrue(self.request.finished)

        d.addCallback(check)

        self.assertIdentical(NOT_DONE_YET, renderElement(self.request, element))

        return d


    def test_simpleFailure(self):
        """
        L{renderElement} handles failures by writing a minimal
        error message to the request and finishing it.
        """
        element = FailingElement()

        d = self.request.notifyFinish()

        def check(_):
            flushed = self.flushLoggedErrors(FlattenerError)
            self.assertEqual(len(flushed), 1)
            self.assertEqual(
                b"".join(self.request.written),
                (b'<!DOCTYPE html>\n'
                 b'<div style="font-size:800%;'
                 b'background-color:#FFF;'
                 b'color:#F00'
                 b'">An error occurred while rendering the response.</div>'))
            self.assertTrue(self.request.finished)

        d.addCallback(check)

        self.assertIdentical(NOT_DONE_YET, renderElement(self.request, element))

        return d


    def test_simpleFailureWithTraceback(self):
        """
        L{renderElement} will render a traceback when rendering of
        the element fails and our site is configured to display tracebacks.
        """
        self.request.site.displayTracebacks = True

        element = FailingElement()

        d = self.request.notifyFinish()

        def check(_):
            flushed = self.flushLoggedErrors(FlattenerError)
            self.assertEqual(len(flushed), 1)
            self.assertEqual(
                b"".join(self.request.written),
                b"<!DOCTYPE html>\n<p>I failed.</p>")
            self.assertTrue(self.request.finished)

        d.addCallback(check)

        renderElement(self.request, element, _failElement=TestFailureElement)

        return d


    def test_nonDefaultDoctype(self):
        """
        L{renderElement} will write the doctype string specified by the
        doctype keyword argument.
        """
        element = TestElement()

        d = self.request.notifyFinish()

        def check(_):
            self.assertEqual(
                b"".join(self.request.written),
                (b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
                 b' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n'
                 b'<p>Hello, world.</p>'))

        d.addCallback(check)

        renderElement(
            self.request,
            element,
            doctype=(
                b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
                b' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'))

        return d


    def test_noneDoctype(self):
        """
        L{renderElement} will not write out a doctype if the doctype keyword
        argument is L{None}.
        """
        element = TestElement()

        d = self.request.notifyFinish()

        def check(_):
            self.assertEqual(
                b"".join(self.request.written),
                b'<p>Hello, world.</p>')

        d.addCallback(check)

        renderElement(self.request, element, doctype=None)

        return d
