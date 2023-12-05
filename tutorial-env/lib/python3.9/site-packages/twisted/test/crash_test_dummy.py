# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


from zope.interface import Interface, implementer

from twisted.python import components


def foo():
    return 2


class X:
    def __init__(self, x):
        self.x = x

    def do(self):
        # print 'X',self.x,'doing!'
        pass


class XComponent(components.Componentized):
    pass


class IX(Interface):
    pass


@implementer(IX)
class XA(components.Adapter):
    def method(self):
        # Kick start :(
        pass


components.registerAdapter(XA, X, IX)
