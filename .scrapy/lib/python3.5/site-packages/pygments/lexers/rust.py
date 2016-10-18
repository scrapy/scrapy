# -*- coding: utf-8 -*-
"""
    pygments.lexers.rust
    ~~~~~~~~~~~~~~~~~~~~

    Lexers for the Rust language.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from pygments.lexer import RegexLexer, include, bygroups, words, default
from pygments.token import Text, Comment, Operator, Keyword, Name, String, \
    Number, Punctuation, Whitespace

__all__ = ['RustLexer']


class RustLexer(RegexLexer):
    """
    Lexer for the Rust programming language (version 1.0).

    .. versionadded:: 1.6
    """
    name = 'Rust'
    filenames = ['*.rs', '*.rs.in']
    aliases = ['rust']
    mimetypes = ['text/rust']

    tokens = {
        'root': [
            # rust allows a file to start with a shebang, but if the first line
            # starts with #![ then it’s not a shebang but a crate attribute.
            (r'#![^[\r\n].*$', Comment.Preproc),
            default('base'),
        ],
        'base': [
            # Whitespace and Comments
            (r'\n', Whitespace),
            (r'\s+', Whitespace),
            (r'//!.*?\n', String.Doc),
            (r'///(\n|[^/].*?\n)', String.Doc),
            (r'//(.*?)\n', Comment.Single),
            (r'/\*\*(\n|[^/*])', String.Doc, 'doccomment'),
            (r'/\*!', String.Doc, 'doccomment'),
            (r'/\*', Comment.Multiline, 'comment'),

            # Macro parameters
            (r"""\$([a-zA-Z_]\w*|\(,?|\),?|,?)""", Comment.Preproc),
            # Keywords
            (words((
                'as', 'box', 'crate', 'do', 'else', 'enum', 'extern',  # break and continue are in labels
                'fn', 'for', 'if', 'impl', 'in', 'loop', 'match', 'mut', 'priv',
                'proc', 'pub', 'ref', 'return', 'static', 'struct',
                'trait', 'true', 'type', 'unsafe', 'while'), suffix=r'\b'),
             Keyword),
            (words(('alignof', 'be', 'const', 'offsetof', 'pure', 'sizeof',
                    'typeof', 'once', 'unsized', 'yield'), suffix=r'\b'),
             Keyword.Reserved),
            (r'(mod|use)\b', Keyword.Namespace),
            (r'(true|false)\b', Keyword.Constant),
            (r'let\b', Keyword.Declaration),
            (words(('u8', 'u16', 'u32', 'u64', 'i8', 'i16', 'i32', 'i64', 'usize',
                    'isize', 'f32', 'f64', 'str', 'bool'), suffix=r'\b'),
             Keyword.Type),
            (r'self\b', Name.Builtin.Pseudo),
            # Prelude (taken from Rust’s src/libstd/prelude.rs)
            (words((
                # Reexported core operators
                'Copy', 'Send', 'Sized', 'Sync',
                'Drop', 'Fn', 'FnMut', 'FnOnce',

                # Reexported functions
                'drop',

                # Reexported types and traits
                'Box',
                'ToOwned',
                'Clone',
                'PartialEq', 'PartialOrd', 'Eq', 'Ord',
                'AsRef', 'AsMut', 'Into', 'From',
                'Default',
                'Iterator', 'Extend', 'IntoIterator',
                'DoubleEndedIterator', 'ExactSizeIterator',
                'Option',
                'Some', 'None',
                'Result',
                'Ok', 'Err',
                'SliceConcatExt',
                'String', 'ToString',
                'Vec',
                ), suffix=r'\b'),
             Name.Builtin),
            # Labels
            (r'(break|continue)(\s*)(\'[A-Za-z_]\w*)?', bygroups(Keyword, Text.Whitespace, Name.Label)),
            # Character Literal
            (r"""'(\\['"\\nrt]|\\x[0-7][0-9a-fA-F]|\\0"""
             r"""|\\u\{[0-9a-fA-F]{1,6}\}|.)'""",
             String.Char),
            (r"""b'(\\['"\\nrt]|\\x[0-9a-fA-F]{2}|\\0"""
             r"""|\\u\{[0-9a-fA-F]{1,6}\}|.)'""",
             String.Char),
            # Binary Literal
            (r'0b[01_]+', Number.Bin, 'number_lit'),
            # Octal Literal
            (r'0o[0-7_]+', Number.Oct, 'number_lit'),
            # Hexadecimal Literal
            (r'0[xX][0-9a-fA-F_]+', Number.Hex, 'number_lit'),
            # Decimal Literal
            (r'[0-9][0-9_]*(\.[0-9_]+[eE][+\-]?[0-9_]+|'
             r'\.[0-9_]*(?!\.)|[eE][+\-]?[0-9_]+)', Number.Float, 'number_lit'),
            (r'[0-9][0-9_]*', Number.Integer, 'number_lit'),
            # String Literal
            (r'b"', String, 'bytestring'),
            (r'"', String, 'string'),
            (r'b?r(#*)".*?"\1', String),

            # Lifetime
            (r"""'static""", Name.Builtin),
            (r"""'[a-zA-Z_]\w*""", Name.Attribute),

            # Operators and Punctuation
            (r'[{}()\[\],.;]', Punctuation),
            (r'[+\-*/%&|<>^!~@=:?]', Operator),

            # Identifier
            (r'[a-zA-Z_]\w*', Name),

            # Attributes
            (r'#!?\[', Comment.Preproc, 'attribute['),
            # Macros
            (r'([A-Za-z_]\w*)(!)(\s*)([A-Za-z_]\w*)?(\s*)(\{)',
             bygroups(Comment.Preproc, Punctuation, Whitespace, Name,
                      Whitespace, Punctuation), 'macro{'),
            (r'([A-Za-z_]\w*)(!)(\s*)([A-Za-z_]\w*)?(\()',
             bygroups(Comment.Preproc, Punctuation, Whitespace, Name,
                      Punctuation), 'macro('),
        ],
        'comment': [
            (r'[^*/]+', Comment.Multiline),
            (r'/\*', Comment.Multiline, '#push'),
            (r'\*/', Comment.Multiline, '#pop'),
            (r'[*/]', Comment.Multiline),
        ],
        'doccomment': [
            (r'[^*/]+', String.Doc),
            (r'/\*', String.Doc, '#push'),
            (r'\*/', String.Doc, '#pop'),
            (r'[*/]', String.Doc),
        ],
        'number_lit': [
            (r'[ui](8|16|32|64|size)', Keyword, '#pop'),
            (r'f(32|64)', Keyword, '#pop'),
            default('#pop'),
        ],
        'string': [
            (r'"', String, '#pop'),
            (r"""\\['"\\nrt]|\\x[0-7][0-9a-fA-F]|\\0"""
             r"""|\\u\{[0-9a-fA-F]{1,6}\}""", String.Escape),
            (r'[^\\"]+', String),
            (r'\\', String),
        ],
        'bytestring': [
            (r"""\\x[89a-fA-F][0-9a-fA-F]""", String.Escape),
            include('string'),
        ],
        'macro{': [
            (r'\{', Operator, '#push'),
            (r'\}', Operator, '#pop'),
        ],
        'macro(': [
            (r'\(', Operator, '#push'),
            (r'\)', Operator, '#pop'),
        ],
        'attribute_common': [
            (r'"', String, 'string'),
            (r'\[', Comment.Preproc, 'attribute['),
            (r'\(', Comment.Preproc, 'attribute('),
        ],
        'attribute[': [
            include('attribute_common'),
            (r'\];?', Comment.Preproc, '#pop'),
            (r'[^"\]]+', Comment.Preproc),
        ],
        'attribute(': [
            include('attribute_common'),
            (r'\);?', Comment.Preproc, '#pop'),
            (r'[^")]+', Comment.Preproc),
        ],
    }
