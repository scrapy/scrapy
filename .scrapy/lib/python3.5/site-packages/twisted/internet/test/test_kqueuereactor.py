# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.kqueuereactor}.
"""

from __future__ import division, absolute_import

import errno

from zope.interface import implementer

from twisted.trial.unittest import TestCase

try:
    from twisted.internet.kqreactor import KQueueReactor, _IKQueue
    kqueueSkip = None
except ImportError:
    kqueueSkip = "KQueue not available."


def _fakeKEvent(*args, **kwargs):
    """
    Do nothing.
    """



def makeFakeKQueue(testKQueue, testKEvent):
    """
    Create a fake that implements L{_IKQueue}.

    @param testKQueue: Something that acts like L{select.kqueue}.
    @param testKEvent: Something that acts like L{select.kevent}.
    @return: An implementation of L{_IKQueue} that includes C{testKQueue} and
        C{testKEvent}.
    """
    @implementer(_IKQueue)
    class FakeKQueue(object):
        kqueue = testKQueue
        kevent = testKEvent

    return FakeKQueue()



class KQueueTests(TestCase):
    """
    These are tests for L{KQueueReactor}'s implementation, not its real world
    behaviour. For that, look at
    L{twisted.internet.test.reactormixins.ReactorBuilder}.
    """
    skip = kqueueSkip

    def test_EINTR(self):
        """
        L{KQueueReactor} handles L{errno.EINTR} in C{doKEvent} by returning.
        """
        class FakeKQueue(object):
            """
            A fake KQueue that raises L{errno.EINTR} when C{control} is called,
            like a real KQueue would if it was interrupted.
            """
            def control(self, *args, **kwargs):
                raise OSError(errno.EINTR, "Interrupted")

        reactor = KQueueReactor(makeFakeKQueue(FakeKQueue, _fakeKEvent))
        # This should return cleanly -- should not raise the OSError we're
        # spawning, nor get upset and raise about the incomplete KQueue fake.
        reactor.doKEvent(0)
