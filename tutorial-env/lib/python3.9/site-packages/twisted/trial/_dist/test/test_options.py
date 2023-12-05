# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for distributed trial's options management.
"""

import gc
import os
import sys

from twisted.trial._dist.options import WorkerOptions
from twisted.trial.unittest import TestCase


class WorkerOptionsTests(TestCase):
    """
    Tests for L{WorkerOptions}.
    """

    def setUp(self):
        """
        Build an L{WorkerOptions} object to be used in the tests.
        """
        self.options = WorkerOptions()

    def test_standardOptions(self):
        """
        L{WorkerOptions} supports a subset of standard options supported by
        trial.
        """
        self.addCleanup(sys.setrecursionlimit, sys.getrecursionlimit())
        if gc.isenabled():
            self.addCleanup(gc.enable)
        gc.enable()
        self.options.parseOptions(["--recursionlimit", "2000", "--disablegc"])
        self.assertEqual(2000, sys.getrecursionlimit())
        self.assertFalse(gc.isenabled())

    def test_coverage(self):
        """
        L{WorkerOptions.coverdir} returns the C{coverage} child directory of
        the current directory to be used for storing coverage data.
        """
        self.assertEqual(
            os.path.realpath(os.path.join(os.getcwd(), "coverage")),
            self.options.coverdir().path,
        )
