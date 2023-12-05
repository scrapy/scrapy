# Copyright (c) 2006 Twisted Matrix Laboratories. See LICENSE for details

"""
Mock test module that contains both a C{test_suite} and a C{testSuite} method.
L{runner.TestLoader} should load the tests from the C{testSuite}, not from the
C{Foo} C{TestCase} nor from the C{test_suite} method.

See {twisted.trial.test.test_loader.LoaderTest.test_loadModuleWithBothCustom}.
"""


from twisted.trial import runner, unittest


class Foo(unittest.SynchronousTestCase):
    def test_foo(self):
        pass


def test_suite():
    ts = runner.TestSuite()
    ts.name = "test_suite"
    return ts


def testSuite():
    ts = runner.TestSuite()
    ts.name = "testSuite"
    return ts
