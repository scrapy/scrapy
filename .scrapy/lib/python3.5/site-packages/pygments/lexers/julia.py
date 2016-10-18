# -*- coding: utf-8 -*-
"""
    pygments.lexers.julia
    ~~~~~~~~~~~~~~~~~~~~~

    Lexers for the Julia language.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re

from pygments.lexer import Lexer, RegexLexer, bygroups, combined, do_insertions
from pygments.token import Text, Comment, Operator, Keyword, Name, String, \
    Number, Punctuation, Generic
from pygments.util import shebang_matches, unirange

__all__ = ['JuliaLexer', 'JuliaConsoleLexer']


class JuliaLexer(RegexLexer):
    """
    For `Julia <http://julialang.org/>`_ source code.

    .. versionadded:: 1.6
    """
    name = 'Julia'
    aliases = ['julia', 'jl']
    filenames = ['*.jl']
    mimetypes = ['text/x-julia', 'application/x-julia']

    flags = re.MULTILINE | re.UNICODE

    builtins = [
        'exit', 'whos', 'edit', 'load', 'is', 'isa', 'isequal', 'typeof', 'tuple',
        'ntuple', 'uid', 'hash', 'finalizer', 'convert', 'promote', 'subtype',
        'typemin', 'typemax', 'realmin', 'realmax', 'sizeof', 'eps', 'promote_type',
        'method_exists', 'applicable', 'invoke', 'dlopen', 'dlsym', 'system',
        'error', 'throw', 'assert', 'new', 'Inf', 'Nan', 'pi', 'im',
    ]

    tokens = {
        'root': [
            (r'\n', Text),
            (r'[^\S\n]+', Text),
            (r'#=', Comment.Multiline, "blockcomment"),
            (r'#.*$', Comment),
            (r'[]{}:(),;[@]', Punctuation),
            (r'\\\n', Text),
            (r'\\', Text),

            # keywords
            (r'(begin|while|for|in|return|break|continue|'
             r'macro|quote|let|if|elseif|else|try|catch|end|'
             r'bitstype|ccall|do|using|module|import|export|'
             r'importall|baremodule|immutable)\b', Keyword),
            (r'(local|global|const)\b', Keyword.Declaration),
            (r'(Bool|Int|Int8|Int16|Int32|Int64|Uint|Uint8|Uint16|Uint32|Uint64'
             r'|Float32|Float64|Complex64|Complex128|Any|Nothing|None)\b',
                Keyword.Type),

            # functions
            (r'(function)((?:\s|\\\s)+)',
                bygroups(Keyword, Name.Function), 'funcname'),

            # types
            (r'(type|typealias|abstract|immutable)((?:\s|\\\s)+)',
                bygroups(Keyword, Name.Class), 'typename'),

            # operators
            (r'==|!=|<=|>=|->|&&|\|\||::|<:|[-~+/*%=<>&^|.?!$]', Operator),
            (r'\.\*|\.\^|\.\\|\.\/|\\', Operator),

            # builtins
            ('(' + '|'.join(builtins) + r')\b',  Name.Builtin),

            # backticks
            (r'`(?s).*?`', String.Backtick),

            # chars
            (r"'(\\.|\\[0-7]{1,3}|\\x[a-fA-F0-9]{1,3}|\\u[a-fA-F0-9]{1,4}|"
             r"\\U[a-fA-F0-9]{1,6}|[^\\\'\n])'", String.Char),

            # try to match trailing transpose
            (r'(?<=[.\w)\]])\'+', Operator),

            # strings
            (r'(?:[IL])"', String, 'string'),
            (r'[E]?"', String, combined('stringescape', 'string')),

            # names
            (r'@[\w.]+', Name.Decorator),
            (u'(?:[a-zA-Z_\u00A1-\uffff]|%s)(?:[a-zA-Z_0-9\u00A1-\uffff]|%s)*!*' %
             ((unirange(0x10000, 0x10ffff),)*2), Name),

            # numbers
            (r'(\d+(_\d+)+\.\d*|\d*\.\d+(_\d+)+)([eEf][+-]?[0-9]+)?', Number.Float),
            (r'(\d+\.\d*|\d*\.\d+)([eEf][+-]?[0-9]+)?', Number.Float),
            (r'\d+(_\d+)+[eEf][+-]?[0-9]+', Number.Float),
            (r'\d+[eEf][+-]?[0-9]+', Number.Float),
            (r'0b[01]+(_[01]+)+', Number.Bin),
            (r'0b[01]+', Number.Bin),
            (r'0o[0-7]+(_[0-7]+)+', Number.Oct),
            (r'0o[0-7]+', Number.Oct),
            (r'0x[a-fA-F0-9]+(_[a-fA-F0-9]+)+', Number.Hex),
            (r'0x[a-fA-F0-9]+', Number.Hex),
            (r'\d+(_\d+)+', Number.Integer),
            (r'\d+', Number.Integer)
        ],

        'funcname': [
            ('[a-zA-Z_]\w*', Name.Function, '#pop'),
            ('\([^\s\w{]{1,2}\)', Operator, '#pop'),
            ('[^\s\w{]{1,2}', Operator, '#pop'),
        ],

        'typename': [
            ('[a-zA-Z_]\w*', Name.Class, '#pop')
        ],

        'stringescape': [
            (r'\\([\\abfnrtv"\']|\n|N\{.*?\}|u[a-fA-F0-9]{4}|'
             r'U[a-fA-F0-9]{8}|x[a-fA-F0-9]{2}|[0-7]{1,3})', String.Escape)
        ],
        "blockcomment": [
            (r'[^=#]', Comment.Multiline),
            (r'#=', Comment.Multiline, '#push'),
            (r'=#', Comment.Multiline, '#pop'),
            (r'[=#]', Comment.Multiline),
        ],
        'string': [
            (r'"', String, '#pop'),
            (r'\\\\|\\"|\\\n', String.Escape),  # included here for raw strings
            # Interpolation is defined as "$" followed by the shortest full
            # expression, which is something we can't parse.
            # Include the most common cases here: $word, and $(paren'd expr).
            (r'\$[a-zA-Z_]+', String.Interpol),
            (r'\$\(', String.Interpol, 'in-intp'),
            # @printf and @sprintf formats
            (r'%[-#0 +]*([0-9]+|[*])?(\.([0-9]+|[*]))?[hlL]?[diouxXeEfFgGcrs%]',
             String.Interpol),
            (r'[^$%"\\]+', String),
            # unhandled special signs
            (r'[$%"\\]', String),
        ],
        'in-intp': [
            (r'[^()]+', String.Interpol),
            (r'\(', String.Interpol, '#push'),
            (r'\)', String.Interpol, '#pop'),
        ]
    }

    def analyse_text(text):
        return shebang_matches(text, r'julia')


line_re  = re.compile('.*?\n')


class JuliaConsoleLexer(Lexer):
    """
    For Julia console sessions. Modeled after MatlabSessionLexer.

    .. versionadded:: 1.6
    """
    name = 'Julia console'
    aliases = ['jlcon']

    def get_tokens_unprocessed(self, text):
        jllexer = JuliaLexer(**self.options)

        curcode = ''
        insertions = []

        for match in line_re.finditer(text):
            line = match.group()

            if line.startswith('julia>'):
                insertions.append((len(curcode),
                                   [(0, Generic.Prompt, line[:6])]))
                curcode += line[6:]

            elif line.startswith('      '):

                idx = len(curcode)

                # without is showing error on same line as before...?
                line = "\n" + line
                token = (0, Generic.Traceback, line)
                insertions.append((idx, [token]))

            else:
                if curcode:
                    for item in do_insertions(
                            insertions, jllexer.get_tokens_unprocessed(curcode)):
                        yield item
                    curcode = ''
                    insertions = []

                yield match.start(), Generic.Output, line

        if curcode:  # or item:
            for item in do_insertions(
                    insertions, jllexer.get_tokens_unprocessed(curcode)):
                yield item
