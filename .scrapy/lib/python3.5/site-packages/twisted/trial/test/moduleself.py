# -*- test-case-name: twisted.trial.test.moduleself -*-
from twisted.trial import unittest

class Foo(unittest.SynchronousTestCase):

    def testFoo(self):
        pass
