# -*- coding: utf-8 -*-
"""
    sphinx.util.logging
    ~~~~~~~~~~~~~~~~~~~

    Logging utility functions for Sphinx.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""


def is_suppressed_warning(type, subtype, suppress_warnings):
    """Check the warning is suppressed or not."""
    if type is None:
        return False

    for warning_type in suppress_warnings:
        if '.' in warning_type:
            target, subtarget = warning_type.split('.', 1)
        else:
            target, subtarget = warning_type, None

        if target == type:
            if (subtype is None or subtarget is None or
               subtarget == subtype or subtarget == '*'):
                return True

    return False
