# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#
"""Module to parse ANSI escape sequences

Maintainer: Jean-Paul Calderone
"""

import string

# Twisted imports
from twisted.logger import Logger

_log = Logger()


class ColorText:
    """
    Represents an element of text along with the texts colors and
    additional attributes.
    """

    # The colors to use
    COLORS = ("b", "r", "g", "y", "l", "m", "c", "w")
    BOLD_COLORS = tuple(x.upper() for x in COLORS)
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(len(COLORS))

    # Color names
    COLOR_NAMES = (
        "Black",
        "Red",
        "Green",
        "Yellow",
        "Blue",
        "Magenta",
        "Cyan",
        "White",
    )

    def __init__(self, text, fg, bg, display, bold, underline, flash, reverse):
        self.text, self.fg, self.bg = text, fg, bg
        self.display = display
        self.bold = bold
        self.underline = underline
        self.flash = flash
        self.reverse = reverse
        if self.reverse:
            self.fg, self.bg = self.bg, self.fg


class AnsiParser:
    """
    Parser class for ANSI codes.
    """

    # Terminators for cursor movement ansi controls - unsupported
    CURSOR_SET = ("H", "f", "A", "B", "C", "D", "R", "s", "u", "d", "G")

    # Terminators for erasure ansi controls - unsupported
    ERASE_SET = ("J", "K", "P")

    # Terminators for mode change ansi controls - unsupported
    MODE_SET = ("h", "l")

    # Terminators for keyboard assignment ansi controls - unsupported
    ASSIGN_SET = ("p",)

    # Terminators for color change ansi controls - supported
    COLOR_SET = ("m",)

    SETS = (CURSOR_SET, ERASE_SET, MODE_SET, ASSIGN_SET, COLOR_SET)

    def __init__(self, defaultFG, defaultBG):
        self.defaultFG, self.defaultBG = defaultFG, defaultBG
        self.currentFG, self.currentBG = self.defaultFG, self.defaultBG
        self.bold, self.flash, self.underline, self.reverse = 0, 0, 0, 0
        self.display = 1
        self.prepend = ""

    def stripEscapes(self, string):
        """
        Remove all ANSI color escapes from the given string.
        """
        result = ""
        show = 1
        i = 0
        L = len(string)
        while i < L:
            if show == 0 and string[i] in _sets:
                show = 1
            elif show:
                n = string.find("\x1B", i)
                if n == -1:
                    return result + string[i:]
                else:
                    result = result + string[i:n]
                    i = n
                    show = 0
            i = i + 1
        return result

    def writeString(self, colorstr):
        pass

    def parseString(self, str):
        """
        Turn a string input into a list of L{ColorText} elements.
        """

        if self.prepend:
            str = self.prepend + str
            self.prepend = ""
        parts = str.split("\x1B")

        if len(parts) == 1:
            self.writeString(self.formatText(parts[0]))
        else:
            self.writeString(self.formatText(parts[0]))
            for s in parts[1:]:
                L = len(s)
                i = 0
                type = None
                while i < L:
                    if s[i] not in string.digits + "[;?":
                        break
                    i += 1
                if not s:
                    self.prepend = "\x1b"
                    return
                if s[0] != "[":
                    self.writeString(self.formatText(s[i + 1 :]))
                    continue
                else:
                    s = s[1:]
                    i -= 1
                if i == L - 1:
                    self.prepend = "\x1b["
                    return
                type = _setmap.get(s[i], None)
                if type is None:
                    continue

                if type == AnsiParser.COLOR_SET:
                    self.parseColor(s[: i + 1])
                    s = s[i + 1 :]
                    self.writeString(self.formatText(s))
                elif type == AnsiParser.CURSOR_SET:
                    cursor, s = s[: i + 1], s[i + 1 :]
                    self.parseCursor(cursor)
                    self.writeString(self.formatText(s))
                elif type == AnsiParser.ERASE_SET:
                    erase, s = s[: i + 1], s[i + 1 :]
                    self.parseErase(erase)
                    self.writeString(self.formatText(s))
                elif type == AnsiParser.MODE_SET:
                    s = s[i + 1 :]
                    # self.parseErase('2J')
                    self.writeString(self.formatText(s))
                elif i == L:
                    self.prepend = "\x1B[" + s
                else:
                    _log.warn(
                        "Unhandled ANSI control type: {control_type}", control_type=s[i]
                    )
                    s = s[i + 1 :]
                    self.writeString(self.formatText(s))

    def parseColor(self, str):
        """
        Handle a single ANSI color sequence
        """
        # Drop the trailing 'm'
        str = str[:-1]

        if not str:
            str = "0"

        try:
            parts = map(int, str.split(";"))
        except ValueError:
            _log.error("Invalid ANSI color sequence: {sequence!r}", sequence=str)
            self.currentFG, self.currentBG = self.defaultFG, self.defaultBG
            return

        for x in parts:
            if x == 0:
                self.currentFG, self.currentBG = self.defaultFG, self.defaultBG
                self.bold, self.flash, self.underline, self.reverse = 0, 0, 0, 0
                self.display = 1
            elif x == 1:
                self.bold = 1
            elif 30 <= x <= 37:
                self.currentFG = x - 30
            elif 40 <= x <= 47:
                self.currentBG = x - 40
            elif x == 39:
                self.currentFG = self.defaultFG
            elif x == 49:
                self.currentBG = self.defaultBG
            elif x == 4:
                self.underline = 1
            elif x == 5:
                self.flash = 1
            elif x == 7:
                self.reverse = 1
            elif x == 8:
                self.display = 0
            elif x == 22:
                self.bold = 0
            elif x == 24:
                self.underline = 0
            elif x == 25:
                self.blink = 0
            elif x == 27:
                self.reverse = 0
            elif x == 28:
                self.display = 1
            else:
                _log.error("Unrecognised ANSI color command: {command}", command=x)

    def parseCursor(self, cursor):
        pass

    def parseErase(self, erase):
        pass

    def pickColor(self, value, mode, BOLD=ColorText.BOLD_COLORS):
        if mode:
            return ColorText.COLORS[value]
        else:
            return self.bold and BOLD[value] or ColorText.COLORS[value]

    def formatText(self, text):
        return ColorText(
            text,
            self.pickColor(self.currentFG, 0),
            self.pickColor(self.currentBG, 1),
            self.display,
            self.bold,
            self.underline,
            self.flash,
            self.reverse,
        )


_sets = "".join(map("".join, AnsiParser.SETS))

_setmap = {}
for s in AnsiParser.SETS:
    for r in s:
        _setmap[r] = s
del s
