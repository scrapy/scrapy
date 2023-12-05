# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.application.runner._exit}.
"""

from io import StringIO
from typing import Optional, Union

import twisted.trial.unittest
from ...runner import _exit
from .._exit import ExitStatus, exit


class ExitTests(twisted.trial.unittest.TestCase):
    """
    Tests for L{exit}.
    """

    def setUp(self) -> None:
        self.exit = DummyExit()
        self.patch(_exit, "sysexit", self.exit)

    def test_exitStatusInt(self) -> None:
        """
        L{exit} given an L{int} status code will pass it to L{sys.exit}.
        """
        status = 1234
        exit(status)
        self.assertEqual(self.exit.arg, status)  # type: ignore[unreachable]

    def test_exitConstant(self) -> None:
        """
        L{exit} given a L{ValueConstant} status code passes the corresponding
        value to L{sys.exit}.
        """
        status = ExitStatus.EX_CONFIG
        exit(status)
        self.assertEqual(self.exit.arg, status.value)  # type: ignore[unreachable]

    def test_exitMessageZero(self) -> None:
        """
        L{exit} given a status code of zero (C{0}) writes the given message to
        standard output.
        """
        out = StringIO()
        self.patch(_exit, "stdout", out)

        message = "Hello, world."
        exit(0, message)

        self.assertEqual(out.getvalue(), message + "\n")  # type: ignore[unreachable]

    def test_exitMessageNonZero(self) -> None:
        """
        L{exit} given a non-zero status code writes the given message to
        standard error.
        """
        out = StringIO()
        self.patch(_exit, "stderr", out)

        message = "Hello, world."
        exit(64, message)

        self.assertEqual(out.getvalue(), message + "\n")  # type: ignore[unreachable]


class DummyExit:
    """
    Stub for L{sys.exit} that remembers whether it's been called and, if it
    has, what argument it was given.
    """

    def __init__(self) -> None:
        self.exited = False

    def __call__(self, arg: Optional[Union[int, str]] = None) -> None:
        assert not self.exited

        self.arg = arg
        self.exited = True
