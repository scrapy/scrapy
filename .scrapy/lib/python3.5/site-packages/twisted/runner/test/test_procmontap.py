# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.runner.procmontap}.
"""

from twisted.python.usage import UsageError
from twisted.trial import unittest
from twisted.runner.procmon import ProcessMonitor
from twisted.runner import procmontap as tap


class ProcessMonitorTapTests(unittest.TestCase):
    """
    Tests for L{twisted.runner.procmontap}'s option parsing and makeService
    method.
    """

    def test_commandLineRequired(self):
        """
        The command line arguments must be provided.
        """
        opt = tap.Options()
        self.assertRaises(UsageError, opt.parseOptions, [])


    def test_threshold(self):
        """
        The threshold option is recognised as a parameter and coerced to
        float.
        """
        opt = tap.Options()
        opt.parseOptions(['--threshold', '7.5', 'foo'])
        self.assertEqual(opt['threshold'], 7.5)


    def test_killTime(self):
        """
        The killtime option is recognised as a parameter and coerced to float.
        """
        opt = tap.Options()
        opt.parseOptions(['--killtime', '7.5', 'foo'])
        self.assertEqual(opt['killtime'], 7.5)


    def test_minRestartDelay(self):
        """
        The minrestartdelay option is recognised as a parameter and coerced to
        float.
        """
        opt = tap.Options()
        opt.parseOptions(['--minrestartdelay', '7.5', 'foo'])
        self.assertEqual(opt['minrestartdelay'], 7.5)


    def test_maxRestartDelay(self):
        """
        The maxrestartdelay option is recognised as a parameter and coerced to
        float.
        """
        opt = tap.Options()
        opt.parseOptions(['--maxrestartdelay', '7.5', 'foo'])
        self.assertEqual(opt['maxrestartdelay'], 7.5)


    def test_parameterDefaults(self):
        """
        The parameters all have default values
        """
        opt = tap.Options()
        opt.parseOptions(['foo'])
        self.assertEqual(opt['threshold'], 1)
        self.assertEqual(opt['killtime'], 5)
        self.assertEqual(opt['minrestartdelay'], 1)
        self.assertEqual(opt['maxrestartdelay'], 3600)


    def test_makeService(self):
        """
        The command line gets added as a process to the ProcessMontor.
        """
        opt = tap.Options()
        opt.parseOptions(['ping', '-c', '3', '8.8.8.8'])
        s = tap.makeService(opt)
        self.assertIsInstance(s, ProcessMonitor)
        self.assertIn('ping -c 3 8.8.8.8', s.processes)
