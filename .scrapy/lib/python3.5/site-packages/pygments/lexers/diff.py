# -*- coding: utf-8 -*-
"""
    pygments.lexers.diff
    ~~~~~~~~~~~~~~~~~~~~

    Lexers for diff/patch formats.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from pygments.lexer import RegexLexer, include, bygroups
from pygments.token import Text, Comment, Operator, Keyword, Name, Generic, \
    Literal

__all__ = ['DiffLexer', 'DarcsPatchLexer']


class DiffLexer(RegexLexer):
    """
    Lexer for unified or context-style diffs or patches.
    """

    name = 'Diff'
    aliases = ['diff', 'udiff']
    filenames = ['*.diff', '*.patch']
    mimetypes = ['text/x-diff', 'text/x-patch']

    tokens = {
        'root': [
            (r' .*\n', Text),
            (r'\+.*\n', Generic.Inserted),
            (r'-.*\n', Generic.Deleted),
            (r'!.*\n', Generic.Strong),
            (r'@.*\n', Generic.Subheading),
            (r'([Ii]ndex|diff).*\n', Generic.Heading),
            (r'=.*\n', Generic.Heading),
            (r'.*\n', Text),
        ]
    }

    def analyse_text(text):
        if text[:7] == 'Index: ':
            return True
        if text[:5] == 'diff ':
            return True
        if text[:4] == '--- ':
            return 0.9


class DarcsPatchLexer(RegexLexer):
    """
    DarcsPatchLexer is a lexer for the various versions of the darcs patch
    format.  Examples of this format are derived by commands such as
    ``darcs annotate --patch`` and ``darcs send``.

    .. versionadded:: 0.10
    """

    name = 'Darcs Patch'
    aliases = ['dpatch']
    filenames = ['*.dpatch', '*.darcspatch']

    DPATCH_KEYWORDS = ('hunk', 'addfile', 'adddir', 'rmfile', 'rmdir', 'move',
                       'replace')

    tokens = {
        'root': [
            (r'<', Operator),
            (r'>', Operator),
            (r'\{', Operator),
            (r'\}', Operator),
            (r'(\[)((?:TAG )?)(.*)(\n)(.*)(\*\*)(\d+)(\s?)(\])',
             bygroups(Operator, Keyword, Name, Text, Name, Operator,
                      Literal.Date, Text, Operator)),
            (r'(\[)((?:TAG )?)(.*)(\n)(.*)(\*\*)(\d+)(\s?)',
             bygroups(Operator, Keyword, Name, Text, Name, Operator,
                      Literal.Date, Text), 'comment'),
            (r'New patches:', Generic.Heading),
            (r'Context:', Generic.Heading),
            (r'Patch bundle hash:', Generic.Heading),
            (r'(\s*)(%s)(.*\n)' % '|'.join(DPATCH_KEYWORDS),
                bygroups(Text, Keyword, Text)),
            (r'\+', Generic.Inserted, "insert"),
            (r'-', Generic.Deleted, "delete"),
            (r'.*\n', Text),
        ],
        'comment': [
            (r'[^\]].*\n', Comment),
            (r'\]', Operator, "#pop"),
        ],
        'specialText': [            # darcs add [_CODE_] special operators for clarity
            (r'\n', Text, "#pop"),  # line-based
            (r'\[_[^_]*_]', Operator),
        ],
        'insert': [
            include('specialText'),
            (r'\[', Generic.Inserted),
            (r'[^\n\[]+', Generic.Inserted),
        ],
        'delete': [
            include('specialText'),
            (r'\[', Generic.Deleted),
            (r'[^\n\[]+', Generic.Deleted),
        ],
    }
