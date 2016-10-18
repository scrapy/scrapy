# -*- coding: utf-8 -*-
"""
    pygments.lexers.css
    ~~~~~~~~~~~~~~~~~~~

    Lexers for CSS and related stylesheet formats.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re
import copy

from pygments.lexer import ExtendedRegexLexer, RegexLexer, include, bygroups, \
    default, words, inherit
from pygments.token import Text, Comment, Operator, Keyword, Name, String, \
    Number, Punctuation
from pygments.util import iteritems

__all__ = ['CssLexer', 'SassLexer', 'ScssLexer', 'LessCssLexer']


class CssLexer(RegexLexer):
    """
    For CSS (Cascading Style Sheets).
    """

    name = 'CSS'
    aliases = ['css']
    filenames = ['*.css']
    mimetypes = ['text/css']

    tokens = {
        'root': [
            include('basics'),
        ],
        'basics': [
            (r'\s+', Text),
            (r'/\*(?:.|\n)*?\*/', Comment),
            (r'\{', Punctuation, 'content'),
            (r'\:[\w-]+', Name.Decorator),
            (r'\.[\w-]+', Name.Class),
            (r'\#[\w-]+', Name.Namespace),
            (r'@[\w-]+', Keyword, 'atrule'),
            (r'[\w-]+', Name.Tag),
            (r'[~^*!%&$\[\]()<>|+=@:;,./?-]', Operator),
            (r'"(\\\\|\\"|[^"])*"', String.Double),
            (r"'(\\\\|\\'|[^'])*'", String.Single)
        ],
        'atrule': [
            (r'\{', Punctuation, 'atcontent'),
            (r';', Punctuation, '#pop'),
            include('basics'),
        ],
        'atcontent': [
            include('basics'),
            (r'\}', Punctuation, '#pop:2'),
        ],
        'content': [
            (r'\s+', Text),
            (r'\}', Punctuation, '#pop'),
            (r'url\(.*?\)', String.Other),
            (r'^@.*?$', Comment.Preproc),
            (words((
                'azimuth', 'background-attachment', 'background-color',
                'background-image', 'background-position', 'background-repeat',
                'background', 'border-bottom-color', 'border-bottom-style',
                'border-bottom-width', 'border-left-color', 'border-left-style',
                'border-left-width', 'border-right', 'border-right-color',
                'border-right-style', 'border-right-width', 'border-top-color',
                'border-top-style', 'border-top-width', 'border-bottom',
                'border-collapse', 'border-left', 'border-width', 'border-color',
                'border-spacing', 'border-style', 'border-top', 'border', 'caption-side',
                'clear', 'clip', 'color', 'content', 'counter-increment', 'counter-reset',
                'cue-after', 'cue-before', 'cue', 'cursor', 'direction', 'display',
                'elevation', 'empty-cells', 'float', 'font-family', 'font-size',
                'font-size-adjust', 'font-stretch', 'font-style', 'font-variant',
                'font-weight', 'font', 'height', 'letter-spacing', 'line-height',
                'list-style-type', 'list-style-image', 'list-style-position',
                'list-style', 'margin-bottom', 'margin-left', 'margin-right',
                'margin-top', 'margin', 'marker-offset', 'marks', 'max-height', 'max-width',
                'min-height', 'min-width', 'opacity', 'orphans', 'outline-color',
                'outline-style', 'outline-width', 'outline', 'overflow', 'overflow-x',
                'overflow-y', 'padding-bottom', 'padding-left', 'padding-right', 'padding-top',
                'padding', 'page', 'page-break-after', 'page-break-before', 'page-break-inside',
                'pause-after', 'pause-before', 'pause', 'pitch-range', 'pitch',
                'play-during', 'position', 'quotes', 'richness', 'right', 'size',
                'speak-header', 'speak-numeral', 'speak-punctuation', 'speak',
                'speech-rate', 'stress', 'table-layout', 'text-align', 'text-decoration',
                'text-indent', 'text-shadow', 'text-transform', 'top', 'unicode-bidi',
                'vertical-align', 'visibility', 'voice-family', 'volume', 'white-space',
                'widows', 'width', 'word-spacing', 'z-index', 'bottom',
                'above', 'absolute', 'always', 'armenian', 'aural', 'auto', 'avoid', 'baseline',
                'behind', 'below', 'bidi-override', 'blink', 'block', 'bolder', 'bold', 'both',
                'capitalize', 'center-left', 'center-right', 'center', 'circle',
                'cjk-ideographic', 'close-quote', 'collapse', 'condensed', 'continuous',
                'crop', 'crosshair', 'cross', 'cursive', 'dashed', 'decimal-leading-zero',
                'decimal', 'default', 'digits', 'disc', 'dotted', 'double', 'e-resize', 'embed',
                'extra-condensed', 'extra-expanded', 'expanded', 'fantasy', 'far-left',
                'far-right', 'faster', 'fast', 'fixed', 'georgian', 'groove', 'hebrew', 'help',
                'hidden', 'hide', 'higher', 'high', 'hiragana-iroha', 'hiragana', 'icon',
                'inherit', 'inline-table', 'inline', 'inset', 'inside', 'invert', 'italic',
                'justify', 'katakana-iroha', 'katakana', 'landscape', 'larger', 'large',
                'left-side', 'leftwards', 'left', 'level', 'lighter', 'line-through', 'list-item',
                'loud', 'lower-alpha', 'lower-greek', 'lower-roman', 'lowercase', 'ltr',
                'lower', 'low', 'medium', 'message-box', 'middle', 'mix', 'monospace',
                'n-resize', 'narrower', 'ne-resize', 'no-close-quote', 'no-open-quote',
                'no-repeat', 'none', 'normal', 'nowrap', 'nw-resize', 'oblique', 'once',
                'open-quote', 'outset', 'outside', 'overline', 'pointer', 'portrait', 'px',
                'relative', 'repeat-x', 'repeat-y', 'repeat', 'rgb', 'ridge', 'right-side',
                'rightwards', 's-resize', 'sans-serif', 'scroll', 'se-resize',
                'semi-condensed', 'semi-expanded', 'separate', 'serif', 'show', 'silent',
                'slower', 'slow', 'small-caps', 'small-caption', 'smaller', 'soft', 'solid',
                'spell-out', 'square', 'static', 'status-bar', 'super', 'sw-resize',
                'table-caption', 'table-cell', 'table-column', 'table-column-group',
                'table-footer-group', 'table-header-group', 'table-row',
                'table-row-group', 'text-bottom', 'text-top', 'text', 'thick', 'thin',
                'transparent', 'ultra-condensed', 'ultra-expanded', 'underline',
                'upper-alpha', 'upper-latin', 'upper-roman', 'uppercase', 'url',
                'visible', 'w-resize', 'wait', 'wider', 'x-fast', 'x-high', 'x-large', 'x-loud',
                'x-low', 'x-small', 'x-soft', 'xx-large', 'xx-small', 'yes'), suffix=r'\b'),
             Name.Builtin),
            (words((
                'indigo', 'gold', 'firebrick', 'indianred', 'yellow', 'darkolivegreen',
                'darkseagreen', 'mediumvioletred', 'mediumorchid', 'chartreuse',
                'mediumslateblue', 'black', 'springgreen', 'crimson', 'lightsalmon', 'brown',
                'turquoise', 'olivedrab', 'cyan', 'silver', 'skyblue', 'gray', 'darkturquoise',
                'goldenrod', 'darkgreen', 'darkviolet', 'darkgray', 'lightpink', 'teal',
                'darkmagenta', 'lightgoldenrodyellow', 'lavender', 'yellowgreen', 'thistle',
                'violet', 'navy', 'orchid', 'blue', 'ghostwhite', 'honeydew', 'cornflowerblue',
                'darkblue', 'darkkhaki', 'mediumpurple', 'cornsilk', 'red', 'bisque', 'slategray',
                'darkcyan', 'khaki', 'wheat', 'deepskyblue', 'darkred', 'steelblue', 'aliceblue',
                'gainsboro', 'mediumturquoise', 'floralwhite', 'coral', 'purple', 'lightgrey',
                'lightcyan', 'darksalmon', 'beige', 'azure', 'lightsteelblue', 'oldlace',
                'greenyellow', 'royalblue', 'lightseagreen', 'mistyrose', 'sienna',
                'lightcoral', 'orangered', 'navajowhite', 'lime', 'palegreen', 'burlywood',
                'seashell', 'mediumspringgreen', 'fuchsia', 'papayawhip', 'blanchedalmond',
                'peru', 'aquamarine', 'white', 'darkslategray', 'ivory', 'dodgerblue',
                'lemonchiffon', 'chocolate', 'orange', 'forestgreen', 'slateblue', 'olive',
                'mintcream', 'antiquewhite', 'darkorange', 'cadetblue', 'moccasin',
                'limegreen', 'saddlebrown', 'darkslateblue', 'lightskyblue', 'deeppink',
                'plum', 'aqua', 'darkgoldenrod', 'maroon', 'sandybrown', 'magenta', 'tan',
                'rosybrown', 'pink', 'lightblue', 'palevioletred', 'mediumseagreen',
                'dimgray', 'powderblue', 'seagreen', 'snow', 'mediumblue', 'midnightblue',
                'paleturquoise', 'palegoldenrod', 'whitesmoke', 'darkorchid', 'salmon',
                'lightslategray', 'lawngreen', 'lightgreen', 'tomato', 'hotpink',
                'lightyellow', 'lavenderblush', 'linen', 'mediumaquamarine', 'green',
                'blueviolet', 'peachpuff'), suffix=r'\b'),
             Name.Builtin),
            (r'\!important', Comment.Preproc),
            (r'/\*(?:.|\n)*?\*/', Comment),
            (r'\#[a-zA-Z0-9]{1,6}', Number),
            (r'[.-]?[0-9]*[.]?[0-9]+(em|px|pt|pc|in|mm|cm|ex|s)\b', Number),
            # Separate regex for percentages, as can't do word boundaries with %
            (r'[.-]?[0-9]*[.]?[0-9]+%', Number),
            (r'-?[0-9]+', Number),
            (r'[~^*!%&<>|+=@:,./?-]+', Operator),
            (r'[\[\]();]+', Punctuation),
            (r'"(\\\\|\\"|[^"])*"', String.Double),
            (r"'(\\\\|\\'|[^'])*'", String.Single),
            (r'[a-zA-Z_]\w*', Name)
        ]
    }


common_sass_tokens = {
    'value': [
        (r'[ \t]+', Text),
        (r'[!$][\w-]+', Name.Variable),
        (r'url\(', String.Other, 'string-url'),
        (r'[a-z_-][\w-]*(?=\()', Name.Function),
        (words((
            'azimuth', 'background-attachment', 'background-color',
            'background-image', 'background-position', 'background-repeat',
            'background', 'border-bottom-color', 'border-bottom-style',
            'border-bottom-width', 'border-left-color', 'border-left-style',
            'border-left-width', 'border-right', 'border-right-color',
            'border-right-style', 'border-right-width', 'border-top-color',
            'border-top-style', 'border-top-width', 'border-bottom',
            'border-collapse', 'border-left', 'border-width', 'border-color',
            'border-spacing', 'border-style', 'border-top', 'border', 'caption-side',
            'clear', 'clip', 'color', 'content', 'counter-increment', 'counter-reset',
            'cue-after', 'cue-before', 'cue', 'cursor', 'direction', 'display',
            'elevation', 'empty-cells', 'float', 'font-family', 'font-size',
            'font-size-adjust', 'font-stretch', 'font-style', 'font-variant',
            'font-weight', 'font', 'height', 'letter-spacing', 'line-height',
            'list-style-type', 'list-style-image', 'list-style-position',
            'list-style', 'margin-bottom', 'margin-left', 'margin-right',
            'margin-top', 'margin', 'marker-offset', 'marks', 'max-height', 'max-width',
            'min-height', 'min-width', 'opacity', 'orphans', 'outline', 'outline-color',
            'outline-style', 'outline-width', 'overflow', 'padding-bottom',
            'padding-left', 'padding-right', 'padding-top', 'padding', 'page',
            'page-break-after', 'page-break-before', 'page-break-inside',
            'pause-after', 'pause-before', 'pause', 'pitch', 'pitch-range',
            'play-during', 'position', 'quotes', 'richness', 'right', 'size',
            'speak-header', 'speak-numeral', 'speak-punctuation', 'speak',
            'speech-rate', 'stress', 'table-layout', 'text-align', 'text-decoration',
            'text-indent', 'text-shadow', 'text-transform', 'top', 'unicode-bidi',
            'vertical-align', 'visibility', 'voice-family', 'volume', 'white-space',
            'widows', 'width', 'word-spacing', 'z-index', 'bottom', 'left',
            'above', 'absolute', 'always', 'armenian', 'aural', 'auto', 'avoid', 'baseline',
            'behind', 'below', 'bidi-override', 'blink', 'block', 'bold', 'bolder', 'both',
            'capitalize', 'center-left', 'center-right', 'center', 'circle',
            'cjk-ideographic', 'close-quote', 'collapse', 'condensed', 'continuous',
            'crop', 'crosshair', 'cross', 'cursive', 'dashed', 'decimal-leading-zero',
            'decimal', 'default', 'digits', 'disc', 'dotted', 'double', 'e-resize', 'embed',
            'extra-condensed', 'extra-expanded', 'expanded', 'fantasy', 'far-left',
            'far-right', 'faster', 'fast', 'fixed', 'georgian', 'groove', 'hebrew', 'help',
            'hidden', 'hide', 'higher', 'high', 'hiragana-iroha', 'hiragana', 'icon',
            'inherit', 'inline-table', 'inline', 'inset', 'inside', 'invert', 'italic',
            'justify', 'katakana-iroha', 'katakana', 'landscape', 'larger', 'large',
            'left-side', 'leftwards', 'level', 'lighter', 'line-through', 'list-item',
            'loud', 'lower-alpha', 'lower-greek', 'lower-roman', 'lowercase', 'ltr',
            'lower', 'low', 'medium', 'message-box', 'middle', 'mix', 'monospace',
            'n-resize', 'narrower', 'ne-resize', 'no-close-quote', 'no-open-quote',
            'no-repeat', 'none', 'normal', 'nowrap', 'nw-resize', 'oblique', 'once',
            'open-quote', 'outset', 'outside', 'overline', 'pointer', 'portrait', 'px',
            'relative', 'repeat-x', 'repeat-y', 'repeat', 'rgb', 'ridge', 'right-side',
            'rightwards', 's-resize', 'sans-serif', 'scroll', 'se-resize',
            'semi-condensed', 'semi-expanded', 'separate', 'serif', 'show', 'silent',
            'slow', 'slower', 'small-caps', 'small-caption', 'smaller', 'soft', 'solid',
            'spell-out', 'square', 'static', 'status-bar', 'super', 'sw-resize',
            'table-caption', 'table-cell', 'table-column', 'table-column-group',
            'table-footer-group', 'table-header-group', 'table-row',
            'table-row-group', 'text', 'text-bottom', 'text-top', 'thick', 'thin',
            'transparent', 'ultra-condensed', 'ultra-expanded', 'underline',
            'upper-alpha', 'upper-latin', 'upper-roman', 'uppercase', 'url',
            'visible', 'w-resize', 'wait', 'wider', 'x-fast', 'x-high', 'x-large', 'x-loud',
            'x-low', 'x-small', 'x-soft', 'xx-large', 'xx-small', 'yes'), suffix=r'\b'),
         Name.Constant),
        (words((
            'indigo', 'gold', 'firebrick', 'indianred', 'darkolivegreen',
            'darkseagreen', 'mediumvioletred', 'mediumorchid', 'chartreuse',
            'mediumslateblue', 'springgreen', 'crimson', 'lightsalmon', 'brown',
            'turquoise', 'olivedrab', 'cyan', 'skyblue', 'darkturquoise',
            'goldenrod', 'darkgreen', 'darkviolet', 'darkgray', 'lightpink',
            'darkmagenta', 'lightgoldenrodyellow', 'lavender', 'yellowgreen', 'thistle',
            'violet', 'orchid', 'ghostwhite', 'honeydew', 'cornflowerblue',
            'darkblue', 'darkkhaki', 'mediumpurple', 'cornsilk', 'bisque', 'slategray',
            'darkcyan', 'khaki', 'wheat', 'deepskyblue', 'darkred', 'steelblue', 'aliceblue',
            'gainsboro', 'mediumturquoise', 'floralwhite', 'coral', 'lightgrey',
            'lightcyan', 'darksalmon', 'beige', 'azure', 'lightsteelblue', 'oldlace',
            'greenyellow', 'royalblue', 'lightseagreen', 'mistyrose', 'sienna',
            'lightcoral', 'orangered', 'navajowhite', 'palegreen', 'burlywood',
            'seashell', 'mediumspringgreen', 'papayawhip', 'blanchedalmond',
            'peru', 'aquamarine', 'darkslategray', 'ivory', 'dodgerblue',
            'lemonchiffon', 'chocolate', 'orange', 'forestgreen', 'slateblue',
            'mintcream', 'antiquewhite', 'darkorange', 'cadetblue', 'moccasin',
            'limegreen', 'saddlebrown', 'darkslateblue', 'lightskyblue', 'deeppink',
            'plum', 'darkgoldenrod', 'sandybrown', 'magenta', 'tan',
            'rosybrown', 'pink', 'lightblue', 'palevioletred', 'mediumseagreen',
            'dimgray', 'powderblue', 'seagreen', 'snow', 'mediumblue', 'midnightblue',
            'paleturquoise', 'palegoldenrod', 'whitesmoke', 'darkorchid', 'salmon',
            'lightslategray', 'lawngreen', 'lightgreen', 'tomato', 'hotpink',
            'lightyellow', 'lavenderblush', 'linen', 'mediumaquamarine',
            'blueviolet', 'peachpuff'), suffix=r'\b'),
         Name.Entity),
        (words((
            'black', 'silver', 'gray', 'white', 'maroon', 'red', 'purple', 'fuchsia', 'green',
            'lime', 'olive', 'yellow', 'navy', 'blue', 'teal', 'aqua'), suffix=r'\b'),
         Name.Builtin),
        (r'\!(important|default)', Name.Exception),
        (r'(true|false)', Name.Pseudo),
        (r'(and|or|not)', Operator.Word),
        (r'/\*', Comment.Multiline, 'inline-comment'),
        (r'//[^\n]*', Comment.Single),
        (r'\#[a-z0-9]{1,6}', Number.Hex),
        (r'(-?\d+)(\%|[a-z]+)?', bygroups(Number.Integer, Keyword.Type)),
        (r'(-?\d*\.\d+)(\%|[a-z]+)?', bygroups(Number.Float, Keyword.Type)),
        (r'#\{', String.Interpol, 'interpolation'),
        (r'[~^*!&%<>|+=@:,./?-]+', Operator),
        (r'[\[\]()]+', Punctuation),
        (r'"', String.Double, 'string-double'),
        (r"'", String.Single, 'string-single'),
        (r'[a-z_-][\w-]*', Name),
    ],

    'interpolation': [
        (r'\}', String.Interpol, '#pop'),
        include('value'),
    ],

    'selector': [
        (r'[ \t]+', Text),
        (r'\:', Name.Decorator, 'pseudo-class'),
        (r'\.', Name.Class, 'class'),
        (r'\#', Name.Namespace, 'id'),
        (r'[\w-]+', Name.Tag),
        (r'#\{', String.Interpol, 'interpolation'),
        (r'&', Keyword),
        (r'[~^*!&\[\]()<>|+=@:;,./?-]', Operator),
        (r'"', String.Double, 'string-double'),
        (r"'", String.Single, 'string-single'),
    ],

    'string-double': [
        (r'(\\.|#(?=[^\n{])|[^\n"#])+', String.Double),
        (r'#\{', String.Interpol, 'interpolation'),
        (r'"', String.Double, '#pop'),
    ],

    'string-single': [
        (r"(\\.|#(?=[^\n{])|[^\n'#])+", String.Double),
        (r'#\{', String.Interpol, 'interpolation'),
        (r"'", String.Double, '#pop'),
    ],

    'string-url': [
        (r'(\\#|#(?=[^\n{])|[^\n#)])+', String.Other),
        (r'#\{', String.Interpol, 'interpolation'),
        (r'\)', String.Other, '#pop'),
    ],

    'pseudo-class': [
        (r'[\w-]+', Name.Decorator),
        (r'#\{', String.Interpol, 'interpolation'),
        default('#pop'),
    ],

    'class': [
        (r'[\w-]+', Name.Class),
        (r'#\{', String.Interpol, 'interpolation'),
        default('#pop'),
    ],

    'id': [
        (r'[\w-]+', Name.Namespace),
        (r'#\{', String.Interpol, 'interpolation'),
        default('#pop'),
    ],

    'for': [
        (r'(from|to|through)', Operator.Word),
        include('value'),
    ],
}


def _indentation(lexer, match, ctx):
    indentation = match.group(0)
    yield match.start(), Text, indentation
    ctx.last_indentation = indentation
    ctx.pos = match.end()

    if hasattr(ctx, 'block_state') and ctx.block_state and \
            indentation.startswith(ctx.block_indentation) and \
            indentation != ctx.block_indentation:
        ctx.stack.append(ctx.block_state)
    else:
        ctx.block_state = None
        ctx.block_indentation = None
        ctx.stack.append('content')


def _starts_block(token, state):
    def callback(lexer, match, ctx):
        yield match.start(), token, match.group(0)

        if hasattr(ctx, 'last_indentation'):
            ctx.block_indentation = ctx.last_indentation
        else:
            ctx.block_indentation = ''

        ctx.block_state = state
        ctx.pos = match.end()

    return callback


class SassLexer(ExtendedRegexLexer):
    """
    For Sass stylesheets.

    .. versionadded:: 1.3
    """

    name = 'Sass'
    aliases = ['sass']
    filenames = ['*.sass']
    mimetypes = ['text/x-sass']

    flags = re.IGNORECASE | re.MULTILINE

    tokens = {
        'root': [
            (r'[ \t]*\n', Text),
            (r'[ \t]*', _indentation),
        ],

        'content': [
            (r'//[^\n]*', _starts_block(Comment.Single, 'single-comment'),
             'root'),
            (r'/\*[^\n]*', _starts_block(Comment.Multiline, 'multi-comment'),
             'root'),
            (r'@import', Keyword, 'import'),
            (r'@for', Keyword, 'for'),
            (r'@(debug|warn|if|while)', Keyword, 'value'),
            (r'(@mixin)( [\w-]+)', bygroups(Keyword, Name.Function), 'value'),
            (r'(@include)( [\w-]+)', bygroups(Keyword, Name.Decorator), 'value'),
            (r'@extend', Keyword, 'selector'),
            (r'@[\w-]+', Keyword, 'selector'),
            (r'=[\w-]+', Name.Function, 'value'),
            (r'\+[\w-]+', Name.Decorator, 'value'),
            (r'([!$][\w-]\w*)([ \t]*(?:(?:\|\|)?=|:))',
             bygroups(Name.Variable, Operator), 'value'),
            (r':', Name.Attribute, 'old-style-attr'),
            (r'(?=.+?[=:]([^a-z]|$))', Name.Attribute, 'new-style-attr'),
            default('selector'),
        ],

        'single-comment': [
            (r'.+', Comment.Single),
            (r'\n', Text, 'root'),
        ],

        'multi-comment': [
            (r'.+', Comment.Multiline),
            (r'\n', Text, 'root'),
        ],

        'import': [
            (r'[ \t]+', Text),
            (r'\S+', String),
            (r'\n', Text, 'root'),
        ],

        'old-style-attr': [
            (r'[^\s:="\[]+', Name.Attribute),
            (r'#\{', String.Interpol, 'interpolation'),
            (r'[ \t]*=', Operator, 'value'),
            default('value'),
        ],

        'new-style-attr': [
            (r'[^\s:="\[]+', Name.Attribute),
            (r'#\{', String.Interpol, 'interpolation'),
            (r'[ \t]*[=:]', Operator, 'value'),
        ],

        'inline-comment': [
            (r"(\\#|#(?=[^\n{])|\*(?=[^\n/])|[^\n#*])+", Comment.Multiline),
            (r'#\{', String.Interpol, 'interpolation'),
            (r"\*/", Comment, '#pop'),
        ],
    }
    for group, common in iteritems(common_sass_tokens):
        tokens[group] = copy.copy(common)
    tokens['value'].append((r'\n', Text, 'root'))
    tokens['selector'].append((r'\n', Text, 'root'))


class ScssLexer(RegexLexer):
    """
    For SCSS stylesheets.
    """

    name = 'SCSS'
    aliases = ['scss']
    filenames = ['*.scss']
    mimetypes = ['text/x-scss']

    flags = re.IGNORECASE | re.DOTALL
    tokens = {
        'root': [
            (r'\s+', Text),
            (r'//.*?\n', Comment.Single),
            (r'/\*.*?\*/', Comment.Multiline),
            (r'@import', Keyword, 'value'),
            (r'@for', Keyword, 'for'),
            (r'@(debug|warn|if|while)', Keyword, 'value'),
            (r'(@mixin)( [\w-]+)', bygroups(Keyword, Name.Function), 'value'),
            (r'(@include)( [\w-]+)', bygroups(Keyword, Name.Decorator), 'value'),
            (r'@extend', Keyword, 'selector'),
            (r'(@media)(\s+)', bygroups(Keyword, Text), 'value'),
            (r'@[\w-]+', Keyword, 'selector'),
            (r'(\$[\w-]*\w)([ \t]*:)', bygroups(Name.Variable, Operator), 'value'),
            # TODO: broken, and prone to infinite loops.
            #(r'(?=[^;{}][;}])', Name.Attribute, 'attr'),
            #(r'(?=[^;{}:]+:[^a-z])', Name.Attribute, 'attr'),
            default('selector'),
        ],

        'attr': [
            (r'[^\s:="\[]+', Name.Attribute),
            (r'#\{', String.Interpol, 'interpolation'),
            (r'[ \t]*:', Operator, 'value'),
            default('#pop'),
        ],

        'inline-comment': [
            (r"(\\#|#(?=[^{])|\*(?=[^/])|[^#*])+", Comment.Multiline),
            (r'#\{', String.Interpol, 'interpolation'),
            (r"\*/", Comment, '#pop'),
        ],
    }
    for group, common in iteritems(common_sass_tokens):
        tokens[group] = copy.copy(common)
    tokens['value'].extend([(r'\n', Text), (r'[;{}]', Punctuation, '#pop')])
    tokens['selector'].extend([(r'\n', Text), (r'[;{}]', Punctuation, '#pop')])


class LessCssLexer(CssLexer):
    """
    For `LESS <http://lesscss.org/>`_ styleshets.

    .. versionadded:: 2.1
    """

    name = 'LessCss'
    aliases = ['less']
    filenames = ['*.less']
    mimetypes = ['text/x-less-css']

    tokens = {
        'root': [
            (r'@\w+', Name.Variable),
            inherit,
        ],
        'content': [
            (r'{', Punctuation, '#push'),
            inherit,
        ],
    }
