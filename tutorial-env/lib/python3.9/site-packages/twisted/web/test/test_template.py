# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.template}
"""


from io import StringIO
from typing import List, Optional

from zope.interface import implementer
from zope.interface.verify import verifyObject

from twisted.internet.defer import Deferred, succeed
from twisted.logger import globalLogPublisher
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.test.proto_helpers import EventLoggingObserver
from twisted.trial.unittest import TestCase
from twisted.trial.util import suppress as SUPPRESS
from twisted.web._element import UnexposedMethodError
from twisted.web.error import FlattenerError, MissingRenderMethod, MissingTemplateLoader
from twisted.web.iweb import IRequest, ITemplateLoader
from twisted.web.server import NOT_DONE_YET
from twisted.web.template import (
    Element,
    Flattenable,
    Tag,
    TagLoader,
    XMLFile,
    XMLString,
    renderElement,
    renderer,
    tags,
)
from twisted.web.test._util import FlattenTestCase
from twisted.web.test.test_web import DummyRequest

_xmlFileSuppress = SUPPRESS(
    category=DeprecationWarning,
    message="Passing filenames or file objects to XMLFile is "
    "deprecated since Twisted 12.1.  Pass a FilePath instead.",
)


class TagFactoryTests(TestCase):
    """
    Tests for L{_TagFactory} through the publicly-exposed L{tags} object.
    """

    def test_lookupTag(self) -> None:
        """
        HTML tags can be retrieved through C{tags}.
        """
        tag = tags.a
        self.assertEqual(tag.tagName, "a")

    def test_lookupHTML5Tag(self) -> None:
        """
        Twisted supports the latest and greatest HTML tags from the HTML5
        specification.
        """
        tag = tags.video
        self.assertEqual(tag.tagName, "video")

    def test_lookupTransparentTag(self) -> None:
        """
        To support transparent inclusion in templates, there is a special tag,
        the transparent tag, which has no name of its own but is accessed
        through the "transparent" attribute.
        """
        tag = tags.transparent
        self.assertEqual(tag.tagName, "")

    def test_lookupInvalidTag(self) -> None:
        """
        Invalid tags which are not part of HTML cause AttributeErrors when
        accessed through C{tags}.
        """
        self.assertRaises(AttributeError, getattr, tags, "invalid")

    def test_lookupXMP(self) -> None:
        """
        As a special case, the <xmp> tag is simply not available through
        C{tags} or any other part of the templating machinery.
        """
        self.assertRaises(AttributeError, getattr, tags, "xmp")


class ElementTests(TestCase):
    """
    Tests for the awesome new L{Element} class.
    """

    def test_missingTemplateLoader(self) -> None:
        """
        L{Element.render} raises L{MissingTemplateLoader} if the C{loader}
        attribute is L{None}.
        """
        element = Element()
        err = self.assertRaises(MissingTemplateLoader, element.render, None)
        self.assertIdentical(err.element, element)

    def test_missingTemplateLoaderRepr(self) -> None:
        """
        A L{MissingTemplateLoader} instance can be repr()'d without error.
        """

        class PrettyReprElement(Element):
            def __repr__(self) -> str:
                return "Pretty Repr Element"

        self.assertIn(
            "Pretty Repr Element", repr(MissingTemplateLoader(PrettyReprElement()))
        )

    def test_missingRendererMethod(self) -> None:
        """
        When called with the name which is not associated with a render method,
        L{Element.lookupRenderMethod} raises L{MissingRenderMethod}.
        """
        element = Element()
        err = self.assertRaises(MissingRenderMethod, element.lookupRenderMethod, "foo")
        self.assertIdentical(err.element, element)
        self.assertEqual(err.renderName, "foo")

    def test_missingRenderMethodRepr(self) -> None:
        """
        A L{MissingRenderMethod} instance can be repr()'d without error.
        """

        class PrettyReprElement(Element):
            def __repr__(self) -> str:
                return "Pretty Repr Element"

        s = repr(MissingRenderMethod(PrettyReprElement(), "expectedMethod"))
        self.assertIn("Pretty Repr Element", s)
        self.assertIn("expectedMethod", s)

    def test_definedRenderer(self) -> None:
        """
        When called with the name of a defined render method,
        L{Element.lookupRenderMethod} returns that render method.
        """

        class ElementWithRenderMethod(Element):
            @renderer
            def foo(self, request: Optional[IRequest], tag: Tag) -> Flattenable:
                return "bar"

        foo = ElementWithRenderMethod().lookupRenderMethod("foo")
        self.assertEqual(foo(None, tags.br), "bar")

    def test_render(self) -> None:
        """
        L{Element.render} loads a document from the C{loader} attribute and
        returns it.
        """

        @implementer(ITemplateLoader)
        class TemplateLoader:
            def load(self) -> List[Flattenable]:
                return ["result"]

        class StubElement(Element):
            loader = TemplateLoader()

        element = StubElement()
        self.assertEqual(element.render(None), ["result"])

    def test_misuseRenderer(self) -> None:
        """
        If the L{renderer} decorator  is called without any arguments, it will
        raise a comprehensible exception.
        """
        te = self.assertRaises(TypeError, renderer)
        self.assertEqual(str(te), "expose() takes at least 1 argument (0 given)")

    def test_renderGetDirectlyError(self) -> None:
        """
        Called directly, without a default, L{renderer.get} raises
        L{UnexposedMethodError} when it cannot find a renderer.
        """
        self.assertRaises(UnexposedMethodError, renderer.get, None, "notARenderer")


class XMLFileReprTests(TestCase):
    """
    Tests for L{twisted.web.template.XMLFile}'s C{__repr__}.
    """

    def test_filePath(self) -> None:
        """
        An L{XMLFile} with a L{FilePath} returns a useful repr().
        """
        path = FilePath("/tmp/fake.xml")
        self.assertEqual(f"<XMLFile of {path!r}>", repr(XMLFile(path)))

    def test_filename(self) -> None:
        """
        An L{XMLFile} with a filename returns a useful repr().
        """
        fname = "/tmp/fake.xml"  # deprecated
        self.assertEqual(f"<XMLFile of {fname!r}>", repr(XMLFile(fname)))  # type: ignore[arg-type]

    test_filename.suppress = [_xmlFileSuppress]  # type: ignore[attr-defined]

    def test_file(self) -> None:
        """
        An L{XMLFile} with a file object returns a useful repr().
        """
        fobj = StringIO("not xml")  # deprecated
        self.assertEqual(f"<XMLFile of {fobj!r}>", repr(XMLFile(fobj)))  # type: ignore[arg-type]

    test_file.suppress = [_xmlFileSuppress]  # type: ignore[attr-defined]


class XMLLoaderTestsMixin:

    deprecatedUse: bool
    """
    C{True} if this use of L{XMLFile} is deprecated and should emit
    a C{DeprecationWarning}.
    """

    templateString = "<p>Hello, world.</p>"
    """
    Simple template to use to exercise the loaders.
    """

    def loaderFactory(self) -> ITemplateLoader:
        raise NotImplementedError

    def test_load(self) -> None:
        """
        Verify that the loader returns a tag with the correct children.
        """
        assert isinstance(self, TestCase)
        loader = self.loaderFactory()
        (tag,) = loader.load()
        assert isinstance(tag, Tag)

        warnings = self.flushWarnings(offendingFunctions=[self.loaderFactory])
        if self.deprecatedUse:
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["category"], DeprecationWarning)
            self.assertEqual(
                warnings[0]["message"],
                "Passing filenames or file objects to XMLFile is "
                "deprecated since Twisted 12.1.  Pass a FilePath instead.",
            )
        else:
            self.assertEqual(len(warnings), 0)

        self.assertEqual(tag.tagName, "p")
        self.assertEqual(tag.children, ["Hello, world."])

    def test_loadTwice(self) -> None:
        """
        If {load()} can be called on a loader twice the result should be the
        same.
        """
        assert isinstance(self, TestCase)
        loader = self.loaderFactory()
        tags1 = loader.load()
        tags2 = loader.load()
        self.assertEqual(tags1, tags2)

    test_loadTwice.suppress = [_xmlFileSuppress]  # type: ignore[attr-defined]


class XMLStringLoaderTests(TestCase, XMLLoaderTestsMixin):
    """
    Tests for L{twisted.web.template.XMLString}
    """

    deprecatedUse = False

    def loaderFactory(self) -> ITemplateLoader:
        """
        @return: an L{XMLString} constructed with C{self.templateString}.
        """
        return XMLString(self.templateString)


class XMLFileWithFilePathTests(TestCase, XMLLoaderTestsMixin):
    """
    Tests for L{twisted.web.template.XMLFile}'s L{FilePath} support.
    """

    deprecatedUse = False

    def loaderFactory(self) -> ITemplateLoader:
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

    def loaderFactory(self) -> ITemplateLoader:
        """
        @return: an L{XMLString} constructed with a file object that contains
            C{self.templateString}.
        """
        return XMLFile(StringIO(self.templateString))  # type: ignore[arg-type]


class XMLFileWithFilenameTests(TestCase, XMLLoaderTestsMixin):
    """
    Tests for L{twisted.web.template.XMLFile}'s deprecated filename support.
    """

    deprecatedUse = True

    def loaderFactory(self) -> ITemplateLoader:
        """
        @return: an L{XMLString} constructed with a filename that points to a
            file containing C{self.templateString}.
        """
        fp = FilePath(self.mktemp())
        fp.setContent(self.templateString.encode("utf8"))
        return XMLFile(fp.path)  # type: ignore[arg-type]


class FlattenIntegrationTests(FlattenTestCase):
    """
    Tests for integration between L{Element} and
    L{twisted.web._flatten.flatten}.
    """

    def test_roundTrip(self) -> None:
        """
        Given a series of parsable XML strings, verify that
        L{twisted.web._flatten.flatten} will flatten the L{Element} back to the
        input when sent on a round trip.
        """
        fragments = [
            b"<p>Hello, world.</p>",
            b"<p><!-- hello, world --></p>",
            b"<p><![CDATA[Hello, world.]]></p>",
            b'<test1 xmlns:test2="urn:test2">' b"<test2:test3></test2:test3></test1>",
            b'<test1 xmlns="urn:test2"><test3></test3></test1>',
            b"<p>\xe2\x98\x83</p>",
        ]
        for xml in fragments:
            self.assertFlattensImmediately(Element(loader=XMLString(xml)), xml)

    def test_entityConversion(self) -> None:
        """
        When flattening an HTML entity, it should flatten out to the utf-8
        representation if possible.
        """
        element = Element(loader=XMLString("<p>&#9731;</p>"))
        self.assertFlattensImmediately(element, b"<p>\xe2\x98\x83</p>")

    def test_missingTemplateLoader(self) -> None:
        """
        Rendering an Element without a loader attribute raises the appropriate
        exception.
        """
        self.assertFlatteningRaises(Element(), MissingTemplateLoader)

    def test_missingRenderMethod(self) -> None:
        """
        Flattening an L{Element} with a C{loader} which has a tag with a render
        directive fails with L{FlattenerError} if there is no available render
        method to satisfy that directive.
        """
        element = Element(
            loader=XMLString(
                """
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="unknownMethod" />
        """
            )
        )
        self.assertFlatteningRaises(element, MissingRenderMethod)

    def test_transparentRendering(self) -> None:
        """
        A C{transparent} element should be eliminated from the DOM and rendered as
        only its children.
        """
        element = Element(
            loader=XMLString(
                "<t:transparent "
                'xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
                "Hello, world."
                "</t:transparent>"
            )
        )
        self.assertFlattensImmediately(element, b"Hello, world.")

    def test_attrRendering(self) -> None:
        """
        An Element with an attr tag renders the vaule of its attr tag as an
        attribute of its containing tag.
        """
        element = Element(
            loader=XMLString(
                '<a xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
                '<t:attr name="href">http://example.com</t:attr>'
                "Hello, world."
                "</a>"
            )
        )
        self.assertFlattensImmediately(
            element, b'<a href="http://example.com">Hello, world.</a>'
        )

    def test_synchronousDeferredRecursion(self) -> None:
        """
        When rendering a large number of already-fired Deferreds we should not
        encounter any recursion errors or stack-depth issues.
        """
        self.assertFlattensImmediately([succeed("x") for i in range(250)], b"x" * 250)

    def test_errorToplevelAttr(self) -> None:
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
            """,
        )

    def test_errorUnnamedAttr(self) -> None:
        """
        A template with an C{attr} tag with no C{name} attribute will not load;
        it will raise L{AssertionError} if you try.
        """
        self.assertRaises(
            AssertionError,
            XMLString,
            """<html><t:attr
            xmlns:t='http://twistedmatrix.com/ns/twisted.web.template/0.1'
            >hello</t:attr></html>""",
        )

    def test_lenientPrefixBehavior(self) -> None:
        """
        If the parser sees a prefix it doesn't recognize on an attribute, it
        will pass it on through to serialization.
        """
        theInput = (
            '<hello:world hello:sample="testing" '
            'xmlns:hello="http://made-up.example.com/ns/not-real">'
            "This is a made-up tag.</hello:world>"
        )
        element = Element(loader=XMLString(theInput))
        self.assertFlattensTo(element, theInput.encode("utf8"))

    def test_deferredRendering(self) -> None:
        """
        An Element with a render method which returns a Deferred will render
        correctly.
        """

        class RenderfulElement(Element):
            @renderer
            def renderMethod(
                self, request: Optional[IRequest], tag: Tag
            ) -> Flattenable:
                return succeed("Hello, world.")

        element = RenderfulElement(
            loader=XMLString(
                """
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod">
            Goodbye, world.
        </p>
        """
            )
        )
        self.assertFlattensImmediately(element, b"Hello, world.")

    def test_loaderClassAttribute(self) -> None:
        """
        If there is a non-None loader attribute on the class of an Element
        instance but none on the instance itself, the class attribute is used.
        """

        class SubElement(Element):
            loader = XMLString("<p>Hello, world.</p>")

        self.assertFlattensImmediately(SubElement(), b"<p>Hello, world.</p>")

    def test_directiveRendering(self) -> None:
        """
        An Element with a valid render directive has that directive invoked and
        the result added to the output.
        """
        renders = []

        class RenderfulElement(Element):
            @renderer
            def renderMethod(
                self, request: Optional[IRequest], tag: Tag
            ) -> Flattenable:
                renders.append((self, request))
                return tag("Hello, world.")

        element = RenderfulElement(
            loader=XMLString(
                """
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod" />
        """
            )
        )
        self.assertFlattensImmediately(element, b"<p>Hello, world.</p>")

    def test_directiveRenderingOmittingTag(self) -> None:
        """
        An Element with a render method which omits the containing tag
        successfully removes that tag from the output.
        """

        class RenderfulElement(Element):
            @renderer
            def renderMethod(
                self, request: Optional[IRequest], tag: Tag
            ) -> Flattenable:
                return "Hello, world."

        element = RenderfulElement(
            loader=XMLString(
                """
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod">
            Goodbye, world.
        </p>
        """
            )
        )
        self.assertFlattensImmediately(element, b"Hello, world.")

    def test_elementContainingStaticElement(self) -> None:
        """
        An Element which is returned by the render method of another Element is
        rendered properly.
        """

        class RenderfulElement(Element):
            @renderer
            def renderMethod(
                self, request: Optional[IRequest], tag: Tag
            ) -> Flattenable:
                return tag(Element(loader=XMLString("<em>Hello, world.</em>")))

        element = RenderfulElement(
            loader=XMLString(
                """
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="renderMethod" />
        """
            )
        )
        self.assertFlattensImmediately(element, b"<p><em>Hello, world.</em></p>")

    def test_elementUsingSlots(self) -> None:
        """
        An Element which is returned by the render method of another Element is
        rendered properly.
        """

        class RenderfulElement(Element):
            @renderer
            def renderMethod(
                self, request: Optional[IRequest], tag: Tag
            ) -> Flattenable:
                return tag.fillSlots(test2="world.")

        element = RenderfulElement(
            loader=XMLString(
                '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"'
                ' t:render="renderMethod">'
                '<t:slot name="test1" default="Hello, " />'
                '<t:slot name="test2" />'
                "</p>"
            )
        )
        self.assertFlattensImmediately(element, b"<p>Hello, world.</p>")

    def test_elementContainingDynamicElement(self) -> None:
        """
        Directives in the document factory of an Element returned from a render
        method of another Element are satisfied from the correct object: the
        "inner" Element.
        """

        class OuterElement(Element):
            @renderer
            def outerMethod(self, request: Optional[IRequest], tag: Tag) -> Flattenable:
                return tag(
                    InnerElement(
                        loader=XMLString(
                            """
                <t:ignored
                  xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
                  t:render="innerMethod" />
                """
                        )
                    )
                )

        class InnerElement(Element):
            @renderer
            def innerMethod(self, request: Optional[IRequest], tag: Tag) -> Flattenable:
                return "Hello, world."

        element = OuterElement(
            loader=XMLString(
                """
        <p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="outerMethod" />
        """
            )
        )
        self.assertFlattensImmediately(element, b"<p>Hello, world.</p>")

    def test_sameLoaderTwice(self) -> None:
        """
        Rendering the output of a loader, or even the same element, should
        return different output each time.
        """
        sharedLoader = XMLString(
            '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
            '<t:transparent t:render="classCounter" /> '
            '<t:transparent t:render="instanceCounter" />'
            "</p>"
        )

        class DestructiveElement(Element):
            count = 0
            instanceCount = 0
            loader = sharedLoader

            @renderer
            def classCounter(
                self, request: Optional[IRequest], tag: Tag
            ) -> Flattenable:
                DestructiveElement.count += 1
                return tag(str(DestructiveElement.count))

            @renderer
            def instanceCounter(
                self, request: Optional[IRequest], tag: Tag
            ) -> Flattenable:
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

    def setUp(self) -> None:
        self.loader = TagLoader(tags.i("test"))

    def test_interface(self) -> None:
        """
        An instance of L{TagLoader} provides L{ITemplateLoader}.
        """
        self.assertTrue(verifyObject(ITemplateLoader, self.loader))

    def test_loadsList(self) -> None:
        """
        L{TagLoader.load} returns a list, per L{ITemplateLoader}.
        """
        self.assertIsInstance(self.loader.load(), list)

    def test_flatten(self) -> None:
        """
        L{TagLoader} can be used in an L{Element}, and flattens as the tag used
        to construct the L{TagLoader} would flatten.
        """
        e = Element(self.loader)
        self.assertFlattensImmediately(e, b"<i>test</i>")


class TestElement(Element):
    """
    An L{Element} that can be rendered successfully.
    """

    loader = XMLString(
        '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
        "Hello, world."
        "</p>"
    )


class TestFailureElement(Element):
    """
    An L{Element} that can be used in place of L{FailureElement} to verify
    that L{renderElement} can render failures properly.
    """

    loader = XMLString(
        '<p xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">'
        "I failed."
        "</p>"
    )

    def __init__(self, failure: Failure, loader: object = None):
        self.failure = failure


class FailingElement(Element):
    """
    An element that raises an exception when rendered.
    """

    def render(self, request: Optional[IRequest]) -> "Flattenable":
        a = 42
        b = 0
        return f"{a // b}"


class FakeSite:
    """
    A minimal L{Site} object that we can use to test displayTracebacks
    """

    displayTracebacks = False


@implementer(IRequest)
class DummyRenderRequest(DummyRequest):  # type: ignore[misc]
    """
    A dummy request object that has a C{site} attribute.

    This does not implement the full IRequest interface, but enough of it
    for this test suite.
    """

    def __init__(self) -> None:
        super().__init__([b""])
        self.site = FakeSite()


class RenderElementTests(TestCase):
    """
    Test L{renderElement}
    """

    def setUp(self) -> None:
        """
        Set up a common L{DummyRenderRequest}.
        """
        self.request = DummyRenderRequest()

    def test_simpleRender(self) -> Deferred[None]:
        """
        L{renderElement} returns NOT_DONE_YET and eventually
        writes the rendered L{Element} to the request before finishing the
        request.
        """
        element = TestElement()

        d = self.request.notifyFinish()

        def check(_: object) -> None:
            self.assertEqual(
                b"".join(self.request.written),
                b"<!DOCTYPE html>\n" b"<p>Hello, world.</p>",
            )
            self.assertTrue(self.request.finished)

        d.addCallback(check)

        self.assertIdentical(NOT_DONE_YET, renderElement(self.request, element))

        return d

    def test_simpleFailure(self) -> Deferred[None]:
        """
        L{renderElement} handles failures by writing a minimal
        error message to the request and finishing it.
        """
        element = FailingElement()

        d = self.request.notifyFinish()

        def check(_: object) -> None:
            flushed = self.flushLoggedErrors(FlattenerError)
            self.assertEqual(len(flushed), 1)
            self.assertEqual(
                b"".join(self.request.written),
                (
                    b"<!DOCTYPE html>\n"
                    b'<div style="font-size:800%;'
                    b"background-color:#FFF;"
                    b"color:#F00"
                    b'">An error occurred while rendering the response.</div>'
                ),
            )
            self.assertTrue(self.request.finished)

        d.addCallback(check)

        self.assertIdentical(NOT_DONE_YET, renderElement(self.request, element))

        return d

    def test_simpleFailureWithTraceback(self) -> Deferred[None]:
        """
        L{renderElement} will render a traceback when rendering of
        the element fails and our site is configured to display tracebacks.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)
        self.request.site.displayTracebacks = True

        element = FailingElement()

        d = self.request.notifyFinish()

        def check(_: object) -> None:
            self.assertEquals(1, len(logObserver))
            f = logObserver[0]["log_failure"]
            self.assertIsInstance(f.value, FlattenerError)
            flushed = self.flushLoggedErrors(FlattenerError)
            self.assertEqual(len(flushed), 1)
            self.assertEqual(
                b"".join(self.request.written), b"<!DOCTYPE html>\n<p>I failed.</p>"
            )
            self.assertTrue(self.request.finished)

        d.addCallback(check)

        renderElement(self.request, element, _failElement=TestFailureElement)

        return d

    def test_nonDefaultDoctype(self) -> Deferred[None]:
        """
        L{renderElement} will write the doctype string specified by the
        doctype keyword argument.
        """
        element = TestElement()

        d = self.request.notifyFinish()

        def check(_: object) -> None:
            self.assertEqual(
                b"".join(self.request.written),
                (
                    b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
                    b' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n'
                    b"<p>Hello, world.</p>"
                ),
            )

        d.addCallback(check)

        renderElement(
            self.request,
            element,
            doctype=(
                b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"'
                b' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
            ),
        )

        return d

    def test_noneDoctype(self) -> Deferred[None]:
        """
        L{renderElement} will not write out a doctype if the doctype keyword
        argument is L{None}.
        """
        element = TestElement()

        d = self.request.notifyFinish()

        def check(_: object) -> None:
            self.assertEqual(b"".join(self.request.written), b"<p>Hello, world.</p>")

        d.addCallback(check)

        renderElement(self.request, element, doctype=None)

        return d
