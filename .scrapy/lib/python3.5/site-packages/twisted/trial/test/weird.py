from __future__ import division, absolute_import

import unittest

from twisted.internet import defer

# Used in test_tests.UnhandledDeferredTests

class TestBleeding(unittest.TestCase):
    """This test creates an unhandled Deferred and leaves it in a cycle.

    The Deferred is left in a cycle so that the garbage collector won't pick it
    up immediately.  We were having some problems where unhandled Deferreds in
    one test were failing random other tests. (See #1507, #1213)
    """
    def test_unhandledDeferred(self):
        try:
            1/0
        except ZeroDivisionError:
            f = defer.fail()
        # these two lines create the cycle. don't remove them
        l = [f]
        l.append(l)
