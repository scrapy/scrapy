# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.persisted.styles}.
"""

import pickle

from twisted.trial import unittest
from twisted.persisted.styles import unpickleMethod, _UniversalPicklingError


class Foo:
    """
    Helper class.
    """
    def method(self):
        """
        Helper method.
        """



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
        self.assertRaises(pickle.PicklingError,
                          self.raise_UniversalPicklingError)


    def test_handledBycPickleModule(self):
        """
        Handling L{cPickle.PicklingError} handles
        L{_UniversalPicklingError}.
        """
        try:
            import cPickle
        except ImportError:
            raise unittest.SkipTest("cPickle not available.")
        else:
            self.assertRaises(cPickle.PicklingError,
                              self.raise_UniversalPicklingError)



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
        m = unpickleMethod('method', foo, Foo)
        self.assertEqual(m, foo.method)
        self.assertIsNot(m, foo.method)


    def test_instanceBuildingNameNotPresent(self):
        """
        If the named method is not present in the class,
        L{unpickleMethod} finds a method on the class of the instance
        and returns a bound method from there.
        """
        foo = Foo()
        m = unpickleMethod('method', foo, Bar)
        self.assertEqual(m, foo.method)
        self.assertIsNot(m, foo.method)


    def test_primeDirective(self):
        """
        We do not contaminate normal function pickling with concerns from
        Twisted.
        """
        def expected(n):
            return "\n".join([
                    "c" + __name__,
                    sampleFunction.__name__, "p" + n, "."
                ]).encode("ascii")
        self.assertEqual(pickle.dumps(sampleFunction, protocol=0),
                         expected("0"))
        try:
            import cPickle
        except:
            pass
        else:
            self.assertEqual(
                cPickle.dumps(sampleFunction, protocol=0),
                expected("1")
            )


    def test_lambdaRaisesPicklingError(self):
        """
        Pickling a C{lambda} function ought to raise a L{pickle.PicklingError}.
        """
        self.assertRaises(pickle.PicklingError, pickle.dumps, lambdaExample)
        try:
            import cPickle
        except:
            pass
        else:
            self.assertRaises(cPickle.PicklingError, cPickle.dumps,
                              lambdaExample)
