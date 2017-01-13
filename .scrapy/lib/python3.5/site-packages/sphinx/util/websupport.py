# -*- coding: utf-8 -*-
"""
    sphinx.util.websupport
    ~~~~~~~~~~~~~~~~~~~~~~

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""


def is_commentable(node):
    # return node.__class__.__name__ in ('paragraph', 'literal_block')
    return node.__class__.__name__ == 'paragraph'
