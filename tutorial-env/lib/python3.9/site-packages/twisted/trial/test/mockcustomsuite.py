# Copyright (c) 2006 Twisted Matrix Laboratories. See LICENSE for details

"""
Mock test module that contains a C{test_suite} method. L{runner.TestLoader}
should load the tests from the C{test_suite}, not from the C{Foo} C{TestCase}.

See {twisted.trial.test.test_loader.LoaderTest.test_loadModuleWith_test_suite}.
"""


from twisted.trial import runner, unittest


class Foo(unittest.SynchronousTestCase):
    def test_foo(self):
        pass


def test_suite():
    ts = runner.TestSuite()
    ts.name = "MyCustomSuite"
    return ts
