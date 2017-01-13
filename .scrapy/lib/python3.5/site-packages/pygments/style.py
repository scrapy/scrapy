# -*- coding: utf-8 -*-
"""
    pygments.style
    ~~~~~~~~~~~~~~

    Basic style object.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from pygments.token import Token, STANDARD_TYPES
from pygments.util import add_metaclass


class StyleMeta(type):

    def __new__(mcs, name, bases, dct):
        obj = type.__new__(mcs, name, bases, dct)
        for token in STANDARD_TYPES:
            if token not in obj.styles:
                obj.styles[token] = ''

        def colorformat(text):
            if text[0:1] == '#':
                col = text[1:]
                if len(col) == 6:
                    return col
                elif len(col) == 3:
                    return col[0]*2 + col[1]*2 + col[2]*2
            elif text == '':
                return ''
            assert False, "wrong color format %r" % text

        _styles = obj._styles = {}

        for ttype in obj.styles:
            for token in ttype.split():
                if token in _styles:
                    continue
                ndef = _styles.get(token.parent, None)
                styledefs = obj.styles.get(token, '').split()
                if not ndef or token is None:
                    ndef = ['', 0, 0, 0, '', '', 0, 0, 0]
                elif 'noinherit' in styledefs and token is not Token:
                    ndef = _styles[Token][:]
                else:
                    ndef = ndef[:]
                _styles[token] = ndef
                for styledef in obj.styles.get(token, '').split():
                    if styledef == 'noinherit':
                        pass
                    elif styledef == 'bold':
                        ndef[1] = 1
                    elif styledef == 'nobold':
                        ndef[1] = 0
                    elif styledef == 'italic':
                        ndef[2] = 1
                    elif styledef == 'noitalic':
                        ndef[2] = 0
                    elif styledef == 'underline':
                        ndef[3] = 1
                    elif styledef == 'nounderline':
                        ndef[3] = 0
                    elif styledef[:3] == 'bg:':
                        ndef[4] = colorformat(styledef[3:])
                    elif styledef[:7] == 'border:':
                        ndef[5] = colorformat(styledef[7:])
                    elif styledef == 'roman':
                        ndef[6] = 1
                    elif styledef == 'sans':
                        ndef[7] = 1
                    elif styledef == 'mono':
                        ndef[8] = 1
                    else:
                        ndef[0] = colorformat(styledef)

        return obj

    def style_for_token(cls, token):
        t = cls._styles[token]
        return {
            'color':        t[0] or None,
            'bold':         bool(t[1]),
            'italic':       bool(t[2]),
            'underline':    bool(t[3]),
            'bgcolor':      t[4] or None,
            'border':       t[5] or None,
            'roman':        bool(t[6]) or None,
            'sans':         bool(t[7]) or None,
            'mono':         bool(t[8]) or None,
        }

    def list_styles(cls):
        return list(cls)

    def styles_token(cls, ttype):
        return ttype in cls._styles

    def __iter__(cls):
        for token in cls._styles:
            yield token, cls.style_for_token(token)

    def __len__(cls):
        return len(cls._styles)


@add_metaclass(StyleMeta)
class Style(object):

    #: overall background color (``None`` means transparent)
    background_color = '#ffffff'

    #: highlight background color
    highlight_color = '#ffffcc'

    #: Style definitions for individual token types.
    styles = {}
