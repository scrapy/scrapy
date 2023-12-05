# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web._stan} portion of the L{twisted.web.template}
implementation.
"""


import sys
from typing import NoReturn

from twisted.trial.unittest import TestCase
from twisted.web.template import CDATA, CharRef, Comment, Flattenable, Tag


def proto(*a: Flattenable, **kw: Flattenable) -> Tag:
    """
    Produce a new tag for testing.
    """
    return Tag("hello")(*a, **kw)


class TagTests(TestCase):
    """
    Tests for L{Tag}.
    """

    def test_renderAttribute(self) -> None:
        """
        Setting an attribute named C{render} will change the C{render} instance
        variable instead of adding an attribute.
        """
        tag = proto(render="myRenderer")
        self.assertEqual(tag.render, "myRenderer")
        self.assertEqual(tag.attributes, {})

    def test_renderAttributeNonString(self) -> None:
        """
        Attempting to set an attribute named C{render} to something other than
        a string will raise L{TypeError}.
        """
        with self.assertRaises(TypeError) as e:
            proto(render=83)  # type: ignore[arg-type]
        self.assertEqual(
            e.exception.args[0], 'Value for "render" attribute must be str, got 83'
        )

    def test_fillSlots(self) -> None:
        """
        L{Tag.fillSlots} returns self.
        """
        tag = proto()
        self.assertIdentical(tag, tag.fillSlots(test="test"))

    def test_cloneShallow(self) -> None:
        """
        L{Tag.clone} copies all attributes and children of a tag, including its
        render attribute.  If the shallow flag is C{False}, that's where it
        stops.
        """
        innerList = ["inner list"]
        tag = proto("How are you", innerList, hello="world", render="aSampleMethod")
        tag.fillSlots(foo="bar")
        tag.filename = "foo/bar"
        tag.lineNumber = 6
        tag.columnNumber = 12
        clone = tag.clone(deep=False)
        self.assertEqual(clone.attributes["hello"], "world")
        self.assertNotIdentical(clone.attributes, tag.attributes)
        self.assertEqual(clone.children, ["How are you", innerList])
        self.assertNotIdentical(clone.children, tag.children)
        self.assertIdentical(clone.children[1], innerList)
        self.assertEqual(tag.slotData, clone.slotData)
        self.assertNotIdentical(tag.slotData, clone.slotData)
        self.assertEqual(clone.filename, "foo/bar")
        self.assertEqual(clone.lineNumber, 6)
        self.assertEqual(clone.columnNumber, 12)
        self.assertEqual(clone.render, "aSampleMethod")

    def test_cloneDeep(self) -> None:
        """
        L{Tag.clone} copies all attributes and children of a tag, including its
        render attribute.  In its normal operating mode (where the deep flag is
        C{True}, as is the default), it will clone all sub-lists and sub-tags.
        """
        innerTag = proto("inner")
        innerList = ["inner list"]
        tag = proto(
            "How are you", innerTag, innerList, hello="world", render="aSampleMethod"
        )
        tag.fillSlots(foo="bar")
        tag.filename = "foo/bar"
        tag.lineNumber = 6
        tag.columnNumber = 12
        clone = tag.clone()
        self.assertEqual(clone.attributes["hello"], "world")
        self.assertNotIdentical(clone.attributes, tag.attributes)
        self.assertNotIdentical(clone.children, tag.children)
        # sanity check
        self.assertIdentical(tag.children[1], innerTag)
        # clone should have sub-clone
        self.assertNotIdentical(clone.children[1], innerTag)
        # sanity check
        self.assertIdentical(tag.children[2], innerList)
        # clone should have sub-clone
        self.assertNotIdentical(clone.children[2], innerList)
        self.assertEqual(tag.slotData, clone.slotData)
        self.assertNotIdentical(tag.slotData, clone.slotData)
        self.assertEqual(clone.filename, "foo/bar")
        self.assertEqual(clone.lineNumber, 6)
        self.assertEqual(clone.columnNumber, 12)
        self.assertEqual(clone.render, "aSampleMethod")

    def test_cloneGeneratorDeprecation(self) -> None:
        """
        Cloning a tag containing a generator is unsafe. To avoid breaking
        programs that only flatten the clone or only flatten the original,
        we deprecate old behavior rather than making it an error immediately.
        """
        tag = proto(str(n) for n in range(10))
        self.assertWarns(
            DeprecationWarning,
            "Cloning a Tag which contains a generator is unsafe, "
            "since the generator can be consumed only once; "
            "this is deprecated since Twisted 21.7.0 and will raise "
            "an exception in the future",
            sys.modules[Tag.__module__].__file__,
            tag.clone,
        )

    def test_cloneCoroutineDeprecation(self) -> None:
        """
        Cloning a tag containing a coroutine is unsafe. To avoid breaking
        programs that only flatten the clone or only flatten the original,
        we deprecate old behavior rather than making it an error immediately.
        """

        async def asyncFunc() -> NoReturn:
            raise NotImplementedError

        coro = asyncFunc()
        tag = proto("123", coro, "789")
        try:
            self.assertWarns(
                DeprecationWarning,
                "Cloning a Tag which contains a coroutine is unsafe, "
                "since the coroutine can run only once; "
                "this is deprecated since Twisted 21.7.0 and will raise "
                "an exception in the future",
                sys.modules[Tag.__module__].__file__,
                tag.clone,
            )
        finally:
            coro.close()

    def test_clear(self) -> None:
        """
        L{Tag.clear} removes all children from a tag, but leaves its attributes
        in place.
        """
        tag = proto("these are", "children", "cool", andSoIs="this-attribute")
        tag.clear()
        self.assertEqual(tag.children, [])
        self.assertEqual(tag.attributes, {"andSoIs": "this-attribute"})

    def test_suffix(self) -> None:
        """
        L{Tag.__call__} accepts Python keywords with a suffixed underscore as
        the DOM attribute of that literal suffix.
        """
        proto = Tag("div")
        tag = proto()
        tag(class_="a")
        self.assertEqual(tag.attributes, {"class": "a"})

    def test_commentReprPy3(self) -> None:
        """
        L{Comment.__repr__} returns a value which makes it easy to see what's
        in the comment.
        """
        self.assertEqual(repr(Comment("hello there")), "Comment('hello there')")

    def test_cdataReprPy3(self) -> None:
        """
        L{CDATA.__repr__} returns a value which makes it easy to see what's in
        the comment.
        """
        self.assertEqual(repr(CDATA("test data")), "CDATA('test data')")

    def test_charrefRepr(self) -> None:
        """
        L{CharRef.__repr__} returns a value which makes it easy to see what
        character is referred to.
        """
        snowman = ord("\N{SNOWMAN}")
        self.assertEqual(repr(CharRef(snowman)), "CharRef(9731)")
