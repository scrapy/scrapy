# -*- twisted.conch.test.test_mixin -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from twisted.conch import mixin
from twisted.test.proto_helpers import StringTransport
from twisted.trial import unittest


class TestBufferingProto(mixin.BufferingMixin):
    scheduled = False
    rescheduled = 0

    def schedule(self):
        self.scheduled = True
        return object()

    def reschedule(self, token):
        self.rescheduled += 1


class BufferingTests(unittest.TestCase):
    def testBuffering(self):
        p = TestBufferingProto()
        t = p.transport = StringTransport()

        self.assertFalse(p.scheduled)

        L = [b"foo", b"bar", b"baz", b"quux"]

        p.write(b"foo")
        self.assertTrue(p.scheduled)
        self.assertFalse(p.rescheduled)

        for s in L:
            n = p.rescheduled
            p.write(s)
            self.assertEqual(p.rescheduled, n + 1)
            self.assertEqual(t.value(), b"")

        p.flush()
        self.assertEqual(t.value(), b"foo" + b"".join(L))
