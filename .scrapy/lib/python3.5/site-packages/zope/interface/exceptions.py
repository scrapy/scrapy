##############################################################################
#
# Copyright (c) 2002 Zope Foundation and Contributors.
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
"""Interface-specific exceptions
"""

class Invalid(Exception):
    """A specification is violated
    """

class DoesNotImplement(Invalid):
    """ This object does not implement """
    def __init__(self, interface):
        self.interface = interface

    def __str__(self):
        return """An object does not implement interface %(interface)s

        """ % self.__dict__

class BrokenImplementation(Invalid):
    """An attribute is not completely implemented.
    """

    def __init__(self, interface, name):
        self.interface=interface
        self.name=name

    def __str__(self):
        return """An object has failed to implement interface %(interface)s

        The %(name)s attribute was not provided.
        """ % self.__dict__

class BrokenMethodImplementation(Invalid):
    """An method is not completely implemented.
    """

    def __init__(self, method, mess):
        self.method=method
        self.mess=mess

    def __str__(self):
        return """The implementation of %(method)s violates its contract
        because %(mess)s.
        """ % self.__dict__

class InvalidInterface(Exception):
    """The interface has invalid contents
    """

class BadImplements(TypeError):
    """An implementation assertion is invalid

    because it doesn't contain an interface or a sequence of valid
    implementation assertions.
    """
