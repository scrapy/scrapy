# -*- test-case-name: twisted.web.test.test_stan -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An s-expression-like syntax for expressing xml in pure python.

Stan tags allow you to build XML documents using Python.

Stan is a DOM, or Document Object Model, implemented using basic Python types
and functions called "flatteners". A flattener is a function that knows how to
turn an object of a specific type into something that is closer to an HTML
string. Stan differs from the W3C DOM by not being as cumbersome and heavy
weight. Since the object model is built using simple python types such as lists,
strings, and dictionaries, the API is simpler and constructing a DOM less
cumbersome.

@var voidElements: the names of HTML 'U{void
    elements<http://www.whatwg.org/specs/web-apps/current-work/multipage/syntax.html#void-elements>}';
    those which can't have contents and can therefore be self-closing in the
    output.
"""


from inspect import iscoroutine, isgenerator
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from warnings import warn

import attr

if TYPE_CHECKING:
    from twisted.web.template import Flattenable


@attr.s(hash=False, eq=False, auto_attribs=True)
class slot:
    """
    Marker for markup insertion in a template.
    """

    name: str
    """
    The name of this slot.

    The key which must be used in L{Tag.fillSlots} to fill it.
    """

    children: List["Tag"] = attr.ib(init=False, factory=list)
    """
    The L{Tag} objects included in this L{slot}'s template.
    """

    default: Optional["Flattenable"] = None
    """
    The default contents of this slot, if it is left unfilled.

    If this is L{None}, an L{UnfilledSlot} will be raised, rather than
    L{None} actually being used.
    """

    filename: Optional[str] = None
    """
    The name of the XML file from which this tag was parsed.

    If it was not parsed from an XML file, L{None}.
    """

    lineNumber: Optional[int] = None
    """
    The line number on which this tag was encountered in the XML file
    from which it was parsed.

    If it was not parsed from an XML file, L{None}.
    """

    columnNumber: Optional[int] = None
    """
    The column number at which this tag was encountered in the XML file
    from which it was parsed.

    If it was not parsed from an XML file, L{None}.
    """


@attr.s(hash=False, eq=False, repr=False, auto_attribs=True)
class Tag:
    """
    A L{Tag} represents an XML tags with a tag name, attributes, and children.
    A L{Tag} can be constructed using the special L{twisted.web.template.tags}
    object, or it may be constructed directly with a tag name. L{Tag}s have a
    special method, C{__call__}, which makes representing trees of XML natural
    using pure python syntax.
    """

    tagName: Union[bytes, str]
    """
    The name of the represented element.

    For a tag like C{<div></div>}, this would be C{"div"}.
    """

    attributes: Dict[Union[bytes, str], "Flattenable"] = attr.ib(factory=dict)
    """The attributes of the element."""

    children: List["Flattenable"] = attr.ib(factory=list)
    """The contents of this C{Tag}."""

    render: Optional[str] = None
    """
    The name of the render method to use for this L{Tag}.

    This name will be looked up at render time by the
    L{twisted.web.template.Element} doing the rendering,
    via L{twisted.web.template.Element.lookupRenderMethod},
    to determine which method to call.
    """

    filename: Optional[str] = None
    """
    The name of the XML file from which this tag was parsed.

    If it was not parsed from an XML file, L{None}.
    """

    lineNumber: Optional[int] = None
    """
    The line number on which this tag was encountered in the XML file
    from which it was parsed.

    If it was not parsed from an XML file, L{None}.
    """

    columnNumber: Optional[int] = None
    """
    The column number at which this tag was encountered in the XML file
    from which it was parsed.

    If it was not parsed from an XML file, L{None}.
    """

    slotData: Optional[Dict[str, "Flattenable"]] = attr.ib(init=False, default=None)
    """
    The data which can fill slots.

    If present, a dictionary mapping slot names to renderable values.
    The values in this dict might be anything that can be present as
    the child of a L{Tag}: strings, lists, L{Tag}s, generators, etc.
    """

    def fillSlots(self, **slots: "Flattenable") -> "Tag":
        """
        Remember the slots provided at this position in the DOM.

        During the rendering of children of this node, slots with names in
        C{slots} will be rendered as their corresponding values.

        @return: C{self}. This enables the idiom C{return tag.fillSlots(...)} in
            renderers.
        """
        if self.slotData is None:
            self.slotData = {}
        self.slotData.update(slots)
        return self

    def __call__(self, *children: "Flattenable", **kw: "Flattenable") -> "Tag":
        """
        Add children and change attributes on this tag.

        This is implemented using __call__ because it then allows the natural
        syntax::

          table(tr1, tr2, width="100%", height="50%", border="1")

        Children may be other tag instances, strings, functions, or any other
        object which has a registered flatten.

        Attributes may be 'transparent' tag instances (so that
        C{a(href=transparent(data="foo", render=myhrefrenderer))} works),
        strings, functions, or any other object which has a registered
        flattener.

        If the attribute is a python keyword, such as 'class', you can add an
        underscore to the name, like 'class_'.

        There is one special keyword argument, 'render', which will be used as
        the name of the renderer and saved as the 'render' attribute of this
        instance, rather than the DOM 'render' attribute in the attributes
        dictionary.
        """
        self.children.extend(children)

        for k, v in kw.items():
            if k[-1] == "_":
                k = k[:-1]

            if k == "render":
                if not isinstance(v, str):
                    raise TypeError(
                        f'Value for "render" attribute must be str, got {v!r}'
                    )
                self.render = v
            else:
                self.attributes[k] = v
        return self

    def _clone(self, obj: "Flattenable", deep: bool) -> "Flattenable":
        """
        Clone a C{Flattenable} object; used by L{Tag.clone}.

        Note that both lists and tuples are cloned into lists.

        @param obj: an object with a clone method, a list or tuple, or something
            which should be immutable.

        @param deep: whether to continue cloning child objects; i.e. the
            contents of lists, the sub-tags within a tag.

        @return: a clone of C{obj}.
        """
        if hasattr(obj, "clone"):
            return obj.clone(deep)  # type: ignore[union-attr]
        elif isinstance(obj, (list, tuple)):
            return [self._clone(x, deep) for x in obj]
        elif isgenerator(obj):
            warn(
                "Cloning a Tag which contains a generator is unsafe, "
                "since the generator can be consumed only once; "
                "this is deprecated since Twisted 21.7.0 and will raise "
                "an exception in the future",
                DeprecationWarning,
            )
            return obj
        elif iscoroutine(obj):
            warn(
                "Cloning a Tag which contains a coroutine is unsafe, "
                "since the coroutine can run only once; "
                "this is deprecated since Twisted 21.7.0 and will raise "
                "an exception in the future",
                DeprecationWarning,
            )
            return obj
        else:
            return obj

    def clone(self, deep: bool = True) -> "Tag":
        """
        Return a clone of this tag. If deep is True, clone all of this tag's
        children. Otherwise, just shallow copy the children list without copying
        the children themselves.
        """
        if deep:
            newchildren = [self._clone(x, True) for x in self.children]
        else:
            newchildren = self.children[:]
        newattrs = self.attributes.copy()
        for key in newattrs.keys():
            newattrs[key] = self._clone(newattrs[key], True)

        newslotdata = None
        if self.slotData:
            newslotdata = self.slotData.copy()
            for key in newslotdata:
                newslotdata[key] = self._clone(newslotdata[key], True)

        newtag = Tag(
            self.tagName,
            attributes=newattrs,
            children=newchildren,
            render=self.render,
            filename=self.filename,
            lineNumber=self.lineNumber,
            columnNumber=self.columnNumber,
        )
        newtag.slotData = newslotdata

        return newtag

    def clear(self) -> "Tag":
        """
        Clear any existing children from this tag.
        """
        self.children = []
        return self

    def __repr__(self) -> str:
        rstr = ""
        if self.attributes:
            rstr += ", attributes=%r" % self.attributes
        if self.children:
            rstr += ", children=%r" % self.children
        return f"Tag({self.tagName!r}{rstr})"


voidElements = (
    "img",
    "br",
    "hr",
    "base",
    "meta",
    "link",
    "param",
    "area",
    "input",
    "col",
    "basefont",
    "isindex",
    "frame",
    "command",
    "embed",
    "keygen",
    "source",
    "track",
    "wbs",
)


@attr.s(hash=False, eq=False, repr=False, auto_attribs=True)
class CDATA:
    """
    A C{<![CDATA[]]>} block from a template.  Given a separate representation in
    the DOM so that they may be round-tripped through rendering without losing
    information.
    """

    data: str
    """The data between "C{<![CDATA[}" and "C{]]>}"."""

    def __repr__(self) -> str:
        return f"CDATA({self.data!r})"


@attr.s(hash=False, eq=False, repr=False, auto_attribs=True)
class Comment:
    """
    A C{<!-- -->} comment from a template.  Given a separate representation in
    the DOM so that they may be round-tripped through rendering without losing
    information.
    """

    data: str
    """The data between "C{<!--}" and "C{-->}"."""

    def __repr__(self) -> str:
        return f"Comment({self.data!r})"


@attr.s(hash=False, eq=False, repr=False, auto_attribs=True)
class CharRef:
    """
    A numeric character reference.  Given a separate representation in the DOM
    so that non-ASCII characters may be output as pure ASCII.

    @since: 12.0
    """

    ordinal: int
    """The ordinal value of the unicode character to which this object refers."""

    def __repr__(self) -> str:
        return "CharRef(%d)" % (self.ordinal,)
