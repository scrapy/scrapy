##############################################################################
# Copyright (c) 2020 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
##############################################################################
"""
Interface definitions paralleling the abstract base classes defined in
:mod:`collections.abc`.

After this module is imported, the standard library types will declare
that they implement the appropriate interface. While most standard
library types will properly implement that interface (that
is, ``verifyObject(ISequence, list()))`` will pass, for example), a few might not:

    - `memoryview` doesn't feature all the defined methods of
      ``ISequence`` such as ``count``; it is still declared to provide
      ``ISequence`` though.

    - `collections.deque.pop` doesn't accept the ``index`` argument of
      `collections.abc.MutableSequence.pop`

    - `range.index` does not accept the ``start`` and ``stop`` arguments.

.. versionadded:: 5.0.0
"""

import sys

from abc import ABCMeta
from collections import abc
from collections import OrderedDict
from collections import UserList
from collections import UserDict
from collections import UserString

from zope.interface.common import ABCInterface
from zope.interface.common import optional

# pylint:disable=inherit-non-class,
# pylint:disable=no-self-argument,no-method-argument
# pylint:disable=unexpected-special-method-signature
# pylint:disable=no-value-for-parameter


def _new_in_ver(name, ver,
                bases_if_missing=(ABCMeta,),
                register_if_missing=()):
    if ver:
        return getattr(abc, name)

    # TODO: It's a shame to have to repeat the bases when
    # the ABC is missing. Can we DRY that?
    missing = ABCMeta(name, bases_if_missing, {
        '__doc__': "The ABC %s is not defined in this version of Python." % (
            name
        ),
    })

    for c in register_if_missing:
        missing.register(c)

    return missing

__all__ = [
    'IAsyncGenerator',
    'IAsyncIterable',
    'IAsyncIterator',
    'IAwaitable',
    'ICollection',
    'IContainer',
    'ICoroutine',
    'IGenerator',
    'IHashable',
    'IItemsView',
    'IIterable',
    'IIterator',
    'IKeysView',
    'IMapping',
    'IMappingView',
    'IMutableMapping',
    'IMutableSequence',
    'IMutableSet',
    'IReversible',
    'ISequence',
    'ISet',
    'ISized',
    'IValuesView',
]

class IContainer(ABCInterface):
    abc = abc.Container

    @optional
    def __contains__(other):
        """
        Optional method. If not provided, the interpreter will use
        ``__iter__`` or the old ``__getitem__`` protocol
        to implement ``in``.
        """

class IHashable(ABCInterface):
    abc = abc.Hashable

class IIterable(ABCInterface):
    abc = abc.Iterable

    @optional
    def __iter__():
        """
        Optional method. If not provided, the interpreter will
        implement `iter` using the old ``__getitem__`` protocol.
        """

class IIterator(IIterable):
    abc = abc.Iterator

class IReversible(IIterable):
    abc = _new_in_ver('Reversible', True, (IIterable.getABC(),))

    @optional
    def __reversed__():
        """
        Optional method. If this isn't present, the interpreter
        will use ``__len__`` and ``__getitem__`` to implement the
        `reversed` builtin.
        """

class IGenerator(IIterator):
    # New in Python 3.5
    abc = _new_in_ver('Generator', True, (IIterator.getABC(),))


class ISized(ABCInterface):
    abc = abc.Sized


# ICallable is not defined because there's no standard signature.

class ICollection(ISized,
                  IIterable,
                  IContainer):
    abc = _new_in_ver('Collection', True,
                      (ISized.getABC(), IIterable.getABC(), IContainer.getABC()))


class ISequence(IReversible,
                ICollection):
    abc = abc.Sequence
    extra_classes = (UserString,)
    # On Python 2, basestring is registered as an ISequence, and
    # its subclass str is an IByteString. If we also register str as
    # an ISequence, that tends to lead to inconsistent resolution order.
    ignored_classes = (basestring,) if str is bytes else () # pylint:disable=undefined-variable

    @optional
    def __reversed__():
        """
        Optional method. If this isn't present, the interpreter
        will use ``__len__`` and ``__getitem__`` to implement the
        `reversed` builtin.
        """

    @optional
    def __iter__():
        """
        Optional method. If not provided, the interpreter will
        implement `iter` using the old ``__getitem__`` protocol.
        """

class IMutableSequence(ISequence):
    abc = abc.MutableSequence
    extra_classes = (UserList,)


class IByteString(ISequence):
    """
    This unifies `bytes` and `bytearray`.
    """
    abc = _new_in_ver('ByteString', True,
                      (ISequence.getABC(),),
                      (bytes, bytearray))


class ISet(ICollection):
    abc = abc.Set


class IMutableSet(ISet):
    abc = abc.MutableSet


class IMapping(ICollection):
    abc = abc.Mapping
    extra_classes = (dict,)
    # OrderedDict is a subclass of dict. On CPython 2,
    # it winds up registered as a IMutableMapping, which
    # produces an inconsistent IRO if we also try to register it
    # here.
    ignored_classes = (OrderedDict,)


class IMutableMapping(IMapping):
    abc = abc.MutableMapping
    extra_classes = (dict, UserDict,)
    ignored_classes = (OrderedDict,)

class IMappingView(ISized):
    abc = abc.MappingView


class IItemsView(IMappingView, ISet):
    abc = abc.ItemsView


class IKeysView(IMappingView, ISet):
    abc = abc.KeysView


class IValuesView(IMappingView, ICollection):
    abc = abc.ValuesView

    @optional
    def __contains__(other):
        """
        Optional method. If not provided, the interpreter will use
        ``__iter__`` or the old ``__len__`` and ``__getitem__`` protocol
        to implement ``in``.
        """

class IAwaitable(ABCInterface):
    abc = _new_in_ver('Awaitable', True)


class ICoroutine(IAwaitable):
    abc = _new_in_ver('Coroutine', True)


class IAsyncIterable(ABCInterface):
    abc = _new_in_ver('AsyncIterable', True)


class IAsyncIterator(IAsyncIterable):
    abc = _new_in_ver('AsyncIterator', True)


class IAsyncGenerator(IAsyncIterator):
    abc = _new_in_ver('AsyncGenerator', True)
