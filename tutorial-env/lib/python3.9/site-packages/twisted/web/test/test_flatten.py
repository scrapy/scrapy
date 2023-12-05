# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the flattening portion of L{twisted.web.template}, implemented in
L{twisted.web._flatten}.
"""

import re
import sys
import traceback
from collections import OrderedDict
from textwrap import dedent
from types import FunctionType
from typing import Callable, Dict, List, NoReturn, Optional, Tuple, cast
from xml.etree.ElementTree import XML

from zope.interface import implementer

from hamcrest import assert_that, equal_to

from twisted.internet.defer import (
    CancelledError,
    Deferred,
    gatherResults,
    passthru,
    succeed,
)
from twisted.python.failure import Failure
from twisted.test.testutils import XMLAssertionMixin
from twisted.trial.unittest import SynchronousTestCase
from twisted.web._flatten import BUFFER_SIZE
from twisted.web.error import FlattenerError, UnfilledSlot, UnsupportedType
from twisted.web.iweb import IRenderable, IRequest, ITemplateLoader
from twisted.web.template import (
    CDATA,
    CharRef,
    Comment,
    Element,
    Flattenable,
    Tag,
    TagLoader,
    flatten,
    flattenString,
    renderer,
    slot,
    tags,
)
from twisted.web.test._util import FlattenTestCase


class SerializationTests(FlattenTestCase, XMLAssertionMixin):
    """
    Tests for flattening various things.
    """

    def test_nestedTags(self) -> None:
        """
        Test that nested tags flatten correctly.
        """
        self.assertFlattensImmediately(
            tags.html(tags.body("42"), hi="there"),
            b'<html hi="there"><body>42</body></html>',
        )

    def test_serializeString(self) -> None:
        """
        Test that strings will be flattened and escaped correctly.
        """
        self.assertFlattensImmediately("one", b"one"),
        self.assertFlattensImmediately("<abc&&>123", b"&lt;abc&amp;&amp;&gt;123"),

    def test_serializeSelfClosingTags(self) -> None:
        """
        The serialized form of a self-closing tag is C{'<tagName />'}.
        """
        self.assertFlattensImmediately(tags.img(), b"<img />")

    def test_serializeAttribute(self) -> None:
        """
        The serialized form of attribute I{a} with value I{b} is C{'a="b"'}.
        """
        self.assertFlattensImmediately(tags.img(src="foo"), b'<img src="foo" />')

    def test_serializedMultipleAttributes(self) -> None:
        """
        Multiple attributes are separated by a single space in their serialized
        form.
        """
        tag = tags.img()
        tag.attributes = OrderedDict([("src", "foo"), ("name", "bar")])
        self.assertFlattensImmediately(tag, b'<img src="foo" name="bar" />')

    def checkAttributeSanitization(
        self,
        wrapData: Callable[[str], Flattenable],
        wrapTag: Callable[[Tag], Flattenable],
    ) -> None:
        """
        Common implementation of L{test_serializedAttributeWithSanitization}
        and L{test_serializedDeferredAttributeWithSanitization},
        L{test_serializedAttributeWithTransparentTag}.

        @param wrapData: A 1-argument callable that wraps around the
            attribute's value so other tests can customize it.

        @param wrapTag: A 1-argument callable that wraps around the outer tag
            so other tests can customize it.
        """
        self.assertFlattensImmediately(
            wrapTag(tags.img(src=wrapData('<>&"'))),
            b'<img src="&lt;&gt;&amp;&quot;" />',
        )

    def test_serializedAttributeWithSanitization(self) -> None:
        """
        Attribute values containing C{"<"}, C{">"}, C{"&"}, or C{'"'} have
        C{"&lt;"}, C{"&gt;"}, C{"&amp;"}, or C{"&quot;"} substituted for those
        bytes in the serialized output.
        """
        self.checkAttributeSanitization(passthru, passthru)

    def test_serializedDeferredAttributeWithSanitization(self) -> None:
        """
        Like L{test_serializedAttributeWithSanitization}, but when the contents
        of the attribute are in a L{Deferred
        <twisted.internet.defer.Deferred>}.
        """
        self.checkAttributeSanitization(succeed, passthru)

    def test_serializedAttributeWithSlotWithSanitization(self) -> None:
        """
        Like L{test_serializedAttributeWithSanitization} but with a slot.
        """
        toss = []

        def insertSlot(value: str) -> Flattenable:
            toss.append(value)
            return slot("stuff")

        def fillSlot(tag: Tag) -> Tag:
            return tag.fillSlots(stuff=toss.pop())

        self.checkAttributeSanitization(insertSlot, fillSlot)

    def test_serializedAttributeWithTransparentTag(self) -> None:
        """
        Attribute values which are supplied via the value of a C{t:transparent}
        tag have the same substitution rules to them as values supplied
        directly.
        """
        self.checkAttributeSanitization(tags.transparent, passthru)

    def test_serializedAttributeWithTransparentTagWithRenderer(self) -> None:
        """
        Like L{test_serializedAttributeWithTransparentTag}, but when the
        attribute is rendered by a renderer on an element.
        """

        class WithRenderer(Element):
            def __init__(self, value: str, loader: Optional[ITemplateLoader]):
                self.value = value
                super().__init__(loader)

            @renderer
            def stuff(self, request: Optional[IRequest], tag: Tag) -> Flattenable:
                return self.value

        toss = []

        def insertRenderer(value: str) -> Flattenable:
            toss.append(value)
            return tags.transparent(render="stuff")

        def render(tag: Tag) -> Flattenable:
            return WithRenderer(toss.pop(), TagLoader(tag))

        self.checkAttributeSanitization(insertRenderer, render)

    def test_serializedAttributeWithRenderable(self) -> None:
        """
        Like L{test_serializedAttributeWithTransparentTag}, but when the
        attribute is a provider of L{IRenderable} rather than a transparent
        tag.
        """

        @implementer(IRenderable)
        class Arbitrary:
            def __init__(self, value: Flattenable):
                self.value = value

            def render(self, request: Optional[IRequest]) -> Flattenable:
                return self.value

            def lookupRenderMethod(
                self, name: str
            ) -> Callable[[Optional[IRequest], Tag], Flattenable]:
                raise NotImplementedError("Unexpected call")

        self.checkAttributeSanitization(Arbitrary, passthru)

    def checkTagAttributeSerialization(
        self, wrapTag: Callable[[Tag], Flattenable]
    ) -> None:
        """
        Common implementation of L{test_serializedAttributeWithTag} and
        L{test_serializedAttributeWithDeferredTag}.

        @param wrapTag: A 1-argument callable that wraps around the attribute's
            value so other tests can customize it.
        @type wrapTag: callable taking L{Tag} and returning something
            flattenable
        """
        innerTag = tags.a('<>&"')
        outerTag = tags.img(src=wrapTag(innerTag))
        outer = self.assertFlattensImmediately(
            outerTag,
            b'<img src="&lt;a&gt;&amp;lt;&amp;gt;&amp;amp;&quot;&lt;/a&gt;" />',
        )
        inner = self.assertFlattensImmediately(innerTag, b'<a>&lt;&gt;&amp;"</a>')

        # Since the above quoting is somewhat tricky, validate it by making sure
        # that the main use-case for tag-within-attribute is supported here: if
        # we serialize a tag, it is quoted *such that it can be parsed out again
        # as a tag*.
        self.assertXMLEqual(XML(outer).attrib["src"], inner)

    def test_serializedAttributeWithTag(self) -> None:
        """
        L{Tag} objects which are serialized within the context of an attribute
        are serialized such that the text content of the attribute may be
        parsed to retrieve the tag.
        """
        self.checkTagAttributeSerialization(passthru)

    def test_serializedAttributeWithDeferredTag(self) -> None:
        """
        Like L{test_serializedAttributeWithTag}, but when the L{Tag} is in a
        L{Deferred <twisted.internet.defer.Deferred>}.
        """
        self.checkTagAttributeSerialization(succeed)

    def test_serializedAttributeWithTagWithAttribute(self) -> None:
        """
        Similar to L{test_serializedAttributeWithTag}, but for the additional
        complexity where the tag which is the attribute value itself has an
        attribute value which contains bytes which require substitution.
        """
        flattened = self.assertFlattensImmediately(
            tags.img(src=tags.a(href='<>&"')),
            b'<img src="&lt;a href='
            b"&quot;&amp;lt;&amp;gt;&amp;amp;&amp;quot;&quot;&gt;"
            b'&lt;/a&gt;" />',
        )

        # As in checkTagAttributeSerialization, belt-and-suspenders:
        self.assertXMLEqual(
            XML(flattened).attrib["src"], b'<a href="&lt;&gt;&amp;&quot;"></a>'
        )

    def test_serializeComment(self) -> None:
        """
        Test that comments are correctly flattened and escaped.
        """
        self.assertFlattensImmediately(Comment("foo bar"), b"<!--foo bar-->")

    def test_commentEscaping(self) -> Deferred[List[bytes]]:
        """
        The data in a L{Comment} is escaped and mangled in the flattened output
        so that the result is a legal SGML and XML comment.

        SGML comment syntax is complicated and hard to use. This rule is more
        restrictive, and more compatible:

        Comments start with <!-- and end with --> and never contain -- or >.

        Also by XML syntax, a comment may not end with '-'.

        @see: U{http://www.w3.org/TR/REC-xml/#sec-comments}
        """

        def verifyComment(c: bytes) -> None:
            self.assertTrue(
                c.startswith(b"<!--"),
                f"{c!r} does not start with the comment prefix",
            )
            self.assertTrue(
                c.endswith(b"-->"),
                f"{c!r} does not end with the comment suffix",
            )
            # If it is shorter than 7, then the prefix and suffix overlap
            # illegally.
            self.assertTrue(len(c) >= 7, f"{c!r} is too short to be a legal comment")
            content = c[4:-3]
            self.assertNotIn(b"--", content)
            self.assertNotIn(b">", content)
            if content:
                self.assertNotEqual(content[-1], b"-")

        results = []
        for c in [
            "",
            "foo---bar",
            "foo---bar-",
            "foo>bar",
            "foo-->bar",
            "----------------",
        ]:
            d = flattenString(None, Comment(c))
            d.addCallback(verifyComment)
            results.append(d)
        return gatherResults(results)

    def test_serializeCDATA(self) -> None:
        """
        Test that CDATA is correctly flattened and escaped.
        """
        self.assertFlattensImmediately(CDATA("foo bar"), b"<![CDATA[foo bar]]>"),
        self.assertFlattensImmediately(
            CDATA("foo ]]> bar"), b"<![CDATA[foo ]]]]><![CDATA[> bar]]>"
        )

    def test_serializeUnicode(self) -> None:
        """
        Test that unicode is encoded correctly in the appropriate places, and
        raises an error when it occurs in inappropriate place.
        """
        snowman = "\N{SNOWMAN}"
        self.assertFlattensImmediately(snowman, b"\xe2\x98\x83")
        self.assertFlattensImmediately(tags.p(snowman), b"<p>\xe2\x98\x83</p>")
        self.assertFlattensImmediately(Comment(snowman), b"<!--\xe2\x98\x83-->")
        self.assertFlattensImmediately(CDATA(snowman), b"<![CDATA[\xe2\x98\x83]]>")
        self.assertFlatteningRaises(Tag(snowman), UnicodeEncodeError)
        self.assertFlatteningRaises(
            Tag("p", attributes={snowman: ""}), UnicodeEncodeError
        )

    def test_serializeCharRef(self) -> None:
        """
        A character reference is flattened to a string using the I{&#NNNN;}
        syntax.
        """
        ref = CharRef(ord("\N{SNOWMAN}"))
        self.assertFlattensImmediately(ref, b"&#9731;")

    def test_serializeDeferred(self) -> None:
        """
        Test that a deferred is substituted with the current value in the
        callback chain when flattened.
        """
        self.assertFlattensImmediately(succeed("two"), b"two")

    def test_serializeSameDeferredTwice(self) -> None:
        """
        Test that the same deferred can be flattened twice.
        """
        d = succeed("three")
        self.assertFlattensImmediately(d, b"three")
        self.assertFlattensImmediately(d, b"three")

    def test_serializeCoroutine(self) -> None:
        """
        Test that a coroutine returning a value is substituted with the that
        value when flattened.
        """
        from textwrap import dedent

        namespace: Dict[str, FunctionType] = {}
        exec(
            dedent(
                """
            async def coro(x):
                return x
            """
            ),
            namespace,
        )
        coro = namespace["coro"]

        self.assertFlattensImmediately(coro("four"), b"four")

    def test_serializeCoroutineWithAwait(self) -> None:
        """
        Test that a coroutine returning an awaited deferred value is
        substituted with that value when flattened.
        """
        from textwrap import dedent

        namespace = dict(succeed=succeed)
        exec(
            dedent(
                """
            async def coro(x):
                return await succeed(x)
            """
            ),
            namespace,
        )
        coro = namespace["coro"]

        self.assertFlattensImmediately(coro("four"), b"four")

    def test_serializeIRenderable(self) -> None:
        """
        Test that flattening respects all of the IRenderable interface.
        """

        @implementer(IRenderable)
        class FakeElement:
            def render(ign, ored: object) -> Tag:
                return tags.p(
                    "hello, ",
                    tags.transparent(render="test"),
                    " - ",
                    tags.transparent(render="test"),
                )

            def lookupRenderMethod(
                ign, name: str
            ) -> Callable[[Optional[IRequest], Tag], Flattenable]:
                self.assertEqual(name, "test")
                return lambda ign, node: node("world")

        self.assertFlattensImmediately(FakeElement(), b"<p>hello, world - world</p>")

    def test_serializeMissingRenderFactory(self) -> None:
        """
        Test that flattening a tag with a C{render} attribute when no render
        factory is available in the context raises an exception.
        """

        self.assertFlatteningRaises(tags.transparent(render="test"), ValueError)

    def test_serializeSlots(self) -> None:
        """
        Test that flattening a slot will use the slot value from the tag.
        """
        t1 = tags.p(slot("test"))
        t2 = t1.clone()
        t2.fillSlots(test="hello, world")
        self.assertFlatteningRaises(t1, UnfilledSlot)
        self.assertFlattensImmediately(t2, b"<p>hello, world</p>")

    def test_serializeDeferredSlots(self) -> None:
        """
        Test that a slot with a deferred as its value will be flattened using
        the value from the deferred.
        """
        t = tags.p(slot("test"))
        t.fillSlots(test=succeed(tags.em("four>")))
        self.assertFlattensImmediately(t, b"<p><em>four&gt;</em></p>")

    def test_unknownTypeRaises(self) -> None:
        """
        Test that flattening an unknown type of thing raises an exception.
        """
        self.assertFlatteningRaises(None, UnsupportedType)  # type: ignore[arg-type]


class FlattenChunkingTests(SynchronousTestCase):
    """
    Tests for the way pieces of the result are chunked together in calls to
    the write function.
    """

    def test_oneSmallChunk(self) -> None:
        """
        If the entire value to be flattened is available synchronously and fits
        into the buffer it is all passed to a single call to the write
        function.
        """
        output: List[bytes] = []
        self.successResultOf(flatten(None, ["1", "2", "3"], output.append))
        assert_that(output, equal_to([b"123"]))

    def test_someLargeChunks(self) -> None:
        """
        If the entire value to be flattened is available synchronously but does
        not fit into the buffer then it is chunked into buffer-sized pieces
        and these are passed to the write function.
        """
        some = ["x"] * BUFFER_SIZE
        someMore = ["y"] * BUFFER_SIZE
        evenMore = ["z"] * BUFFER_SIZE

        output: List[bytes] = []
        self.successResultOf(flatten(None, [some, someMore, evenMore], output.append))
        assert_that(
            output,
            equal_to([b"x" * BUFFER_SIZE, b"y" * BUFFER_SIZE, b"z" * BUFFER_SIZE]),
        )

    def _chunksSeparatedByAsyncTest(
        self,
        start: Callable[
            [Flattenable], Tuple[Deferred[Flattenable], Callable[[], object]]
        ],
    ) -> None:
        """
        Assert that flattening with a L{Deferred} returned by C{start} results
        in the expected buffering behavior.

        The L{Deferred} need not have a result by it is returned by C{start}
        but must have a result after the callable returned along with it is
        called.

        The expected buffering behavior is that flattened values up to the
        L{Deferred} are written together and then the result of the
        L{Deferred} is written together with values following it up to the
        next L{Deferred}.
        """
        first_wait, first_finish = start("first-")
        second_wait, second_finish = start("second-")
        value = [
            "already-available",
            "-chunks",
            first_wait,
            "chunks-already-",
            "computed",
            second_wait,
            "more-chunks-",
            "already-available",
        ]
        output: List[bytes] = []
        d = flatten(None, value, output.append)
        first_finish()
        second_finish()
        self.successResultOf(d)
        assert_that(
            output,
            equal_to(
                [
                    b"already-available-chunks",
                    b"first-chunks-already-computed",
                    b"second-more-chunks-already-available",
                ]
            ),
        )

    def test_chunksSeparatedByFiredDeferred(self) -> None:
        """
        When a fired L{Deferred} is encountered any buffered data is
        passed to the write function.  Then the L{Deferred}'s result is passed
        to another write along with following synchronous values.

        This exact buffering behavior should be considered an implementation
        detail and can be replaced by some other better behavior in the future
        if someone wants.
        """

        def sync_start(
            v: Flattenable,
        ) -> Tuple[Deferred[Flattenable], Callable[[], None]]:
            return (succeed(v), lambda: None)

        self._chunksSeparatedByAsyncTest(sync_start)

    def test_chunksSeparatedByUnfiredDeferred(self) -> None:
        """
        When an unfired L{Deferred} is encountered any buffered data is
        passed to the write function.  After the result of the L{Deferred} is
        available it is passed to another write along with following
        synchronous values.
        """

        def async_start(
            v: Flattenable,
        ) -> Tuple[Deferred[Flattenable], Callable[[], None]]:
            d: Deferred[Flattenable] = Deferred()
            return (d, lambda: d.callback(v))

        self._chunksSeparatedByAsyncTest(async_start)


# Use the co_filename mechanism (instead of the __file__ mechanism) because
# it is the mechanism traceback formatting uses.  The two do not necessarily
# agree with each other.  This requires a code object compiled in this file.
# The easiest way to get a code object is with a new function.  I'll use a
# lambda to avoid adding anything else to this namespace.  The result will
# be a string which agrees with the one the traceback module will put into a
# traceback for frames associated with functions defined in this file.

HERE = (lambda: None).__code__.co_filename


class FlattenerErrorTests(SynchronousTestCase):
    """
    Tests for L{FlattenerError}.
    """

    def test_renderable(self) -> None:
        """
        If a L{FlattenerError} is created with an L{IRenderable} provider root,
        the repr of that object is included in the string representation of the
        exception.
        """

        @implementer(IRenderable)
        class Renderable:  # type: ignore[misc]
            def __repr__(self) -> str:
                return "renderable repr"

        self.assertEqual(
            str(FlattenerError(RuntimeError("reason"), [Renderable()], [])),
            "Exception while flattening:\n"
            "  renderable repr\n"
            "RuntimeError: reason\n",
        )

    def test_tag(self) -> None:
        """
        If a L{FlattenerError} is created with a L{Tag} instance with source
        location information, the source location is included in the string
        representation of the exception.
        """
        tag = Tag("div", filename="/foo/filename.xhtml", lineNumber=17, columnNumber=12)

        self.assertEqual(
            str(FlattenerError(RuntimeError("reason"), [tag], [])),
            "Exception while flattening:\n"
            '  File "/foo/filename.xhtml", line 17, column 12, in "div"\n'
            "RuntimeError: reason\n",
        )

    def test_tagWithoutLocation(self) -> None:
        """
        If a L{FlattenerError} is created with a L{Tag} instance without source
        location information, only the tagName is included in the string
        representation of the exception.
        """
        self.assertEqual(
            str(FlattenerError(RuntimeError("reason"), [Tag("span")], [])),
            "Exception while flattening:\n" "  Tag <span>\n" "RuntimeError: reason\n",
        )

    def test_traceback(self) -> None:
        """
        If a L{FlattenerError} is created with traceback frames, they are
        included in the string representation of the exception.
        """
        # Try to be realistic in creating the data passed in for the traceback
        # frames.
        def f() -> None:
            g()

        def g() -> NoReturn:
            raise RuntimeError("reason")

        try:
            f()
        except RuntimeError as e:
            # Get the traceback, minus the info for *this* frame
            tbinfo = traceback.extract_tb(sys.exc_info()[2])[1:]
            exc = e
        else:
            self.fail("f() must raise RuntimeError")

        self.assertEqual(
            str(FlattenerError(exc, [], tbinfo)),
            "Exception while flattening:\n"
            '  File "%s", line %d, in f\n'
            "    g()\n"
            '  File "%s", line %d, in g\n'
            '    raise RuntimeError("reason")\n'
            "RuntimeError: reason\n"
            % (
                HERE,
                f.__code__.co_firstlineno + 1,
                HERE,
                g.__code__.co_firstlineno + 1,
            ),
        )

    def test_asynchronousFlattenError(self) -> None:
        """
        When flattening a renderer which raises an exception asynchronously,
        the error is reported when it occurs.
        """
        failing: Deferred[object] = Deferred()

        @implementer(IRenderable)
        class NotActuallyRenderable:
            "No methods provided; this will fail"

            def __repr__(self) -> str:
                return "<unrenderable>"

            def lookupRenderMethod(
                self, name: str
            ) -> Callable[[Optional[IRequest], Tag], Flattenable]:
                ...

            def render(self, request: Optional[IRequest]) -> Flattenable:
                return failing

        flattening = flattenString(None, [NotActuallyRenderable()])
        self.assertNoResult(flattening)
        exc = RuntimeError("example")
        failing.errback(exc)
        failure = self.failureResultOf(flattening, FlattenerError)
        self.assertRegex(
            str(failure.value),
            re.compile(
                dedent(
                    """\
                    Exception while flattening:
                      \\[<unrenderable>\\]
                      <unrenderable>
                      .*
                      File ".*", line \\d*, in _flattenTree
                        element = await element
                    RuntimeError: example
                    """
                ),
                flags=re.MULTILINE,
            ),
        )
        # The original exception is unmodified and will be logged separately if
        # unhandled.
        self.failureResultOf(failing, RuntimeError)

    def test_cancel(self) -> None:
        """
        The flattening of a Deferred can be cancelled.
        """
        cancelCount = 0
        cancelArg = None

        def checkCancel(cancelled: Deferred[object]) -> None:
            nonlocal cancelArg, cancelCount
            cancelArg = cancelled
            cancelCount += 1

        err = None

        def saveErr(failure: Failure) -> None:
            nonlocal err
            err = failure

        d: Deferred[object] = Deferred(checkCancel)
        flattening = flattenString(None, d)
        self.assertNoResult(flattening)
        d.addErrback(saveErr)

        flattening.cancel()

        # Check whether we got an orderly cancellation.
        # Do this first to get more meaningful reporting if something crashed.
        failure = self.failureResultOf(flattening, FlattenerError)

        self.assertEqual(cancelCount, 1)
        self.assertIs(cancelArg, d)

        self.assertIsInstance(err, Failure)
        self.assertIsInstance(cast(Failure, err).value, CancelledError)

        exc = failure.value.args[0]
        self.assertIsInstance(exc, CancelledError)
