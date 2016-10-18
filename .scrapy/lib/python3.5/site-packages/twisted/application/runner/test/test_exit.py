# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.runner._exit}.
"""

from io import BytesIO
from ...runner import _exit
from .._exit import exit, ExitStatus

import twisted.trial.unittest



class ExitTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{exit}.
    """

    def setUp(self):
        self.exit = DummyExit()
        self.patch(_exit, "sysexit", self.exit)


    def test_exitStatusInt(self):
        """
        L{exit} given an L{int} status code will pass it to L{sys.exit}.
        """
        status = 1234
        exit(status)
        self.assertEqual(self.exit.arg, status)


    def test_exitStatusStringNotInt(self):
        """
        L{exit} given a L{str} status code that isn't a string integer raises
        L{ValueError}.
        """
        self.assertRaises(ValueError, exit, "foo")


    def test_exitStatusStringInt(self):
        """
        L{exit} given a L{str} status code that is a string integer passes the
        corresponding L{int} to L{sys.exit}.
        """
        exit("1234")
        self.assertEqual(self.exit.arg, 1234)


    def test_exitConstant(self):
        """
        L{exit} given a L{ValueConstant} status code passes the corresponding
        value to L{sys.exit}.
        """
        status = ExitStatus.EX_CONFIG
        exit(status)
        self.assertEqual(self.exit.arg, status.value)


    def test_exitMessageZero(self):
        """
        L{exit} given a status code of zero (C{0}) writes the given message to
        standard output.
        """
        out = BytesIO()
        self.patch(_exit, "stdout", out)

        message = b"Hello, world."
        exit(0, message)

        self.assertEqual(out.getvalue(), message + b"\n")


    def test_exitMessageNonZero(self):
        """
        L{exit} given a non-zero status code writes the given message to
        standard error.
        """
        out = BytesIO()
        self.patch(_exit, "stderr", out)

        message = b"Hello, world."
        exit(64, message)

        self.assertEqual(out.getvalue(), message + b"\n")



class DummyExit(object):
    """
    Stub for L{sys.exit} that remembers whether it's been called and, if it
    has, what argument it was given.
    """
    def __init__(self):
        self.exited = False


    def __call__(self, arg=None):
        assert not self.exited

        self.arg    = arg
        self.exited = True
