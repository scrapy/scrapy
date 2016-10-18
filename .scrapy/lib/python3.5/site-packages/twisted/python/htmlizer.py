# -*- test-case-name: twisted.python.test.test_htmlizer -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTML rendering of Python source.
"""

import tokenize, cgi, keyword
from . import reflect

class TokenPrinter:

    currentCol, currentLine = 0, 1
    lastIdentifier = parameters = 0

    def __init__(self, writer):
        self.writer = writer

    def printtoken(self, type, token, sCoordinates, eCoordinates, line):
        (srow, scol) = sCoordinates
        (erow, ecol) = eCoordinates
        #print "printtoken(%r,%r,%r,(%r,%r),(%r,%r),%r), row=%r,col=%r" % (
        #    self, type, token, srow,scol, erow,ecol, line,
        #    self.currentLine, self.currentCol)
        if self.currentLine < srow:
            self.writer('\n'*(srow-self.currentLine))
            self.currentLine, self.currentCol = srow, 0
        self.writer(' '*(scol-self.currentCol))
        if self.lastIdentifier:
            type = "identifier"
            self.parameters = 1
        elif type == tokenize.NAME:
             if keyword.iskeyword(token):
                 type = 'keyword'
             else:
                 if self.parameters:
                     type = 'parameter'
                 else:
                     type = 'variable'
        else:
            type = tokenize.tok_name.get(type).lower()
        self.writer(token, type)
        self.currentCol = ecol
        self.currentLine += token.count('\n')
        if self.currentLine != erow:
            self.currentCol = 0
        self.lastIdentifier = token in ('def', 'class')
        if token == ':':
            self.parameters = 0


class HTMLWriter:

    noSpan = []

    def __init__(self, writer):
        self.writer = writer
        noSpan = []
        reflect.accumulateClassList(self.__class__, "noSpan", noSpan)
        self.noSpan = noSpan

    def write(self, token, type=None):
        token = cgi.escape(token)
        if (type is None) or (type in self.noSpan):
            self.writer(token)
        else:
            self.writer('<span class="py-src-%s">%s</span>' %
                        (type, token))


class SmallerHTMLWriter(HTMLWriter):
    """HTMLWriter that doesn't generate spans for some junk.

    Results in much smaller HTML output.
    """
    noSpan = ["endmarker", "indent", "dedent", "op", "newline", "nl"]

def filter(inp, out, writer=HTMLWriter):
    out.write('<pre>')
    printer = TokenPrinter(writer(out.write).write).printtoken
    try:
        tokenize.tokenize(inp.readline, printer)
    except tokenize.TokenError:
        pass
    out.write('</pre>\n')

def main():
    import sys
    with open(sys.argv[1]) as f:
        filter(f, sys.stdout)

if __name__ == '__main__':
   main()
