# -*- coding: utf-8 -*-
"""
    pygments.lexers.qvt
    ~~~~~~~~~~~~~~~~~~~

    Lexer for QVT Operational language.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from pygments.lexer import RegexLexer, bygroups, include, combined
from pygments.token import Text, Comment, Operator, Keyword, Punctuation, \
    Name, String, Number

__all__ = ['QVToLexer']


class QVToLexer(RegexLexer):
    """
    For the `QVT Operational Mapping language <http://www.omg.org/spec/QVT/1.1/>`_.

    Reference for implementing this: «Meta Object Facility (MOF) 2.0
    Query/View/Transformation Specification», Version 1.1 - January 2011
    (http://www.omg.org/spec/QVT/1.1/), see §8.4, «Concrete Syntax» in
    particular.

    Notable tokens assignments:

    - Name.Class is assigned to the identifier following any of the following
      keywords: metamodel, class, exception, primitive, enum, transformation
      or library

    - Name.Function is assigned to the names of mappings and queries

    - Name.Builtin.Pseudo is assigned to the pre-defined variables 'this',
      'self' and 'result'.
    """
    # With obvious borrowings & inspiration from the Java, Python and C lexers

    name = 'QVTO'
    aliases = ['qvto', 'qvt']
    filenames = ['*.qvto']

    tokens = {
        'root': [
            (r'\n', Text),
            (r'[^\S\n]+', Text),
            (r'(--|//)(\s*)(directive:)?(.*)$',
             bygroups(Comment, Comment, Comment.Preproc, Comment)),
            # Uncomment the following if you want to distinguish between
            # '/*' and '/**', à la javadoc
            #(r'/[*]{2}(.|\n)*?[*]/', Comment.Multiline),
            (r'/[*](.|\n)*?[*]/', Comment.Multiline),
            (r'\\\n', Text),
            (r'(and|not|or|xor|##?)\b', Operator.Word),
            (r'([:]{1-2}=|[-+]=)\b', Operator.Word),
            (r'(@|<<|>>)\b', Keyword), # stereotypes
            (r'!=|<>|=|==|!->|->|>=|<=|[.]{3}|[+/*%=<>&|.~]', Operator),
            (r'[]{}:(),;[]', Punctuation),
            (r'(true|false|unlimited|null)\b', Keyword.Constant),
            (r'(this|self|result)\b', Name.Builtin.Pseudo),
            (r'(var)\b', Keyword.Declaration),
            (r'(from|import)\b', Keyword.Namespace, 'fromimport'),
            (r'(metamodel|class|exception|primitive|enum|transformation|library)(\s+)([a-zA-Z0-9_]+)',
             bygroups(Keyword.Word, Text, Name.Class)),
            (r'(exception)(\s+)([a-zA-Z0-9_]+)', bygroups(Keyword.Word, Text, Name.Exception)),
            (r'(main)\b', Name.Function),
            (r'(mapping|helper|query)(\s+)', bygroups(Keyword.Declaration, Text), 'operation'),
            (r'(assert)(\s+)\b', bygroups(Keyword, Text), 'assert'),
            (r'(Bag|Collection|Dict|OrderedSet|Sequence|Set|Tuple|List)\b',
             Keyword.Type),
            include('keywords'),
            ('"', String, combined('stringescape', 'dqs')),
            ("'", String, combined('stringescape', 'sqs')),
            include('name'),
            include('numbers'),
            # (r'([a-zA-Z_][a-zA-Z0-9_]*)(::)([a-zA-Z_][a-zA-Z0-9_]*)',
            # bygroups(Text, Text, Text)),
            ],

        'fromimport': [
            (r'(?:[ \t]|\\\n)+', Text),
            (r'[a-zA-Z_][a-zA-Z0-9_.]*', Name.Namespace),
            (r'', Text, '#pop'),
            ],

        'operation': [
            (r'::', Text),
            (r'(.*::)([a-zA-Z_][a-zA-Z0-9_]*)[ \t]*(\()', bygroups(Text,Name.Function, Text), '#pop')
            ],

        'assert': [
            (r'(warning|error|fatal)\b', Keyword, '#pop'),
            (r'', Text, '#pop') # all else: go back
            ],

        'keywords': [
            (r'(abstract|access|any|assert|'
             r'blackbox|break|case|collect|collectNested|'
             r'collectOne|collectselect|collectselectOne|composes|'
             r'compute|configuration|constructor|continue|datatype|'
             r'default|derived|disjuncts|do|elif|else|end|'
             r'endif|except|exists|extends|'
             r'forAll|forEach|forOne|from|if|'
             r'implies|in|inherits|init|inout|'
             r'intermediate|invresolve|invresolveIn|invresolveone|'
             r'invresolveoneIn|isUnique|iterate|late|let|'
             r'literal|log|map|merges|'
             r'modeltype|new|object|one|'
             r'ordered|out|package|population|'
             r'property|raise|readonly|references|refines|'
             r'reject|resolve|resolveIn|resolveone|resolveoneIn|'
             r'return|select|selectOne|sortedBy|static|switch|'
             r'tag|then|try|typedef|'
             r'unlimited|uses|when|where|while|with|'
             r'xcollect|xmap|xselect)\b', Keyword),
        ],

        # There is no need to distinguish between String.Single and
        # String.Double: 'strings' is factorised for 'dqs' and 'sqs'
        'strings': [
            (r'[^\\\'"\n]+', String),
            # quotes, percents and backslashes must be parsed one at a time
            (r'[\'"\\]', String),
            ],
        'stringescape': [
            (r'\\([\\btnfr"\']|u[0-3][0-7]{2}|u[0-7]{1,2})', String.Escape)
        ],
        'dqs': [ # double-quoted string
            (r'"', String, '#pop'),
            (r'\\\\|\\"', String.Escape),
            include('strings')
            ],
        'sqs': [ # single-quoted string
            (r"'", String, '#pop'),
            (r"\\\\|\\'", String.Escape),
            include('strings')
            ],
        'name': [
            ('[a-zA-Z_][a-zA-Z0-9_]*', Name),
            ],
        # numbers: excerpt taken from the python lexer
        'numbers': [
            (r'(\d+\.\d*|\d*\.\d+)([eE][+-]?[0-9]+)?', Number.Float),
            (r'\d+[eE][+-]?[0-9]+', Number.Float),
            (r'\d+', Number.Integer)
        ],
       }

