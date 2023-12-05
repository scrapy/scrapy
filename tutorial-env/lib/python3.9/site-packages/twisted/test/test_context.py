# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.context}.
"""


from twisted.python import context
from twisted.trial.unittest import SynchronousTestCase


class ContextTests(SynchronousTestCase):
    """
    Tests for the module-scope APIs for L{twisted.python.context}.
    """

    def test_notPresentIfNotSet(self):
        """
        Arbitrary keys which have not been set in the context have an associated
        value of L{None}.
        """
        self.assertIsNone(context.get("x"))

    def test_setByCall(self):
        """
        Values may be associated with keys by passing them in a dictionary as
        the first argument to L{twisted.python.context.call}.
        """
        self.assertEqual(context.call({"x": "y"}, context.get, "x"), "y")

    def test_unsetAfterCall(self):
        """
        After a L{twisted.python.context.call} completes, keys specified in the
        call are no longer associated with the values from that call.
        """
        context.call({"x": "y"}, lambda: None)
        self.assertIsNone(context.get("x"))

    def test_setDefault(self):
        """
        A default value may be set for a key in the context using
        L{twisted.python.context.setDefault}.
        """
        key = object()
        self.addCleanup(context.defaultContextDict.pop, key, None)
        context.setDefault(key, "y")
        self.assertEqual("y", context.get(key))
