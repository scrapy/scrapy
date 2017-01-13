# -*- test-case-name: twisted.python.test.test_textattributes -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module provides some common functionality for the manipulation of
formatting states.

Defining the mechanism by which text containing character attributes is
constructed begins by subclassing L{CharacterAttributesMixin}.

Defining how a single formatting state is to be serialized begins by
subclassing L{_FormattingStateMixin}.

Serializing a formatting structure is done with L{flatten}.

@see: L{twisted.conch.insults.helper._FormattingState}
@see: L{twisted.conch.insults.text._CharacterAttributes}
@see: L{twisted.words.protocols.irc._FormattingState}
@see: L{twisted.words.protocols.irc._CharacterAttributes}
"""

from __future__ import print_function

from twisted.python.util import FancyEqMixin



class _Attribute(FancyEqMixin, object):
    """
    A text attribute.

    Indexing a text attribute with a C{str} or another text attribute adds that
    object as a child, indexing with a C{list} or C{tuple} adds the elements as
    children; in either case C{self} is returned.

    @type children: C{list}
    @ivar children: Child attributes.
    """
    compareAttributes = ('children',)


    def __init__(self):
        self.children = []


    def __repr__(self):
        return '<%s %r>' % (type(self).__name__, vars(self))


    def __getitem__(self, item):
        assert isinstance(item, (list, tuple, _Attribute, str))
        if isinstance(item, (list, tuple)):
            self.children.extend(item)
        else:
            self.children.append(item)
        return self


    def serialize(self, write, attrs=None, attributeRenderer='toVT102'):
        """
        Serialize the text attribute and its children.

        @param write: C{callable}, taking one C{str} argument, called to output
            a single text attribute at a time.

        @param attrs: A formatting state instance used to determine how to
            serialize the attribute children.

        @type attributeRenderer: C{str}
        @param attributeRenderer: Name of the method on I{attrs} that should be
            called to render the attributes during serialization. Defaults to
            C{'toVT102'}.
        """
        if attrs is None:
            attrs = DefaultFormattingState()
        for ch in self.children:
            if isinstance(ch, _Attribute):
                ch.serialize(write, attrs.copy(), attributeRenderer)
            else:
                renderMeth = getattr(attrs, attributeRenderer)
                write(renderMeth())
                write(ch)



class _NormalAttr(_Attribute):
    """
    A text attribute for normal text.
    """
    def serialize(self, write, attrs, attributeRenderer):
        attrs.__init__()
        _Attribute.serialize(self, write, attrs, attributeRenderer)



class _OtherAttr(_Attribute):
    """
    A text attribute for text with formatting attributes.

    The unary minus operator returns the inverse of this attribute, where that
    makes sense.

    @type attrname: C{str}
    @ivar attrname: Text attribute name.

    @ivar attrvalue: Text attribute value.
    """
    compareAttributes = ('attrname', 'attrvalue', 'children')


    def __init__(self, attrname, attrvalue):
        _Attribute.__init__(self)
        self.attrname = attrname
        self.attrvalue = attrvalue


    def __neg__(self):
        result = _OtherAttr(self.attrname, not self.attrvalue)
        result.children.extend(self.children)
        return result


    def serialize(self, write, attrs, attributeRenderer):
        attrs = attrs._withAttribute(self.attrname, self.attrvalue)
        _Attribute.serialize(self, write, attrs, attributeRenderer)



class _ColorAttr(_Attribute):
    """
    Generic color attribute.

    @param color: Color value.

    @param ground: Foreground or background attribute name.
    """
    compareAttributes = ('color', 'ground', 'children')


    def __init__(self, color, ground):
        _Attribute.__init__(self)
        self.color = color
        self.ground = ground


    def serialize(self, write, attrs, attributeRenderer):
        attrs = attrs._withAttribute(self.ground, self.color)
        _Attribute.serialize(self, write, attrs, attributeRenderer)



class _ForegroundColorAttr(_ColorAttr):
    """
    Foreground color attribute.
    """
    def __init__(self, color):
        _ColorAttr.__init__(self, color, 'foreground')



class _BackgroundColorAttr(_ColorAttr):
    """
    Background color attribute.
    """
    def __init__(self, color):
        _ColorAttr.__init__(self, color, 'background')



class _ColorAttribute(object):
    """
    A color text attribute.

    Attribute access results in a color value lookup, by name, in
    I{_ColorAttribute.attrs}.

    @type ground: L{_ColorAttr}
    @param ground: Foreground or background color attribute to look color names
        up from.

    @param attrs: Mapping of color names to color values.
    @type attrs: Dict like object.
    """
    def __init__(self, ground, attrs):
        self.ground = ground
        self.attrs = attrs


    def __getattr__(self, name):
        try:
            return self.ground(self.attrs[name])
        except KeyError:
            raise AttributeError(name)



class CharacterAttributesMixin(object):
    """
    Mixin for character attributes that implements a C{__getattr__} method
    returning a new C{_NormalAttr} instance when attempting to access
    a C{'normal'} attribute; otherwise a new C{_OtherAttr} instance is returned
    for names that appears in the C{'attrs'} attribute.
    """
    def __getattr__(self, name):
        if name == 'normal':
            return _NormalAttr()
        if name in self.attrs:
            return _OtherAttr(name, True)
        raise AttributeError(name)



class DefaultFormattingState(FancyEqMixin, object):
    """
    A character attribute that does nothing, thus applying no attributes to
    text.
    """
    compareAttributes = ('_dummy',)

    _dummy = 0


    def copy(self):
        """
        Make a copy of this formatting state.

        @return: A formatting state instance.
        """
        return type(self)()


    def _withAttribute(self, name, value):
        """
        Add a character attribute to a copy of this formatting state.

        @param name: Attribute name to be added to formatting state.

        @param value: Attribute value.

        @return: A formatting state instance with the new attribute.
        """
        return self.copy()


    def toVT102(self):
        """
        Emit a VT102 control sequence that will set up all the attributes this
        formatting state has set.

        @return: A string containing VT102 control sequences that mimic this
            formatting state.
        """
        return ''



class _FormattingStateMixin(DefaultFormattingState):
    """
    Mixin for the formatting state/attributes of a single character.
    """
    def copy(self):
        c = DefaultFormattingState.copy(self)
        c.__dict__.update(vars(self))
        return c


    def _withAttribute(self, name, value):
        if getattr(self, name) != value:
            attr = self.copy()
            attr._subtracting = not value
            setattr(attr, name, value)
            return attr
        else:
            return self.copy()



def flatten(output, attrs, attributeRenderer='toVT102'):
    """
    Serialize a sequence of characters with attribute information

    The resulting string can be interpreted by compatible software so that the
    contained characters are displayed and, for those attributes which are
    supported by the software, the attributes expressed. The exact result of
    the serialization depends on the behavior of the method specified by
    I{attributeRenderer}.

    For example, if your terminal is VT102 compatible, you might run
    this for a colorful variation on the \"hello world\" theme::

        from twisted.conch.insults.text import flatten, attributes as A
        from twisted.conch.insults.helper import CharacterAttribute
        print(flatten(
            A.normal[A.bold[A.fg.red['He'], A.fg.green['ll'], A.fg.magenta['o'], ' ',
                            A.fg.yellow['Wo'], A.fg.blue['rl'], A.fg.cyan['d!']]],
            CharacterAttribute()))

    @param output: Object returned by accessing attributes of the
        module-level attributes object.

    @param attrs: A formatting state instance used to determine how to
        serialize C{output}.

    @type attributeRenderer: C{str}
    @param attributeRenderer: Name of the method on I{attrs} that should be
        called to render the attributes during serialization. Defaults to
        C{'toVT102'}.

    @return: A string expressing the text and display attributes specified by
        L{output}.
    """
    flattened = []
    output.serialize(flattened.append, attrs, attributeRenderer)
    return ''.join(flattened)



__all__ = [
    'flatten', 'DefaultFormattingState', 'CharacterAttributesMixin']
