# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A trivial extension that just raises an exception.
See L{twisted.test.test_failure.test_failureConstructionWithMungedStackSucceeds}.
"""



class RaiserException(Exception):
    """
    A speficic exception only used to be identified in tests.
    """


def raiseException():
    """
    Raise L{RaiserException}.
    """
    raise RaiserException("This function is intentionally broken")
