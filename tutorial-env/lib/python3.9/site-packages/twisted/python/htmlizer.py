# -*- test-case-name: twisted.python.test.test_htmlizer -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTML rendering of Python source.
"""

import keyword
import tokenize
from html import escape
from typing import List

from . import reflect


class TokenPrinter:
    """
    Format a stream of tokens and intermediate whitespace, for pretty-printing.
    """

    currentCol, currentLine = 0, 1
    lastIdentifier = parameters = 0
    encoding = "utf-8"

    def __init__(self, writer):
        """
        @param writer: A file-like object, opened in bytes mode.
        """
        self.writer = writer

    def printtoken(self, type, token, sCoordinates, eCoordinates, line):
        if hasattr(tokenize, "ENCODING") and type == tokenize.ENCODING:
            self.encoding = token
            return

        if not isinstance(token, bytes):
            token = token.encode(self.encoding)

        (srow, scol) = sCoordinates
        (erow, ecol) = eCoordinates
        if self.currentLine < srow:
            self.writer(b"\n" * (srow - self.currentLine))
            self.currentLine, self.currentCol = srow, 0
        self.writer(b" " * (scol - self.currentCol))
        if self.lastIdentifier:
            type = "identifier"
            self.parameters = 1
        elif type == tokenize.NAME:
            if keyword.iskeyword(token):
                type = "keyword"
            else:
                if self.parameters:
                    type = "parameter"
                else:
                    type = "variable"
        else:
            type = tokenize.tok_name.get(type)
            assert type is not None
            type = type.lower()
        self.writer(token, type)
        self.currentCol = ecol
        self.currentLine += token.count(b"\n")
        if self.currentLine != erow:
            self.currentCol = 0
        self.lastIdentifier = token in (b"def", b"class")
        if token == b":":
            self.parameters = 0


class HTMLWriter:
    """
    Write the stream of tokens and whitespace from L{TokenPrinter}, formating
    tokens as HTML spans.
    """

    noSpan: List[str] = []

    def __init__(self, writer):
        self.writer = writer
        noSpan: List[str] = []
        reflect.accumulateClassList(self.__class__, "noSpan", noSpan)
        self.noSpan = noSpan

    def write(self, token, type=None):
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        token = escape(token)
        token = token.encode("utf-8")
        if (type is None) or (type in self.noSpan):
            self.writer(token)
        else:
            self.writer(
                b'<span class="py-src-'
                + type.encode("utf-8")
                + b'">'
                + token
                + b"</span>"
            )


class SmallerHTMLWriter(HTMLWriter):
    """
    HTMLWriter that doesn't generate spans for some junk.

    Results in much smaller HTML output.
    """

    noSpan = ["endmarker", "indent", "dedent", "op", "newline", "nl"]


def filter(inp, out, writer=HTMLWriter):
    out.write(b"<pre>")
    printer = TokenPrinter(writer(out.write).write).printtoken
    try:
        for token in tokenize.tokenize(inp.readline):
            (tokenType, string, start, end, line) = token
            printer(tokenType, string, start, end, line)
    except tokenize.TokenError:
        pass
    out.write(b"</pre>\n")


def main():
    import sys

    stdout = getattr(sys.stdout, "buffer", sys.stdout)
    with open(sys.argv[1], "rb") as f:
        filter(f, stdout)


if __name__ == "__main__":
    main()
