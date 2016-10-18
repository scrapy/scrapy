# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{inetdtap}.
"""

from twisted.python.reflect import requireModule
from twisted.trial import unittest

inetdtap = requireModule('twisted.runner.inetdtap')
inetdtapSkip = None
if inetdtap is None:
    inetdtapSkip = 'inetdtap not available'



class RPCServerTests(unittest.TestCase):
    """
    Tests for L{inetdtap.RPCServer}
    """
    if inetdtapSkip:
        skip = inetdtapSkip


    def test_deprecation(self):
        """
        It is deprecated.
        """
        inetdtap.RPCServer(
            'some-versions', '/tmp/rpc.conf', 'tcp', 'some-service')

        message = (
            'twisted.runner.inetdtap.RPCServer was deprecated in '
            'Twisted 16.2.0: '
            'The RPC server is no longer maintained.'
            )
        warnings = self.flushWarnings([self.test_deprecation])
        self.assertEqual(1, len(warnings))
        self.assertEqual(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(message, warnings[0]['message'])
