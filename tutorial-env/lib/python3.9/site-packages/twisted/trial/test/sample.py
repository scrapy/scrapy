"""This module is used by test_loader to test the Trial test loading
functionality. Do NOT change the number of tests in this module.  Do NOT change
the names the tests in this module.
"""


import unittest as pyunit

from twisted.python.util import mergeFunctionMetadata
from twisted.trial import unittest


class FooTest(unittest.SynchronousTestCase):
    def test_foo(self):
        pass

    def test_bar(self):
        pass


def badDecorator(fn):
    """
    Decorate a function without preserving the name of the original function.
    Always return a function with the same name.
    """

    def nameCollision(*args, **kwargs):
        return fn(*args, **kwargs)

    return nameCollision


def goodDecorator(fn):
    """
    Decorate a function and preserve the original name.
    """

    def nameCollision(*args, **kwargs):
        return fn(*args, **kwargs)

    return mergeFunctionMetadata(fn, nameCollision)


class DecorationTest(unittest.SynchronousTestCase):
    def test_badDecorator(self):
        """
        This test method is decorated in a way that gives it a confusing name
        that collides with another method.
        """

    test_badDecorator = badDecorator(test_badDecorator)

    def test_goodDecorator(self):
        """
        This test method is decorated in a way that preserves its name.
        """

    test_goodDecorator = goodDecorator(test_goodDecorator)

    def renamedDecorator(self):
        """
        This is secretly a test method and will be decorated and then renamed so
        test discovery can find it.
        """

    test_renamedDecorator = goodDecorator(renamedDecorator)

    def nameCollision(self):
        """
        This isn't a test, it's just here to collide with tests.
        """


class PyunitTest(pyunit.TestCase):
    def test_foo(self):
        pass

    def test_bar(self):
        pass


class NotATest:
    def test_foo(self):
        pass


class AlphabetTest(unittest.SynchronousTestCase):
    def test_a(self):
        pass

    def test_b(self):
        pass

    def test_c(self):
        pass
