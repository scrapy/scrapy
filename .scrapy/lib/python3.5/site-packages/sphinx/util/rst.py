# -*- coding: utf-8 -*-
"""
    sphinx.util.rst
    ~~~~~~~~~~~~~~~

    reST helper functions.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re

symbols_re = re.compile('([!-/:-@\[-`{-~])')


def escape(text):
    return symbols_re.sub(r'\\\1', text)
