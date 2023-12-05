# -*- test-case-name: twisted.conch.test.test_text -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Character attribute manipulation API.

This module provides a domain-specific language (using Python syntax)
for the creation of text with additional display attributes associated
with it.  It is intended as an alternative to manually building up
strings containing ECMA 48 character attribute control codes.  It
currently supports foreground and background colors (black, red,
green, yellow, blue, magenta, cyan, and white), intensity selection,
underlining, blinking and reverse video.  Character set selection
support is planned.

Character attributes are specified by using two Python operations:
attribute lookup and indexing.  For example, the string \"Hello
world\" with red foreground and all other attributes set to their
defaults, assuming the name twisted.conch.insults.text.attributes has
been imported and bound to the name \"A\" (with the statement C{from
twisted.conch.insults.text import attributes as A}, for example) one
uses this expression::

    A.fg.red[\"Hello world\"]

Other foreground colors are set by substituting their name for
\"red\".  To set both a foreground and a background color, this
expression is used::

    A.fg.red[A.bg.green[\"Hello world\"]]

Note that either A.bg.green can be nested within A.fg.red or vice
versa.  Also note that multiple items can be nested within a single
index operation by separating them with commas::

    A.bg.green[A.fg.red[\"Hello\"], " ", A.fg.blue[\"world\"]]

Other character attributes are set in a similar fashion.  To specify a
blinking version of the previous expression::

    A.blink[A.bg.green[A.fg.red[\"Hello\"], " ", A.fg.blue[\"world\"]]]

C{A.reverseVideo}, C{A.underline}, and C{A.bold} are also valid.

A third operation is actually supported: unary negation.  This turns
off an attribute when an enclosing expression would otherwise have
caused it to be on.  For example::

    A.underline[A.fg.red[\"Hello\", -A.underline[\" world\"]]]

A formatting structure can then be serialized into a string containing the
necessary VT102 control codes with L{assembleFormattedText}.

@see: L{twisted.conch.insults.text._CharacterAttributes}
@author: Jp Calderone
"""

from incremental import Version

from twisted.conch.insults import helper, insults
from twisted.python import _textattributes
from twisted.python.deprecate import deprecatedModuleAttribute

flatten = _textattributes.flatten

deprecatedModuleAttribute(
    Version("Twisted", 13, 1, 0),
    "Use twisted.conch.insults.text.assembleFormattedText instead.",
    "twisted.conch.insults.text",
    "flatten",
)

_TEXT_COLORS = {
    "black": helper.BLACK,
    "red": helper.RED,
    "green": helper.GREEN,
    "yellow": helper.YELLOW,
    "blue": helper.BLUE,
    "magenta": helper.MAGENTA,
    "cyan": helper.CYAN,
    "white": helper.WHITE,
}


class _CharacterAttributes(_textattributes.CharacterAttributesMixin):
    """
    Factory for character attributes, including foreground and background color
    and non-color attributes such as bold, reverse video and underline.

    Character attributes are applied to actual text by using object
    indexing-syntax (C{obj['abc']}) after accessing a factory attribute, for
    example::

        attributes.bold['Some text']

    These can be nested to mix attributes::

        attributes.bold[attributes.underline['Some text']]

    And multiple values can be passed::

        attributes.normal[attributes.bold['Some'], ' text']

    Non-color attributes can be accessed by attribute name, available
    attributes are:

        - bold
        - blink
        - reverseVideo
        - underline

    Available colors are:

        0. black
        1. red
        2. green
        3. yellow
        4. blue
        5. magenta
        6. cyan
        7. white

    @ivar fg: Foreground colors accessed by attribute name, see above
        for possible names.

    @ivar bg: Background colors accessed by attribute name, see above
        for possible names.
    """

    fg = _textattributes._ColorAttribute(
        _textattributes._ForegroundColorAttr, _TEXT_COLORS
    )
    bg = _textattributes._ColorAttribute(
        _textattributes._BackgroundColorAttr, _TEXT_COLORS
    )

    attrs = {
        "bold": insults.BOLD,
        "blink": insults.BLINK,
        "underline": insults.UNDERLINE,
        "reverseVideo": insults.REVERSE_VIDEO,
    }


def assembleFormattedText(formatted):
    """
    Assemble formatted text from structured information.

    Currently handled formatting includes: bold, blink, reverse, underline and
    color codes.

    For example::

        from twisted.conch.insults.text import attributes as A
        assembleFormattedText(
            A.normal[A.bold['Time: '], A.fg.lightRed['Now!']])

    Would produce "Time: " in bold formatting, followed by "Now!" with a
    foreground color of light red and without any additional formatting.

    @param formatted: Structured text and attributes.

    @rtype: L{str}
    @return: String containing VT102 control sequences that mimic those
        specified by C{formatted}.

    @see: L{twisted.conch.insults.text._CharacterAttributes}
    @since: 13.1
    """
    return _textattributes.flatten(formatted, helper._FormattingState(), "toVT102")


attributes = _CharacterAttributes()

__all__ = ["attributes", "flatten"]
