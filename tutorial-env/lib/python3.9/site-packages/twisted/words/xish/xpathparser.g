# -*- test-case-name: twisted.words.test.test_xpath -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

# pylint: disable=W9401,W9402

# DO NOT EDIT xpathparser.py!
#
# It is generated from xpathparser.g using Yapps. Make needed changes there.
# This also means that the generated Python may not conform to Twisted's coding
# standards, so it is wrapped in exec to prevent automated checkers from
# complaining.

# HOWTO Generate me:
#
# 1.) Grab a copy of yapps2:
#         https://github.com/smurfix/yapps
#
#     Note: Do NOT use the package in debian/ubuntu as it has incompatible
#     modifications. The original at http://theory.stanford.edu/~amitp/yapps/
#     hasn't been touched since 2003 and has not been updated to work with
#     Python 3.
#
# 2.) Generate the grammar:
#
#         yapps2 xpathparser.g xpathparser.py.proto
#
# 3.) Edit the output to depend on the embedded runtime, and remove extraneous
#     imports:
#
#         sed -e '/^# Begin/,${/^[^ ].*mport/d}' -e 's/runtime\.//g' \
#             -e "s/^\(from __future\)/exec(r'''\n\1/" -e"\$a''')"
#             xpathparser.py.proto > xpathparser.py

"""
XPath Parser.

Besides the parser code produced by Yapps, this module also defines the
parse-time exception classes, a scanner class, a base class for parsers
produced by Yapps, and a context class that keeps track of the parse stack.
These have been copied from the Yapps runtime module.
"""

from __future__ import print_function
import sys, re

MIN_WINDOW=4096
# File lookup window

class SyntaxError(Exception):
    """When we run into an unexpected token, this is the exception to use"""
    def __init__(self, pos=None, msg="Bad Token", context=None):
        Exception.__init__(self)
        self.pos = pos
        self.msg = msg
        self.context = context

    def __str__(self):
        if not self.pos: return 'SyntaxError'
        else: return 'SyntaxError@%s(%s)' % (repr(self.pos), self.msg)

class NoMoreTokens(Exception):
    """Another exception object, for when we run out of tokens"""
    pass

class Token:
    """Yapps token.

    This is a container for a scanned token.
    """

    def __init__(self, type,value, pos=None):
        """Initialize a token."""
        self.type = type
        self.value = value
        self.pos = pos

    def __repr__(self):
        output = '<%s: %s' % (self.type, repr(self.value))
        if self.pos:
            output += " @ "
            if self.pos[0]:
                output += "%s:" % self.pos[0]
            if self.pos[1]:
                output += "%d" % self.pos[1]
            if self.pos[2] is not None:
                output += ".%d" % self.pos[2]
        output += ">"
        return output

in_name=0
class Scanner:
    """Yapps scanner.

    The Yapps scanner can work in context sensitive or context
    insensitive modes.  The token(i) method is used to retrieve the
    i-th token.  It takes a restrict set that limits the set of tokens
    it is allowed to return.  In context sensitive mode, this restrict
    set guides the scanner.  In context insensitive mode, there is no
    restriction (the set is always the full set of tokens).

    """

    def __init__(self, patterns, ignore, input="",
            file=None,filename=None,stacked=False):
        """Initialize the scanner.

        Parameters:
          patterns : [(terminal, uncompiled regex), ...] or None
          ignore : {terminal:None, ...}
          input : string

        If patterns is None, we assume that the subclass has
        defined self.patterns : [(terminal, compiled regex), ...].
        Note that the patterns parameter expects uncompiled regexes,
        whereas the self.patterns field expects compiled regexes.

        The 'ignore' value is either None or a callable, which is called
        with the scanner and the to-be-ignored match object; this can
        be used for include file or comment handling.
        """

        if not filename:
            global in_name
            filename="<f.%d>" % in_name
            in_name += 1

        self.input = input
        self.ignore = ignore
        self.file = file
        self.filename = filename
        self.pos = 0
        self.del_pos = 0 # skipped
        self.line = 1
        self.del_line = 0 # skipped
        self.col = 0
        self.tokens = []
        self.stack = None
        self.stacked = stacked

        self.last_read_token = None
        self.last_token = None
        self.last_types = None

        if patterns is not None:
            # Compile the regex strings into regex objects
            self.patterns = []
            for terminal, regex in patterns:
                self.patterns.append( (terminal, re.compile(regex)) )

    def stack_input(self, input="", file=None, filename=None):
        """Temporarily parse from a second file."""

        # Already reading from somewhere else: Go on top of that, please.
        if self.stack:
            # autogenerate a recursion-level-identifying filename
            if not filename:
                filename = 1
            else:
                try:
                    filename += 1
                except TypeError:
                    pass
                # now pass off to the include file
            self.stack.stack_input(input,file,filename)
        else:

            try:
                filename += 0
            except TypeError:
                pass
            else:
                filename = "<str_%d>" % filename

#			self.stack = object.__new__(self.__class__)
#			Scanner.__init__(self.stack,self.patterns,self.ignore,input,file,filename, stacked=True)

            # Note that the pattern+ignore are added by the generated
            # scanner code
            self.stack = self.__class__(input,file,filename, stacked=True)

    def get_pos(self):
        """Return a file/line/char tuple."""
        if self.stack: return self.stack.get_pos()

        return (self.filename, self.line+self.del_line, self.col)

#	def __repr__(self):
#		"""Print the last few tokens that have been scanned in"""
#		output = ''
#		for t in self.tokens:
#			output += '%s\n' % (repr(t),)
#		return output

    def print_line_with_pointer(self, pos, length=0, out=sys.stderr):
        """Print the line of 'text' that includes position 'p',
        along with a second line with a single caret (^) at position p"""

        file,line,p = pos
        if file != self.filename:
            if self.stack: return self.stack.print_line_with_pointer(pos,length=length,out=out)
            print >>out, "(%s: not in input buffer)" % file
            return

        text = self.input
        p += length-1 # starts at pos 1

        origline=line
        line -= self.del_line
        spos=0
        if line > 0:
            while 1:
                line = line - 1
                try:
                    cr = text.index("\n",spos)
                except ValueError:
                    if line:
                        text = ""
                    break
                if line == 0:
                    text = text[spos:cr]
                    break
                spos = cr+1
        else:
            print >>out, "(%s:%d not in input buffer)" % (file,origline)
            return

        # Now try printing part of the line
        text = text[max(p-80, 0):p+80]
        p = p - max(p-80, 0)

        # Strip to the left
        i = text[:p].rfind('\n')
        j = text[:p].rfind('\r')
        if i < 0 or (0 <= j < i): i = j
        if 0 <= i < p:
            p = p - i - 1
            text = text[i+1:]

        # Strip to the right
        i = text.find('\n', p)
        j = text.find('\r', p)
        if i < 0 or (0 <= j < i): i = j
        if i >= 0:
            text = text[:i]

        # Now shorten the text
        while len(text) > 70 and p > 60:
            # Cut off 10 chars
            text = "..." + text[10:]
            p = p - 7

        # Now print the string, along with an indicator
        print >>out, '> ',text
        print >>out, '> ',' '*p + '^'

    def grab_input(self):
        """Get more input if possible."""
        if not self.file: return
        if len(self.input) - self.pos >= MIN_WINDOW: return

        data = self.file.read(MIN_WINDOW)
        if data is None or data == "":
            self.file = None

        # Drop bytes from the start, if necessary.
        if self.pos > 2*MIN_WINDOW:
            self.del_pos += MIN_WINDOW
            self.del_line += self.input[:MIN_WINDOW].count("\n")
            self.pos -= MIN_WINDOW
            self.input = self.input[MIN_WINDOW:] + data
        else:
            self.input = self.input + data

    def getchar(self):
        """Return the next character."""
        self.grab_input()

        c = self.input[self.pos]
        self.pos += 1
        return c

    def token(self, restrict, context=None):
        """Scan for another token."""

        while 1:
            if self.stack:
                try:
                    return self.stack.token(restrict, context)
                except StopIteration:
                    self.stack = None

        # Keep looking for a token, ignoring any in self.ignore
            self.grab_input()

            # special handling for end-of-file
            if self.stacked and self.pos==len(self.input):
                raise StopIteration

            # Search the patterns for the longest match, with earlier
            # tokens in the list having preference
            best_match = -1
            best_pat = '(error)'
            best_m = None
            for p, regexp in self.patterns:
                # First check to see if we're ignoring this token
                if restrict and p not in restrict and p not in self.ignore:
                    continue
                m = regexp.match(self.input, self.pos)
                if m and m.end()-m.start() > best_match:
                    # We got a match that's better than the previous one
                    best_pat = p
                    best_match = m.end()-m.start()
                    best_m = m

            # If we didn't find anything, raise an error
            if best_pat == '(error)' and best_match < 0:
                msg = 'Bad Token'
                if restrict:
                    msg = 'Trying to find one of '+', '.join(restrict)
                raise SyntaxError(self.get_pos(), msg, context=context)

            ignore = best_pat in self.ignore
            value = self.input[self.pos:self.pos+best_match]
            if not ignore:
                tok=Token(type=best_pat, value=value, pos=self.get_pos())

            self.pos += best_match

            npos = value.rfind("\n")
            if npos > -1:
                self.col = best_match-npos
                self.line += value.count("\n")
            else:
                self.col += best_match

            # If we found something that isn't to be ignored, return it
            if not ignore:
                if len(self.tokens) >= 10:
                    del self.tokens[0]
                self.tokens.append(tok)
                self.last_read_token = tok
                # print repr(tok)
                return tok
            else:
                ignore = self.ignore[best_pat]
                if ignore:
                    ignore(self, best_m)

    def peek(self, *types, **kw):
        """Returns the token type for lookahead; if there are any args
        then the list of args is the set of token types to allow"""
        context = kw.get("context",None)
        if self.last_token is None:
            self.last_types = types
            self.last_token = self.token(types,context)
        elif self.last_types:
            for t in types:
                if t not in self.last_types:
                    raise NotImplementedError("Unimplemented: restriction set changed")
        return self.last_token.type

    def scan(self, type, **kw):
        """Returns the matched text, and moves to the next token"""
        context = kw.get("context",None)

        if self.last_token is None:
            tok = self.token([type],context)
        else:
            if self.last_types and type not in self.last_types:
                raise NotImplementedError("Unimplemented: restriction set changed")

            tok = self.last_token
            self.last_token = None
        if tok.type != type:
            if not self.last_types: self.last_types=[]
            raise SyntaxError(tok.pos, 'Trying to find '+type+': '+ ', '.join(self.last_types)+", got "+tok.type, context=context)
        return tok.value

class Parser:
    """Base class for Yapps-generated parsers.

    """

    def __init__(self, scanner):
        self._scanner = scanner

    def _stack(self, input="",file=None,filename=None):
        """Temporarily read from someplace else"""
        self._scanner.stack_input(input,file,filename)
        self._tok = None

    def _peek(self, *types, **kw):
        """Returns the token type for lookahead; if there are any args
        then the list of args is the set of token types to allow"""
        return self._scanner.peek(*types, **kw)

    def _scan(self, type, **kw):
        """Returns the matched text, and moves to the next token"""
        return self._scanner.scan(type, **kw)

class Context:
    """Class to represent the parser's call stack.

    Every rule creates a Context that links to its parent rule.  The
    contexts can be used for debugging.

    """

    def __init__(self, parent, scanner, rule, args=()):
        """Create a new context.

        Args:
        parent: Context object or None
        scanner: Scanner object
        rule: string (name of the rule)
        args: tuple listing parameters to the rule

        """
        self.parent = parent
        self.scanner = scanner
        self.rule = rule
        self.args = args
        while scanner.stack: scanner = scanner.stack
        self.token = scanner.last_read_token

    def __str__(self):
        output = ''
        if self.parent: output = str(self.parent) + ' > '
        output += self.rule
        return output

def print_error(err, scanner, max_ctx=None):
    """Print error messages, the parser stack, and the input text -- for human-readable error messages."""
    # NOTE: this function assumes 80 columns :-(
    # Figure out the line number
    pos = err.pos
    if not pos:
        pos = scanner.get_pos()

    file_name, line_number, column_number = pos
    print('%s:%d:%d: %s' % (file_name, line_number, column_number, err.msg), file=sys.stderr)

    scanner.print_line_with_pointer(pos)

    context = err.context
    token = None
    while context:
        print('while parsing %s%s:' % (context.rule, tuple(context.args)), file=sys.stderr)
        if context.token:
            token = context.token
        if token:
            scanner.print_line_with_pointer(token.pos, length=len(token.value))
        context = context.parent
        if max_ctx:
            max_ctx = max_ctx-1
            if not max_ctx:
                break

def wrap_error_reporter(parser, rule, *args,**kw):
    try:
        return getattr(parser, rule)(*args,**kw)
    except SyntaxError as e:
        print_error(e, parser._scanner)
    except NoMoreTokens:
        print('Could not complete parsing; stopped around here:', file=sys.stderr)
        print(parser._scanner, file=sys.stderr)

from twisted.words.xish.xpath import AttribValue, BooleanValue, CompareValue
from twisted.words.xish.xpath import Function, IndexValue, LiteralValue
from twisted.words.xish.xpath import _AnyLocation, _Location

%%
parser XPathParser:
        ignore:             "\\s+"
        token INDEX:        "[0-9]+"
        token WILDCARD:     "\*"
        token IDENTIFIER:   "[a-zA-Z][a-zA-Z0-9_\-]*"
        token ATTRIBUTE:    "\@[a-zA-Z][a-zA-Z0-9_\-]*"
        token FUNCNAME:     "[a-zA-Z][a-zA-Z0-9_]*"
        token CMP_EQ:       "\="
        token CMP_NE:       "\!\="
        token STR_DQ:       '"([^"]|(\\"))*?"'
        token STR_SQ:       "'([^']|(\\'))*?'"
        token OP_AND:       "and"
        token OP_OR:        "or"
        token END:          "$"

        rule XPATH:      PATH {{ result = PATH; current = result }}
                           ( PATH {{ current.childLocation = PATH; current = current.childLocation }} ) * END
                           {{ return  result }}

        rule PATH:       ("/" {{ result = _Location() }} | "//" {{ result = _AnyLocation() }} )
                           ( IDENTIFIER {{ result.elementName = IDENTIFIER }} | WILDCARD {{ result.elementName = None }} )
                           ( "\[" PREDICATE {{ result.predicates.append(PREDICATE) }} "\]")*
                           {{ return result }}

        rule PREDICATE:  EXPR  {{ return EXPR }} |
                         INDEX {{ return IndexValue(INDEX) }}

        rule EXPR:       FACTOR {{ e = FACTOR }}
                           ( BOOLOP FACTOR {{ e = BooleanValue(e, BOOLOP, FACTOR) }} )*
                           {{ return e }}

        rule BOOLOP:     ( OP_AND {{ return OP_AND }} | OP_OR {{ return OP_OR }} )

        rule FACTOR:     TERM {{ return TERM }}
                           | "\(" EXPR "\)" {{ return EXPR }}

        rule TERM:       VALUE            {{ t = VALUE }}
                           [ CMP VALUE  {{ t = CompareValue(t, CMP, VALUE) }} ]
                                          {{ return t }}

        rule VALUE:      "@" IDENTIFIER   {{ return AttribValue(IDENTIFIER) }} |
                         FUNCNAME         {{ f = Function(FUNCNAME); args = [] }}
                           "\(" [ VALUE      {{ args.append(VALUE) }}
                             (
                               "," VALUE     {{ args.append(VALUE) }}
                             )*
                           ] "\)"           {{ f.setParams(*args); return f }} |
                         STR              {{ return LiteralValue(STR[1:len(STR)-1]) }}

        rule CMP: (CMP_EQ  {{ return CMP_EQ }} | CMP_NE {{ return CMP_NE }})
        rule STR: (STR_DQ  {{ return STR_DQ }} | STR_SQ {{ return STR_SQ }})
