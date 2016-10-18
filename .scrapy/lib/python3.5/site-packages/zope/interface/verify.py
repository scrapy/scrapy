##############################################################################
#
# Copyright (c) 2001, 2002 Zope Foundation and Contributors.
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
"""Verify interface implementations
"""
from zope.interface.exceptions import BrokenImplementation, DoesNotImplement
from zope.interface.exceptions import BrokenMethodImplementation
from types import FunctionType, MethodType
from zope.interface.interface import fromMethod, fromFunction, Method
import sys

# This will be monkey-patched when running under Zope 2, so leave this
# here:
MethodTypes = (MethodType, )


def _verify(iface, candidate, tentative=0, vtype=None):
    """Verify that 'candidate' might correctly implements 'iface'.

    This involves:

      o Making sure the candidate defines all the necessary methods

      o Making sure the methods have the correct signature

      o Making sure the candidate asserts that it implements the interface

    Note that this isn't the same as verifying that the class does
    implement the interface.

    If optional tentative is true, suppress the "is implemented by" test.
    """

    if vtype == 'c':
        tester = iface.implementedBy
    else:
        tester = iface.providedBy

    if not tentative and not tester(candidate):
        raise DoesNotImplement(iface)

    # Here the `desc` is either an `Attribute` or `Method` instance
    for name, desc in iface.namesAndDescriptions(1):
        try:
            attr = getattr(candidate, name)
        except AttributeError:
            if (not isinstance(desc, Method)) and vtype == 'c':
                # We can't verify non-methods on classes, since the
                # class may provide attrs in it's __init__.
                continue

            raise BrokenImplementation(iface, name)

        if not isinstance(desc, Method):
            # If it's not a method, there's nothing else we can test
            continue

        if isinstance(attr, FunctionType):
            if sys.version[0] == '3' and isinstance(candidate, type):
                # This is an "unbound method" in Python 3.
                meth = fromFunction(attr, iface, name=name,
                                    imlevel=1) #pragma NO COVERAGE
            else:
                # Nope, just a normal function
                meth = fromFunction(attr, iface, name=name)
        elif (isinstance(attr, MethodTypes)
              and type(attr.__func__) is FunctionType):
            meth = fromMethod(attr, iface, name)
        elif isinstance(attr, property) and vtype == 'c':
            # We without an instance we cannot be sure it's not a
            # callable.
            continue
        else:
            if not callable(attr):
                raise BrokenMethodImplementation(name, "Not a method")
            # sigh, it's callable, but we don't know how to introspect it, so
            # we have to give it a pass.
            continue #pragma NO COVERAGE

        # Make sure that the required and implemented method signatures are
        # the same.
        desc = desc.getSignatureInfo()
        meth = meth.getSignatureInfo()

        mess = _incompat(desc, meth)
        if mess:
            raise BrokenMethodImplementation(name, mess)

    return True

def verifyClass(iface, candidate, tentative=0):
    return _verify(iface, candidate, tentative, vtype='c')

def verifyObject(iface, candidate, tentative=0):
    return _verify(iface, candidate, tentative, vtype='o')

def _incompat(required, implemented):
    #if (required['positional'] !=
    #    implemented['positional'][:len(required['positional'])]
    #    and implemented['kwargs'] is None):
    #    return 'imlementation has different argument names'
    if len(implemented['required']) > len(required['required']):
        return 'implementation requires too many arguments'
    if ((len(implemented['positional']) < len(required['positional']))
        and not implemented['varargs']):
        return "implementation doesn't allow enough arguments"
    if required['kwargs'] and not implemented['kwargs']:
        return "implementation doesn't support keyword arguments"
    if required['varargs'] and not implemented['varargs']:
        return "implementation doesn't support variable arguments"
