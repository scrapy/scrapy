# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the command-line mailer tool provided by Twisted Mail.
"""

from twisted.scripts.test.test_scripts import ScriptTestsMixin
from twisted.trial.unittest import TestCase


class ScriptTests(TestCase, ScriptTestsMixin):
    """
    Tests for all one of mail's scripts.
    """

    def test_mailmail(self):
        self.scriptTest("mail/mailmail")
