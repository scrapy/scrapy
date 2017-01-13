# Copyright (c) 2005 Divmod, Inc.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

# Don't change the docstring, it's part of the tests
"""
I'm a test drop-in.  The plugin system's unit tests use me.  No one
else should.
"""

from zope.interface import provider

from twisted.plugin import IPlugin
from twisted.test.test_plugin import ITestPlugin, ITestPlugin2



@provider(ITestPlugin, IPlugin)
class TestPlugin:
    """
    A plugin used solely for testing purposes.
    """

    def test1():
        pass
    test1 = staticmethod(test1)



@provider(ITestPlugin2, IPlugin)
class AnotherTestPlugin:
    """
    Another plugin used solely for testing purposes.
    """

    def test():
        pass
    test = staticmethod(test)



@provider(ITestPlugin2, IPlugin)
class ThirdTestPlugin:
    """
    Another plugin used solely for testing purposes.
    """

    def test():
        pass
    test = staticmethod(test)

