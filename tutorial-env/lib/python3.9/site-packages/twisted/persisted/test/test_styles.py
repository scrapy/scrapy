# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.persisted.styles}.
"""

import copy
import pickle

from twisted.persisted.styles import _UniversalPicklingError, unpickleMethod
from twisted.trial import unittest


class Foo:
    """
    Helper class.
    """

    def __init__(self):
        self.instance_member = "test-value"

    def method(self):
        """
        Helper method.
        """
        return self.instance_member


class Bar:
    """
    Helper class.
    """


def sampleFunction():
    """
    A sample function for pickling.
    """


lambdaExample = lambda x: x


class UniversalPicklingErrorTests(unittest.TestCase):
    """
    Tests the L{_UniversalPicklingError} exception.
    """

    def raise_UniversalPicklingError(self):
        """
        Raise L{UniversalPicklingError}.
        """
        raise _UniversalPicklingError

    def test_handledByPickleModule(self):
        """
        Handling L{pickle.PicklingError} handles
        L{_UniversalPicklingError}.
        """
        self.assertRaises(pickle.PicklingError, self.raise_UniversalPicklingError)


class UnpickleMethodTests(unittest.TestCase):
    """
    Tests for the unpickleMethod function.
    """

    def test_instanceBuildingNamePresent(self):
        """
        L{unpickleMethod} returns an instance method bound to the
        instance passed to it.
        """
        foo = Foo()
        m = unpickleMethod("method", foo, Foo)
        self.assertEqual(m, foo.method)
        self.assertIsNot(m, foo.method)

    def test_instanceCopyMethod(self):
        """
        Copying an instance method returns a new method with the same
        behavior.
        """
        foo = Foo()
        m = copy.copy(foo.method)
        self.assertEqual(m, foo.method)
        self.assertIsNot(m, foo.method)
        self.assertEqual("test-value", m())
        foo.instance_member = "new-value"
        self.assertEqual("new-value", m())

    def test_instanceBuildingNameNotPresent(self):
        """
        If the named method is not present in the class,
        L{unpickleMethod} finds a method on the class of the instance
        and returns a bound method from there.
        """
        foo = Foo()
        m = unpickleMethod("method", foo, Bar)
        self.assertEqual(m, foo.method)
        self.assertIsNot(m, foo.method)

    def test_copyFunction(self):
        """
        Copying a function returns the same reference, without creating
        an actual copy.
        """
        f = copy.copy(sampleFunction)
        self.assertEqual(f, sampleFunction)

    def test_primeDirective(self):
        """
        We do not contaminate normal function pickling with concerns from
        Twisted.
        """

        def expected(n):
            return "\n".join(
                ["c" + __name__, sampleFunction.__name__, "p" + n, "."]
            ).encode("ascii")

        self.assertEqual(pickle.dumps(sampleFunction, protocol=0), expected("0"))

    def test_lambdaRaisesPicklingError(self):
        """
        Pickling a C{lambda} function ought to raise a L{pickle.PicklingError}.
        """
        self.assertRaises(pickle.PicklingError, pickle.dumps, lambdaExample)
