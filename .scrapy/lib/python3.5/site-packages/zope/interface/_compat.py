##############################################################################
#
# Copyright (c) 2006 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Basic components support
"""
import sys
import types

if sys.version_info[0] < 3: #pragma NO COVER

    def _normalize_name(name):
        if isinstance(name, basestring):
            return unicode(name)
        raise TypeError("name must be a regular or unicode string")

    CLASS_TYPES = (type, types.ClassType)
    STRING_TYPES = (basestring,)

    _BUILTINS = '__builtin__'

    PYTHON3 = False
    PYTHON2 = True

else: #pragma NO COVER

    def _normalize_name(name):
        if isinstance(name, bytes):
            name = str(name, 'ascii')
        if isinstance(name, str):
            return name
        raise TypeError("name must be a string or ASCII-only bytes")

    CLASS_TYPES = (type,)
    STRING_TYPES = (str,)

    _BUILTINS = 'builtins'

    PYTHON3 = True
    PYTHON2 = False

def _skip_under_py3k(test_method): #pragma NO COVER
    if sys.version_info[0] < 3:
        return test_method
    def _dummy(*args):
        pass
    return _dummy

def _skip_under_py2(test_method): #pragma NO COVER
    if sys.version_info[0] > 2:
        return test_method
    def _dummy(*args):
        pass
    return _dummy
