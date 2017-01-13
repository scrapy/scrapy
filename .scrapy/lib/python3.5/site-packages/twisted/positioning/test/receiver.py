# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Receivers for use in tests.
"""

from __future__ import absolute_import, division

from twisted.positioning import base, ipositioning


class MockPositioningReceiver(base.BasePositioningReceiver):
    """
    A mock positioning receiver.

    Mocks all the L{IPositioningReceiver} methods with stubs that don't do
    anything but register that they were called.

    @ivar called: A mapping of names of callbacks that have been called to
        C{True}.
    @type called: C{dict}
    """
    def __init__(self):
        self.clear()

        for methodName in ipositioning.IPositioningReceiver:
            self._addCallback(methodName)


    def clear(self):
        """
        Forget all the methods that have been called on this receiver, by
        emptying C{self.called}.
        """
        self.called = {}


    def _addCallback(self, name):
        """
        Adds a callback of the given name, setting C{self.called[name]} to
        C{True} when called.
        """
        def callback(*a, **kw):
            self.called[name] = True

        setattr(self, name, callback)
