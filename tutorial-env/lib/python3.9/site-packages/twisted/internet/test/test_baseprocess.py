# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet._baseprocess} which implements process-related
functionality that is useful in all platforms supporting L{IReactorProcess}.
"""

from twisted.internet._baseprocess import BaseProcess
from twisted.python.deprecate import getWarningMethod, setWarningMethod
from twisted.trial.unittest import TestCase


class BaseProcessTests(TestCase):
    """
    Tests for L{BaseProcess}, a parent class for other classes which represent
    processes which implements functionality common to many different process
    implementations.
    """

    def test_callProcessExited(self):
        """
        L{BaseProcess._callProcessExited} calls the C{processExited} method of
        its C{proto} attribute and passes it a L{Failure} wrapping the given
        exception.
        """

        class FakeProto:
            reason = None

            def processExited(self, reason):
                self.reason = reason

        reason = RuntimeError("fake reason")
        process = BaseProcess(FakeProto())
        process._callProcessExited(reason)
        process.proto.reason.trap(RuntimeError)
        self.assertIs(reason, process.proto.reason.value)

    def test_callProcessExitedMissing(self):
        """
        L{BaseProcess._callProcessExited} emits a L{DeprecationWarning} if the
        object referred to by its C{proto} attribute has no C{processExited}
        method.
        """

        class FakeProto:
            pass

        reason = object()
        process = BaseProcess(FakeProto())

        self.addCleanup(setWarningMethod, getWarningMethod())
        warnings = []

        def collect(message, category, stacklevel):
            warnings.append((message, category, stacklevel))

        setWarningMethod(collect)

        process._callProcessExited(reason)

        [(message, category, stacklevel)] = warnings
        self.assertEqual(
            message,
            "Since Twisted 8.2, IProcessProtocol.processExited is required.  "
            "%s.%s must implement it." % (FakeProto.__module__, FakeProto.__name__),
        )
        self.assertIs(category, DeprecationWarning)
        # The stacklevel doesn't really make sense for this kind of
        # deprecation.  Requiring it to be 0 will at least avoid pointing to
        # any part of Twisted or a random part of the application's code, which
        # I think would be more misleading than having it point inside the
        # warning system itself. -exarkun
        self.assertEqual(stacklevel, 0)
