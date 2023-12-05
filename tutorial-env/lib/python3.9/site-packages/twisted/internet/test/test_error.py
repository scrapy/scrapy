# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.error}
"""


from twisted.internet import error
from twisted.trial.unittest import SynchronousTestCase


class ConnectionAbortedTests(SynchronousTestCase):
    """
    Tests for the L{twisted.internet.error.ConnectionAborted} exception.
    """

    def test_str(self):
        """
        The default message of L{ConnectionAborted} is a sentence which points
        to L{ITCPTransport.abortConnection()}
        """
        self.assertEqual(
            ("Connection was aborted locally" " using ITCPTransport.abortConnection."),
            str(error.ConnectionAborted()),
        )

    def test_strArgs(self):
        """
        Any arguments passed to L{ConnectionAborted} are included in its
        message.
        """
        self.assertEqual(
            (
                "Connection was aborted locally using"
                " ITCPTransport.abortConnection:"
                " foo bar."
            ),
            str(error.ConnectionAborted("foo", "bar")),
        )
