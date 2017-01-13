##############################################################################
#
# Copyright (c) 2010 Zope Foundation and Contributors.
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
""" zope.interface.exceptions unit tests
"""
import unittest

def _makeIface():
    from zope.interface import Interface
    class IDummy(Interface):
        pass
    return IDummy

class DoesNotImplementTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.exceptions import DoesNotImplement
        return DoesNotImplement

    def _makeOne(self, iface=None):
        if iface is None:
            iface = _makeIface()
        return self._getTargetClass()(iface)

    def test___str__(self):
        dni = self._makeOne()
        # XXX The trailing newlines and blank spaces are a stupid artifact.
        self.assertEqual(str(dni),
            'An object does not implement interface <InterfaceClass '
               'zope.interface.tests.test_exceptions.IDummy>\n\n        ')

class BrokenImplementationTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.exceptions import BrokenImplementation
        return BrokenImplementation

    def _makeOne(self, iface=None, name='missing'):
        if iface is None:
            iface = _makeIface()
        return self._getTargetClass()(iface, name)

    def test___str__(self):
        dni = self._makeOne()
        # XXX The trailing newlines and blank spaces are a stupid artifact.
        self.assertEqual(str(dni),
            'An object has failed to implement interface <InterfaceClass '
               'zope.interface.tests.test_exceptions.IDummy>\n\n'
               '        The missing attribute was not provided.\n        ')

class BrokenMethodImplementationTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.exceptions import BrokenMethodImplementation
        return BrokenMethodImplementation

    def _makeOne(self, method='aMethod', mess='I said so'):
        return self._getTargetClass()(method, mess)

    def test___str__(self):
        dni = self._makeOne()
        self.assertEqual(str(dni),
            'The implementation of aMethod violates its contract\n'
             '        because I said so.\n        ')

